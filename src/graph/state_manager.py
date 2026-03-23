# src/graph/state_manager.py
"""统一状态管理器 - 统一管理 BaziAgentState 和 SessionData"""
from typing import Dict, Any, Optional, List
from datetime import datetime
import logging

from .state import BaziAgentState
from src.storage import FileStorage, SessionData, Message, MessageRole, StorageConfig, BaziCache
from src.cache.redis_cache import RedisCacheManager

logger = logging.getLogger(__name__)


class UnifiedStateManager:
    """
    统一状态管理器
    
    功能：
    1. 统一管理 BaziAgentState 和 SessionData
    2. 同步 Redis 缓存和文件存储
    3. 处理状态转换和数据一致性
    """
    
    def __init__(
        self,
        redis_cache: Optional[RedisCacheManager] = None,
        file_storage: Optional[FileStorage] = None
    ):
        self.redis_cache = redis_cache or RedisCacheManager()
        self.file_storage = file_storage or FileStorage()
        self._state: Optional[BaziAgentState] = None
        self._session: Optional[SessionData] = None
        self._dirty = False  # 脏标记，标记数据是否被修改
    
    def create_session(
        self,
        user_id: str,
        session_id: Optional[str] = None,
        system_prompt: Optional[str] = None,
        context_strategy: str = "FULL_CONTEXT",
        retrieval_mode: str = "hybrid_rerank"
    ) -> BaziAgentState:
        """
        创建新会话，同时初始化 State 和 Session
        
        Args:
            user_id: 用户ID
            session_id: 会话ID（可选）
            system_prompt: 系统提示词
            context_strategy: 上下文策略
            retrieval_mode: 检索模式
            
        Returns:
            初始化的 BaziAgentState
        """
        # 生成会话ID
        conversation_id = self._generate_conversation_id(user_id)
        
        # 创建 SessionData
        metadata = {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "session_id": session_id,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "message_count": 0,
            "token_count": 0,
            "context_strategy": context_strategy,
            "retrieval_mode": retrieval_mode
        }
        
        self._session = SessionData(
            conversation_id=conversation_id,
            user_id=user_id,
            messages=[],
            metadata=metadata
        )
        
        # 如果有系统提示词，添加到消息列表
        if system_prompt:
            self._session.add_message(MessageRole.SYSTEM, system_prompt)
        
        # 创建 BaziAgentState
        self._state = BaziAgentState(
            user_id=user_id,
            session_id=session_id,
            conversation_id=conversation_id,
            messages=[],
            message_count=0,
            token_count=0,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            status="initialized",
            context_strategy=context_strategy,
            retrieval_mode=retrieval_mode
        )
        
        # 同步到存储层
        self._sync_all()
        
        logger.info(f"创建新会话: {conversation_id}")
        return self._state
    
    def load_session(self, conversation_id: str) -> Optional[BaziAgentState]:
        """
        加载会话，优先从 Redis，fallback 到文件
        
        Args:
            conversation_id: 会话ID
            
        Returns:
            加载的 BaziAgentState，失败返回 None
        """
        # 1. 尝试从 Redis 加载
        if self.redis_cache.client:
            cached = self.redis_cache.get(f"conversation:{conversation_id}")
            if cached and cached.get("messages"):
                self._state = self._deserialize_state(cached)
                # 先初始化 _session，否则 _update_session_from_state 会因 _session=None 直接 return
                self._session = SessionData(
                    conversation_id=conversation_id,
                    user_id=cached.get("user_id", "default"),
                    messages=[],
                    metadata={
                        "conversation_id": conversation_id,
                        "user_id": cached.get("user_id", "default"),
                        "session_id": cached.get("session_id"),
                        "created_at": datetime.now(),
                        "updated_at": datetime.now(),
                        "message_count": 0,
                        "token_count": 0,
                        "context_strategy": cached.get("context_strategy", "FULL_CONTEXT"),
                        "retrieval_mode": cached.get("retrieval_mode", "hybrid_rerank"),
                    }
                )
                # 同步 State → SessionData（消息、bazi_cache 等）
                self._update_session_from_state()
                return self._state
        
        # 2. 从文件加载
        self._session = self.file_storage.load_session(conversation_id)
        if self._session:
            self._state = self._session_to_state(self._session)
            # 回填 Redis
            if self.redis_cache.client:
                self.redis_cache.set(
                    f"conversation:{conversation_id}",
                    self._state,
                    ttl=86400
                )
            return self._state
        
        return None
    
    def update_state(self, updates: Dict[str, Any]) -> None:
        """
        更新状态，标记脏位
        
        Args:
            updates: 要更新的字段字典
        """
        if self._state is None:
            logger.warning("状态未初始化，无法更新")
            return
        
        for key, value in updates.items():
            self._state[key] = value
        
        self._dirty = True
        
        # 同步到 SessionData
        self._update_session_from_state()
    
    def get_state(self) -> Optional[BaziAgentState]:
        """获取当前状态"""
        return self._state
    
    def get_session(self) -> Optional[SessionData]:
        """获取当前会话"""
        return self._session
    
    def save(self, force: bool = False) -> bool:
        """
        同步到存储层
        
        Args:
            force: 是否强制保存，即使没有修改
            
        Returns:
            保存是否成功
        """
        if not self._dirty and not force:
            return True
        
        success = self._sync_all()
        self._dirty = False
        return success
    
    def add_message(self, role: str, content: str) -> None:
        """添加消息到 State 和 Session"""
        if self._state is not None:
            if "messages" not in self._state:
                self._state["messages"] = []
            self._state["messages"].append({"role": role, "content": content})
            self._state["message_count"] = len(self._state["messages"])
            self._state["token_count"] = self._state.get("token_count", 0) + len(content) // 3
            self._state["updated_at"] = datetime.now().isoformat()

        if self._session is not None:
            from src.storage import MessageRole
            role_enum = MessageRole(role)
            self._session.add_message(role_enum, content)
            self._session.metadata.updated_at = datetime.now()

        self._dirty = True

    def update_slots(self, slots: Dict[str, Any]) -> None:
        """更新槽位到 State 和 Session（持久化）"""
        if not slots:
            return

        if self._state is not None:
            existing = self._state.get("intent_slots") or {}
            existing.update(slots)
            self._state["intent_slots"] = existing

        if self._session is not None:
            self._session.metadata.slots.update(slots)

        self._dirty = True

    def get_slots(self) -> Dict[str, Any]:
        """获取当前槽位"""
        if self._session is not None:
            return self._session.metadata.slots.copy()
        if self._state is not None:
            return (self._state.get("intent_slots") or {}).copy()
        return {}

    def clear_session(self) -> bool:
        """清空会话"""
        if self._session:
            self._session.messages = []
            self._session.metadata.message_count = 0
            self._session.metadata.token_count = 0
            self._session.metadata.updated_at = datetime.now()
        
        if self._state:
            self._state["messages"] = []
            self._state["message_count"] = 0
            self._state["token_count"] = 0
            self._state["updated_at"] = datetime.now().isoformat()
            self._state["status"] = "cleared"
        
        self._dirty = True
        return self._sync_all()
    
    def _sync_all(self) -> bool:
        """同步到 Redis 和文件"""
        if self._state is None:
            return False
        
        try:
            # 1. 同步到 Redis
            if self.redis_cache.client:
                self.redis_cache.set(
                    f"conversation:{self._state.get('conversation_id', '')}",
                    self._state,
                    ttl=86400
                )
            
            # 2. 同步到文件
            if self._session:
                self.file_storage.save_session(self._session)
            
            return True
        except Exception as e:
            logger.error(f"同步失败: {e}")
            return False
    
    def _generate_conversation_id(self, user_id: str) -> str:
        """生成会话ID"""
        import uuid
        return f"{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
    
    def _deserialize_state(self, data: Dict[str, Any]) -> BaziAgentState:
        """从字典反序列化 State"""
        # 处理 datetime 字段
        if "created_at" in data and isinstance(data["created_at"], str):
            data["created_at"] = data["created_at"]
        if "updated_at" in data and isinstance(data["updated_at"], str):
            data["updated_at"] = data["updated_at"]
        
        return BaziAgentState(**data)
    
    def _update_session_from_state(self) -> None:
        """从 State 更新 SessionData"""
        if self._state is None or self._session is None:
            return

        # 更新消息
        messages = self._state.get("messages", [])
        self._session.messages = [
            Message(role=MessageRole(msg.get("role", "user")), content=msg.get("content", ""))
            for msg in messages
        ]

        # 更新元数据
        self._session.metadata.message_count = self._state.get("message_count", 0)
        self._session.metadata.token_count = self._state.get("token_count", 0)
        self._session.metadata.updated_at = datetime.now()
        # 同步槽位
        if self._state.get("intent_slots"):
            self._session.metadata.slots = self._state["intent_slots"]

        # 同步 bazi_cache
        bazi_cache_data = self._state.get("bazi_cache")
        if bazi_cache_data and isinstance(bazi_cache_data, dict):
            try:
                from src.storage import BaziCache
                self._session.bazi_cache = BaziCache(**bazi_cache_data)
            except Exception as e:
                logger.warning(f"bazi_cache 同步到 session 失败: {e}")

    
    def _session_to_state(self, session: SessionData) -> BaziAgentState:
        """从 SessionData 转换为 State"""
        state = BaziAgentState(
            conversation_id=session.conversation_id,
            user_id=session.user_id,
            session_id=session.metadata.session_id,
            messages=[
                {
                    "role": msg.role.value if hasattr(msg.role, 'value') else msg.role,
                    "content": msg.content
                }
                for msg in session.messages
            ],
            message_count=session.metadata.message_count,
            token_count=session.metadata.token_count,
            created_at=session.metadata.created_at.isoformat() if hasattr(session.metadata.created_at, 'isoformat') else str(session.metadata.created_at),
            updated_at=session.metadata.updated_at.isoformat() if hasattr(session.metadata.updated_at, 'isoformat') else str(session.metadata.updated_at),
            status="loaded",
            context_strategy=session.metadata.context_strategy,
            retrieval_mode=session.metadata.retrieval_mode
        )
        # 恢复持久化的槽位
        if session.metadata.slots:
            state["intent_slots"] = session.metadata.slots
        # 恢复 bazi_cache
        if session.bazi_cache:
            state["bazi_cache"] = {
                "bazi_data": session.bazi_cache.bazi_data,
                "analysis_result": session.bazi_cache.analysis_result,
            }
        return state
