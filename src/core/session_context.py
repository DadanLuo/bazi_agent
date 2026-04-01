# src/core/session_context.py
"""
================================================================================
请求级会话上下文 — 每个 API 请求一个实例，替代全局单例 UnifiedStateManager
================================================================================

功能说明：
    SessionContext 是一个请求级的会话管理器，每个 HTTP API 请求都会创建一个独立的实例。
    它替代了全局单例的 UnifiedStateManager，实现了更好的线程安全性和可测试性。
    
核心特性：
    1. 请求隔离：每个请求拥有独立的会话实例，避免并发冲突
    2. 双重持久化：同时写入 Redis（快速访问）和文件（持久备份）
    3. 向后兼容：提供与旧 UnifiedStateManager 兼容的 API，支持渐进迁移
    4. 自动迁移：支持从旧 SessionData 格式自动迁移到 UnifiedSession
    5. 线程安全：每个请求独立实例，天然线程安全

使用场景：
    - 在 FastAPI 中间件或路由处理函数中创建 SessionContext 实例
    - 通过 conversation_id 加载已有会话或创建新会话
    - 在分析流程中更新会话状态并自动持久化
    - 处理完成后保存会话供后续追问使用

================================================================================
"""
from typing import Dict, Any, Optional
from datetime import datetime
import uuid
import logging

from src.core.contracts import (
    UnifiedSession, SessionMetadata, ChatMessage, MessageRole,
    BaziCacheData, ANALYSIS_STATE_KEYS,
)
from src.core.tokenizer import estimate_tokens
from src.storage.file_storage import FileStorage
from src.cache.redis_cache import RedisCacheManager

logger = logging.getLogger(__name__)


class SessionContext:
    """
    ================================================================================
    请求级会话上下文 — 线程安全（每个请求独立实例）
    ================================================================================
    
    功能说明：
        SessionContext 是请求级的会话管理器，每个 API 请求创建一个独立实例。
        它替代了全局单例的 UnifiedStateManager，实现了更好的线程安全性和可测试性。
        
    核心特性：
        1. 请求隔离：每个请求拥有独立的会话实例，避免并发冲突
        2. 双重持久化：同时写入 Redis（快速访问）和文件（持久备份）
        3. 向后兼容：提供与旧 UnifiedStateManager 兼容的 API，支持渐进迁移
        4. 自动迁移：支持从旧 SessionData 格式自动迁移到 UnifiedSession
        5. 线程安全：每个请求独立实例，天然线程安全
        
    公开 API 与旧 UnifiedStateManager 兼容，方便渐进迁移。
    内部只维护 UnifiedSession，不再有 TypedDict/Pydantic 双重转换。
    
    使用示例：
        # 在 FastAPI 路由中使用
        @app.post("/api/bazi/analyze")
        async def analyze_bazi(request: BaziRequest):
            # 创建或加载会话
            session_ctx = SessionContext(redis_cache=redis, file_storage=file_storage)
            session = session_ctx.create_session(user_id=request.user_id)
            
            # 更新分析状态
            session_ctx.update_state({"bazi_result": bazi_data})
            
            # 保存会话
            session_ctx.save()
            
            return {"conversation_id": session["metadata"]["conversation_id"]}
    """
    
    def __init__(
        self,
        redis_cache: Optional[RedisCacheManager] = None,
        file_storage: Optional[FileStorage] = None,
    ):
        """
        ================================================================================
        初始化 SessionContext
        ================================================================================
        
        参数说明：
            redis_cache (Optional[RedisCacheManager]): Redis 缓存管理器实例
                - 用于快速读写会话数据
                - TTL 设置为 86400 秒（24小时）
                - 如果为 None，则只使用文件存储
                
            file_storage (Optional[FileStorage]): 文件存储管理器实例
                - 用于持久化备份会话数据
                - 兼容旧的 SessionData 格式
                - 如果为 None，则只使用 Redis 缓存
        
        执行流程：
            1. 初始化 Redis 和文件存储管理器引用
            2. 初始化会话对象为 None（需要显式创建或加载）
            3. 初始化脏标记为 False（表示会话未修改）
        
        异常处理：
            无异常抛出，所有错误在持久化时处理
        """
        self._redis = redis_cache
        self._storage = file_storage
        self._session: Optional[UnifiedSession] = None
        self._dirty = False
    
    # ---- 会话生命周期 ----
    
    def create_session(
        self,
        user_id: str,
        session_id: Optional[str] = None,
        system_prompt: Optional[str] = None,
        context_strategy: str = "FULL_CONTEXT",
        retrieval_mode: str = "hybrid_rerank",
        agent_id: str = "bazi",
    ) -> Dict[str, Any]:
        """
        ================================================================================
        创建新会话
        ================================================================================
        
        功能说明：
            创建一个新的会话，生成唯一的 conversation_id，并初始化会话元数据。
            会话创建后自动持久化到 Redis 和文件存储。
        
        参数说明：
            user_id (str): 用户唯一标识符
                - 用于区分不同用户的会话
                - 作为 conversation_id 的前缀
                
            session_id (Optional[str]): 会话唯一标识符
                - 如果为 None，则自动生成
                - 用于标识特定的会话实例
                
            system_prompt (Optional[str]): 系统提示词
                - 如果提供，会作为第一条 system 消息添加到会话中
                - 用于定义 AI 的角色和行为规范
                
            context_strategy (str): 上下文策略
                - 默认值: "FULL_CONTEXT"
                - 可选值: "FULL_CONTEXT", "RECENT_MESSAGES", "RAG_ONLY"
                - 决定模型可见的历史消息范围
                
            retrieval_mode (str): 检索模式
                - 默认值: "hybrid_rerank"
                - 可选值: "keyword", "semantic", "hybrid", "hybrid_rerank"
                - 决定 RAG 检索知识的方式
                
            agent_id (str): Agent 标识符
                - 默认值: "bazi"
                - 可选值: "bazi", "tarot"
                - 决定使用哪个 Agent 的分析逻辑
        
        返回值：
            Dict[str, Any]: graph-state 兼容的字典
                - 包含完整的会话数据
                - 可直接用于 LangGraph 的 state 更新
                - 格式与 UnifiedSession.to_graph_state() 一致
        
        执行流程：
            1. 生成唯一的 conversation_id（格式: user_id_timestamp_uuid）
            2. 创建 UnifiedSession 实例，包含 SessionMetadata
            3. 如果提供 system_prompt，添加为第一条 system 消息
            4. 设置脏标记为 True
            5. 调用 _persist() 持久化到 Redis 和文件
            6. 记录日志
            7. 返回 graph-state 兼容字典
        
        异常处理：
            无异常抛出，持久化失败时记录日志但不中断流程
        
        使用示例：
            session_ctx = SessionContext(redis_cache=redis, file_storage=file_storage)
            session = session_ctx.create_session(
                user_id="user_123",
                session_id="session_456",
                system_prompt="你是一个专业的八字命理师...",
                context_strategy="FULL_CONTEXT",
                retrieval_mode="hybrid_rerank",
                agent_id="bazi"
            )
            conversation_id = session["metadata"]["conversation_id"]
        """
        conversation_id = self._generate_id(user_id)
        
        self._session = UnifiedSession(
            metadata=SessionMetadata(
                conversation_id=conversation_id,
                user_id=user_id,
                session_id=session_id,
                agent_id=agent_id,
                context_strategy=context_strategy,
                retrieval_mode=retrieval_mode,
            ),
        )
        
        if system_prompt:
            self._session.add_message("system", system_prompt)
        
        self._dirty = True
        self._persist()
        logger.info(f"创建新会话: {conversation_id}")
        return self._session.to_graph_state()
    
    def load_session(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """
        ================================================================================
        加载会话
        ================================================================================
        
        功能说明：
            从持久化存储中加载指定 conversation_id 的会话。
            加载顺序：Redis → 文件（兼容旧 SessionData 格式）
        
        参数说明：
            conversation_id (str): 会话唯一标识符
                - 格式: user_id_timestamp_uuid
                - 用于定位特定的会话
        
        返回值：
            Optional[Dict[str, Any]]: graph-state 兼容的字典
                - 如果找到会话，返回完整的会话数据字典
                - 如果未找到，返回 None
                - 格式与 UnifiedSession.to_graph_state() 一致
        
        执行流程：
            1. 尝试从 Redis 加载
               - 检查 Redis 客户端是否可用
               - 使用 key "session:{conversation_id}" 查询
               - 如果找到，使用 UnifiedSession.model_validate() 反序列化
               - 反序列化成功则返回 graph-state 字典
               - 失败则记录警告日志，继续尝试文件存储
            
            2. 尝试从文件存储加载（兼容旧格式）
               - 检查 FileStorage 是否可用
               - 调用 load_session() 加载旧 SessionData 格式
               - 如果找到，调用 _migrate_old_session() 迁移到 UnifiedSession
               - 迁移成功后回填 Redis（提升后续访问速度）
               - 返回 graph-state 字典
            
            3. 如果两种方式都失败，返回 None
        
        异常处理：
            - Redis 反序列化失败：记录警告日志，fallback 到文件存储
            - 文件加载失败：记录警告日志，返回 None
            - 迁移失败：记录警告日志，返回 None
        
        使用示例：
            session_ctx = SessionContext(redis_cache=redis, file_storage=file_storage)
            session = session_ctx.load_session("user_123_20240101120000_abc12345")
            if session:
                # 使用会话数据
                messages = session["messages"]
                metadata = session["metadata"]
            else:
                # 会话不存在，创建新会话
                session = session_ctx.create_session(user_id="user_123")
        """
        # 1. Redis（快速路径）
        if self._redis and self._redis.client:
            cached = self._redis.get(f"session:{conversation_id}")
            if cached:
                try:
                    self._session = UnifiedSession.model_validate(cached)
                    return self._session.to_graph_state()
                except Exception as e:
                    logger.warning(f"Redis 反序列化失败，fallback 文件: {e}")
        
        # 2. 文件（兼容旧 SessionData 格式）
        if self._storage:
            unified_session = None
            if hasattr(self._storage, "load_unified_session"):
                unified_session = self._storage.load_unified_session(conversation_id)
            if unified_session:
                self._session = unified_session
                return self._session.to_graph_state()

            old_session = self._storage.load_session(conversation_id)
            if old_session:
                self._session = self._migrate_old_session(old_session)
                # 回填 Redis（提升后续访问速度）
                self._persist_redis()
                return self._session.to_graph_state()
        
        return None
    
    def save(self, force: bool = False) -> bool:
        """
        ================================================================================
        持久化会话
        ================================================================================
        
        功能说明：
            将当前会话持久化到 Redis 和文件存储。
            支持强制保存（忽略脏标记）。
        
        参数说明：
            force (bool): 是否强制保存
                - False（默认）：只有当会话被修改（_dirty=True）时才保存
                - True：无论是否修改都强制保存
        
        返回值：
            bool: 保存是否成功
                - True: 保存成功
                - False: 保存失败（记录日志）
        
        执行流程：
            1. 检查是否需要保存
               - 如果 _dirty=False 且 force=False，直接返回 True
               - 否则继续执行保存
            
            2. 调用 _persist() 执行实际持久化
               - 持久化到 Redis
               - 持久化到文件
               - 任一失败都会记录日志
            
            3. 重置脏标记
               - 无论保存成功与否，都重置 _dirty=False
        
        异常处理：
            - 持久化失败：记录错误日志，返回 False
            - 不会抛出异常中断流程
        
        使用示例：
            session_ctx = SessionContext(redis_cache=redis, file_storage=file_storage)
            session_ctx.load_session("user_123_20240101120000_abc12345")
            
            # 更新会话
            session_ctx.update_state({"bazi_result": bazi_data})
            
            # 保存会话
            if session_ctx.save():
                print("会话保存成功")
            else:
                print("会话保存失败")
            
            # 强制保存（即使未修改）
            session_ctx.save(force=True)
        """
        if not self._dirty and not force:
            return True
        success = self._persist()
        self._dirty = False
        return success
    
    # ---- 数据操作（兼容旧 API）----
    
    def get_session(self) -> Optional[UnifiedSession]:
        """
        ================================================================================
        获取底层 UnifiedSession 对象
        ================================================================================
        
        功能说明：
            返回内部维护的 UnifiedSession 对象引用。
            用于需要直接访问 Pydantic 模型的场景。
        
        返回值：
            Optional[UnifiedSession]: UnifiedSession 实例
                - 如果会话已创建/加载，返回会话对象
                - 如果会话未创建/加载，返回 None
        
        使用示例：
            session_ctx = SessionContext()
            session = session_ctx.get_session()
            if session:
                # 直接访问 Pydantic 模型属性
                print(session.metadata.conversation_id)
                print(session.metadata.user_id)
        """
        return self._session
    
    def get_state(self) -> Optional[Dict[str, Any]]:
        """
        ================================================================================
        获取 graph-state 兼容字典
        ================================================================================
        
        功能说明：
            返回与旧代码 state_manager.get_state() 兼容的字典格式。
            用于 LangGraph 节点的状态更新。
        
        返回值：
            Optional[Dict[str, Any]]: graph-state 兼容字典
                - 如果会话存在，返回会话的字典表示
                - 如果会话不存在，返回 None
                - 格式与 UnifiedSession.to_graph_state() 一致
        
        使用示例：
            session_ctx = SessionContext()
            session_ctx.load_session("user_123_20240101120000_abc12345")
            
            # 在 LangGraph 节点中使用
            def my_node(state: BaziAgentState):
                session_ctx = state["session_context"]
                state_dict = session_ctx.get_state()
                # 更新 state
                state_dict["bazi_result"] = bazi_data
                session_ctx.update_state(state_dict)
        """
        if self._session is None:
            return None
        return self._session.to_graph_state()
    
    def add_message(self, role: str, content: str) -> None:
        """
        ================================================================================
        添加消息到会话
        ================================================================================
        
        功能说明：
            向会话的消息历史中添加一条新消息，并标记会话为已修改。
        
        参数说明：
            role (str): 消息角色
                - "user": 用户消息
                - "assistant": AI 消息
                - "system": 系统消息
                - "tool": 工具调用结果
                
            content (str): 消息内容
                - 用户输入的文本
                - AI 生成的回复
                - 系统提示词
                - 工具调用结果
        
        执行流程：
            1. 检查会话是否存在
            2. 调用 UnifiedSession.add_message() 添加消息
            3. 设置脏标记为 True
        
        异常处理：
            - 会话不存在：静默忽略（不抛出异常）
        
        使用示例：
            session_ctx = SessionContext()
            session_ctx.load_session("user_123_20240101120000_abc12345")
            
            # 添加用户消息
            session_ctx.add_message("user", "请帮我分析2024年的运势")
            
            # 添加 AI 消息
            session_ctx.add_message("assistant", "好的，我来为您分析...")
            
            # 保存会话
            session_ctx.save()
        """
        if self._session:
            self._session.add_message(role, content)
            self._dirty = True
    
    def update_state(self, updates: Dict[str, Any]) -> None:
        """
        ================================================================================
        更新分析状态
        ================================================================================
        
        功能说明：
            批量更新会话的分析状态和缓存数据。
            支持更新 bazi_cache、bazi_result 和 analysis_state。
        
        参数说明：
            updates (Dict[str, Any]): 更新数据字典
                - bazi_cache (Dict): 八字缓存数据
                    - bazi_data (Dict): 八字排盘结果
                    - analysis_result (Dict): 八字分析结果
                    - timestamp (datetime): 缓存时间戳
                    - user_query (str): 用户查询
                    - response (str): AI 回复
                
                - bazi_result (Dict): 八字排盘结果
                    - 如果 bazi_cache 不存在，会自动创建
                    - 会同步到 bazi_cache.bazi_data
                
                - 其他键值: 存入 analysis_state
                    - 只有在 ANALYSIS_STATE_KEYS 中的键才会被存储
                    - 包括：geju, yongshen, liunian, knowledge 等
        
        执行流程：
            1. 检查会话是否存在，不存在则直接返回
            
            2. 处理 bazi_cache（特殊逻辑）
               - 如果 updates 中包含 "bazi_cache" 键
               - 从 updates 中弹出该键
               - 如果是字典类型，尝试创建 BaziCacheData 对象
               - 失败则记录警告日志
            
            3. 处理 bazi_result（同步逻辑）
               - 如果 updates 中包含 "bazi_result" 键且不为空
               - 如果 bazi_cache 不存在，创建新的 BaziCacheData
               - 如果 bazi_cache 存在，更新 bazi_data 字段
            
            4. 处理其他键（analysis_state）
               - 遍历 updates 中的其他键值对
               - 只有在 ANALYSIS_STATE_KEYS 中的键才会被存储
               - 存入 analysis_state 字典
            
            5. 更新元数据
               - 设置 updated_at 为当前时间
               - 设置脏标记为 True
        
        异常处理：
            - bazi_cache 格式错误：记录警告日志，继续处理其他字段
            - 会话不存在：静默忽略
        
        使用示例：
            session_ctx = SessionContext()
            session_ctx.load_session("user_123_20240101120000_abc12345")
            
            # 更新分析状态
            session_ctx.update_state({
                "bazi_result": bazi_data,  # 八字排盘结果
                "geju": "正格",  # 格局
                "yongshen": ["火", "土"],  # 喜用神
                "liunian": liunian_result,  # 流年分析
                "knowledge": knowledge_results,  # RAG 检索结果
            })
            
            # 保存会话
            session_ctx.save()
        """
        if self._session is None:
            return
        # bazi_cache 特殊处理（从字典转换为 Pydantic 模型）
        if "bazi_cache" in updates:
            bc = updates.pop("bazi_cache")
            if isinstance(bc, dict):
                try:
                    self._session.bazi_cache = BaziCacheData(**bc)
                except Exception as e:
                    logger.warning(f"bazi_cache 更新失败: {e}")
        # bazi_result 同步到 bazi_cache（如果 bazi_cache 不存在则创建）
        if "bazi_result" in updates and updates["bazi_result"]:
            if self._session.bazi_cache is None:
                self._session.bazi_cache = BaziCacheData(
                    bazi_data=updates["bazi_result"],
                )
            else:
                self._session.bazi_cache.bazi_data = updates["bazi_result"]
        # 其余 key 存入 analysis_state（只存储已知的分析状态键）
        for key, value in updates.items():
            if key in ANALYSIS_STATE_KEYS:
                self._session.analysis_state[key] = value
        self._session.metadata.updated_at = datetime.now()
        self._dirty = True
    
    def update_slots(self, slots: Dict[str, Any]) -> None:
        """
        ================================================================================
        更新槽位信息
        ================================================================================
        
        功能说明：
            更新会话的槽位信息，用于跟踪用户在多轮对话中提供的信息。
        
        参数说明：
            slots (Dict[str, Any]): 槽位数据字典
                - 键：槽位名称（如 "year", "month", "day", "hour", "gender"）
                - 值：槽位值（如 "1990", "1", "1", "12", "male"）
        
        执行流程：
            1. 检查 slots 是否为空或会话是否存在
            2. 更新 SessionMetadata.slots 字典
            3. 设置脏标记为 True
        
        异常处理：
            - slots 为空：静默忽略
            - 会话不存在：静默忽略
        
        使用示例：
            session_ctx = SessionContext()
            session_ctx.load_session("user_123_20240101120000_abc12345")
            
            # 更新槽位
            session_ctx.update_slots({
                "year": "1990",
                "month": "1",
                "day": "1",
                "hour": "12",
                "gender": "male",
            })
            
            # 保存会话
            session_ctx.save()
        """
        if not slots or self._session is None:
            return
        self._session.metadata.slots.update(slots)
        self._dirty = True

    def absorb_graph_result(self, graph_output: Dict[str, Any]) -> None:
        """
        将 graph 输出合并回 UnifiedSession
        """
        if self._session is None:
            return
        self._session.absorb_graph_result(graph_output)
        self._dirty = True
    
    def get_slots(self) -> Dict[str, Any]:
        """
        ================================================================================
        获取槽位信息
        ================================================================================
        
        功能说明：
            返回会话的槽位信息副本，用于检查用户是否提供了足够的信息进行分析。
        
        返回值：
            Dict[str, Any]: 槽位数据字典（副本）
                - 键：槽位名称
                - 值：槽位值
                - 返回副本以防止外部修改影响内部状态
        
        执行流程：
            1. 检查会话是否存在
            2. 返回 slots 字典的副本（使用 copy()）
            3. 如果会话不存在，返回空字典
        
        使用示例：
            session_ctx = SessionContext()
            session_ctx.load_session("user_123_20240101120000_abc12345")
            
            # 获取槽位
            slots = session_ctx.get_slots()
            if "year" not in slots or "month" not in slots:
                # 槽位不完整，提示用户补充
                return "请提供完整的出生年月日时信息"
        """
        if self._session:
            return self._session.metadata.slots.copy()
        return {}
    
    def clear_session(self) -> bool:
        """
        ================================================================================
        清空会话
        ================================================================================
        
        功能说明：
            清空会话的消息历史和分析状态，重置为初始状态。
            用于开始新的分析流程。
        
        返回值：
            bool: 清空是否成功
                - True: 清空成功
                - False: 清空失败
        
        执行流程：
            1. 检查会话是否存在
            2. 清空消息列表
            3. 重置消息计数和 token 计数
            4. 重置更新时间为当前时间
            5. 清空分析状态
            6. 设置脏标记为 True
            7. 强制保存会话
        
        使用示例：
            session_ctx = SessionContext()
            session_ctx.load_session("user_123_20240101120000_abc12345")
            
            # 开始新的分析
            session_ctx.clear_session()
            session_ctx.create_session(
                user_id="user_123",
                system_prompt="你是一个专业的八字命理师..."
            )
        """
        if self._session:
            self._session.messages = []
            self._session.metadata.message_count = 0
            self._session.metadata.token_count = 0
            self._session.metadata.updated_at = datetime.now()
            self._session.analysis_state = {}
            self._dirty = True
        return self.save(force=True)
    
    # ---- 内部方法 ----
    
    def _persist(self) -> bool:
        """
        ================================================================================
        持久化会话到 Redis 和文件
        ================================================================================
        
        功能说明：
            将当前会话同时持久化到 Redis（快速访问）和文件（持久备份）。
            这是内部方法，不直接暴露给外部调用。
        
        返回值：
            bool: 持久化是否成功
                - True: 两者都成功
                - False: 任一失败
        
        执行流程：
            1. 检查会话是否存在，不存在则返回 False
            2. 调用 _persist_redis() 持久化到 Redis
            3. 调用 _persist_file() 持久化到文件
            4. 任一失败都会记录日志
            5. 返回成功标志
        
        异常处理：
            - 会话不存在：返回 False
            - Redis 持久化失败：记录错误日志，继续文件持久化
            - 文件持久化失败：记录警告日志，继续返回
        
        使用示例：
            # 由 save() 方法调用，不直接使用
            session_ctx.save()  # 内部会调用 _persist()
        """
        if self._session is None:
            return False
        try:
            self._persist_redis()
            self._persist_file()
            return True
        except Exception as e:
            logger.error(f"持久化失败: {e}")
            return False
    
    def _persist_redis(self) -> None:
        """
        ================================================================================
        持久化会话到 Redis
        ================================================================================
        
        功能说明：
            将当前会话序列化为 JSON 格式并存储到 Redis。
            TTL 设置为 86400 秒（24小时）。
        
        执行流程：
            1. 检查 Redis 客户端和会话是否存在
            2. 使用 UnifiedSession.model_dump(mode="json") 序列化
            3. 使用 key "session:{conversation_id}" 存储
            4. 设置 TTL 为 86400 秒
        
        异常处理：
            - 任何异常都会被静默忽略（不中断流程）
        
        使用示例：
            # 由 _persist() 方法调用，不直接使用
            self._persist()  # 内部会调用 _persist_redis()
        """
        if self._redis and self._redis.client and self._session:
            cid = self._session.metadata.conversation_id
            data = self._session.model_dump(mode="json")
            self._redis.set(f"session:{cid}", data, ttl=86400)
    
    def _persist_file(self) -> None:
        """
        ================================================================================
        持久化会话到文件（兼容旧格式）
        ================================================================================
        
        功能说明：
            将当前 UnifiedSession 转换为旧的 SessionData 格式并写入文件。
            这是为了兼容旧的 FileStorage 实现。
        
        执行流程：
            1. 检查 FileStorage 和会话是否存在
            2. 导入旧的模型类（SessionData, Message, BaziCache, ConversationMetadata）
            3. 转换消息列表（ChatMessage → Message）
            4. 转换 bazi_cache（BaziCacheData → BaziCache）
            5. 转换元数据（SessionMetadata → ConversationMetadata）
            6. 创建旧 SessionData 对象
            7. 调用 FileStorage.save_session() 写入文件
        
        异常处理：
            - 任何异常都会记录警告日志，不中断流程
        
        使用示例：
            # 由 _persist() 方法调用，不直接使用
            self._persist()  # 内部会调用 _persist_file()
        """
        if not self._storage or not self._session:
            return
        try:
            if hasattr(self._storage, "save_unified_session"):
                self._storage.save_unified_session(self._session)
                return

            from src.storage.models import (
                SessionData, Message, MessageRole as OldRole,
                BaziCache, ConversationMetadata,
            )
            # 转换消息列表
            old_messages = [
                Message(
                    role=OldRole(m.role if isinstance(m.role, str) else m.role.value),
                    content=m.content,
                )
                for m in self._session.messages
            ]
            # 转换 bazi_cache
            old_bazi_cache = None
            if self._session.bazi_cache:
                old_bazi_cache = BaziCache(
                    bazi_data=self._session.bazi_cache.bazi_data,
                    analysis_result=self._session.bazi_cache.analysis_result,
                    timestamp=self._session.bazi_cache.timestamp,
                    user_query=self._session.bazi_cache.user_query,
                    response=self._session.bazi_cache.response,
                )
            # 转换元数据
            meta = self._session.metadata
            old_session = SessionData(
                conversation_id=meta.conversation_id,
                user_id=meta.user_id,
                messages=old_messages,
                bazi_cache=old_bazi_cache,
                metadata=ConversationMetadata(
                    conversation_id=meta.conversation_id,
                    user_id=meta.user_id,
                    session_id=meta.session_id,
                    created_at=meta.created_at,
                    updated_at=meta.updated_at,
                    message_count=meta.message_count,
                    token_count=meta.token_count,
                    context_strategy=meta.context_strategy,
                    retrieval_mode=meta.retrieval_mode,
                    slots=meta.slots,
                ),
            )
            self._storage.save_session(old_session)
        except Exception as e:
            logger.warning(f"文件持久化失败: {e}")
    
    def _migrate_old_session(self, old) -> UnifiedSession:
        """
        ================================================================================
        从旧 SessionData 迁移到 UnifiedSession
        ================================================================================
        
        功能说明：
            将旧的 SessionData 格式转换为新的 UnifiedSession 格式。
            用于加载旧会话数据。
        
        参数说明：
            old: 旧的 SessionData 对象
                - 包含 conversation_id, user_id, messages, bazi_cache, metadata
        
        返回值：
            UnifiedSession: 迁移后的 UnifiedSession 对象
        
        执行流程：
            1. 转换消息列表（Message → ChatMessage）
            2. 转换 bazi_cache（BaziCache → BaziCacheData）
            3. 转换元数据（ConversationMetadata → SessionMetadata）
            4. 创建新的 UnifiedSession 对象
        
        异常处理：
            - 任何异常都会被静默忽略（使用 getattr() 提供默认值）
        
        使用示例：
            # 由 load_session() 方法调用，不直接使用
            session = self._migrate_old_session(old_session)
        """
        # 转换消息列表
        messages = [
            ChatMessage(
                role=MessageRole(m.role.value if hasattr(m.role, "value") else m.role),
                content=m.content,
            )
            for m in old.messages
        ]
        # 转换 bazi_cache
        bazi_cache = None
        if old.bazi_cache:
            bazi_cache = BaziCacheData(
                bazi_data=old.bazi_cache.bazi_data,
                analysis_result=old.bazi_cache.analysis_result,
                timestamp=getattr(old.bazi_cache, "timestamp", datetime.now()),
                user_query=getattr(old.bazi_cache, "user_query", None),
                response=getattr(old.bazi_cache, "response", None),
            )
        # 转换元数据
        meta = old.metadata
        return UnifiedSession(
            metadata=SessionMetadata(
                conversation_id=old.conversation_id,
                user_id=old.user_id,
                session_id=getattr(meta, "session_id", None),
                created_at=meta.created_at,
                updated_at=meta.updated_at,
                message_count=meta.message_count,
                token_count=meta.token_count,
                context_strategy=meta.context_strategy,
                retrieval_mode=meta.retrieval_mode,
                slots=getattr(meta, "slots", {}),
            ),
            messages=messages,
            bazi_cache=bazi_cache,
        )
    
    @staticmethod
    def _generate_id(user_id: str) -> str:
        """
        ================================================================================
        生成唯一的 conversation_id
        ================================================================================
        
        功能说明：
            生成唯一的会话标识符，格式为：user_id_timestamp_uuid
        
        参数说明：
            user_id (str): 用户唯一标识符
        
        返回值：
            str: conversation_id
                - 格式: user_id_YYYYMMDDHHMMSS_uuid8
                - 示例: user_123_20240101120000_abc12345
        
        执行流程：
            1. 获取当前时间并格式化为 YYYYMMDDHHMMSS
            2. 生成 UUID 并取前8位
            3. 拼接成最终的 conversation_id
        
        使用示例：
            # 由 create_session() 方法调用，不直接使用
            conversation_id = self._generate_id(user_id)
        """
        return f"{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
