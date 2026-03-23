# src/core/session_context.py
"""
请求级会话上下文 — 每个 API 请求一个实例，替代全局单例 UnifiedStateManager
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
    请求级会话上下文 — 线程安全（每个请求独立实例）

    公开 API 与旧 UnifiedStateManager 兼容，方便渐进迁移。
    内部只维护 UnifiedSession，不再有 TypedDict/Pydantic 双重转换。
    """

    def __init__(
        self,
        redis_cache: Optional[RedisCacheManager] = None,
        file_storage: Optional[FileStorage] = None,
    ):
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
        """创建新会话，返回 graph-state 兼容 dict"""
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
        """加载会话，优先 Redis，fallback 文件。返回 graph-state 兼容 dict"""
        # 1. Redis
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
            old_session = self._storage.load_session(conversation_id)
            if old_session:
                self._session = self._migrate_old_session(old_session)
                # 回填 Redis
                self._persist_redis()
                return self._session.to_graph_state()

        return None

    def save(self, force: bool = False) -> bool:
        """持久化到 Redis + 文件"""
        if not self._dirty and not force:
            return True
        success = self._persist()
        self._dirty = False
        return success

    # ---- 数据操作（兼容旧 API）----

    def get_session(self) -> Optional[UnifiedSession]:
        return self._session

    def get_state(self) -> Optional[Dict[str, Any]]:
        """兼容旧代码 state_manager.get_state()"""
        if self._session is None:
            return None
        return self._session.to_graph_state()

    def add_message(self, role: str, content: str) -> None:
        if self._session:
            self._session.add_message(role, content)
            self._dirty = True

    def update_state(self, updates: Dict[str, Any]) -> None:
        """更新分析状态 + bazi_cache"""
        if self._session is None:
            return
        # bazi_cache 特殊处理
        if "bazi_cache" in updates:
            bc = updates.pop("bazi_cache")
            if isinstance(bc, dict):
                try:
                    self._session.bazi_cache = BaziCacheData(**bc)
                except Exception as e:
                    logger.warning(f"bazi_cache 更新失败: {e}")
        # bazi_result 同步到 bazi_cache
        if "bazi_result" in updates and updates["bazi_result"]:
            if self._session.bazi_cache is None:
                self._session.bazi_cache = BaziCacheData(
                    bazi_data=updates["bazi_result"],
                )
            else:
                self._session.bazi_cache.bazi_data = updates["bazi_result"]
        # 其余 key 存入 analysis_state
        for key, value in updates.items():
            if key in ANALYSIS_STATE_KEYS:
                self._session.analysis_state[key] = value
        self._session.metadata.updated_at = datetime.now()
        self._dirty = True

    def update_slots(self, slots: Dict[str, Any]) -> None:
        if not slots or self._session is None:
            return
        self._session.metadata.slots.update(slots)
        self._dirty = True

    def get_slots(self) -> Dict[str, Any]:
        if self._session:
            return self._session.metadata.slots.copy()
        return {}

    def clear_session(self) -> bool:
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
        if self._redis and self._redis.client and self._session:
            cid = self._session.metadata.conversation_id
            data = self._session.model_dump(mode="json")
            self._redis.set(f"session:{cid}", data, ttl=86400)

    def _persist_file(self) -> None:
        """兼容旧 FileStorage — 转为旧 SessionData 格式写入"""
        if not self._storage or not self._session:
            return
        try:
            from src.storage.models import (
                SessionData, Message, MessageRole as OldRole,
                BaziCache, ConversationMetadata,
            )
            old_messages = [
                Message(
                    role=OldRole(m.role if isinstance(m.role, str) else m.role.value),
                    content=m.content,
                )
                for m in self._session.messages
            ]
            old_bazi_cache = None
            if self._session.bazi_cache:
                old_bazi_cache = BaziCache(
                    bazi_data=self._session.bazi_cache.bazi_data,
                    analysis_result=self._session.bazi_cache.analysis_result,
                    timestamp=self._session.bazi_cache.timestamp,
                    user_query=self._session.bazi_cache.user_query,
                    response=self._session.bazi_cache.response,
                )
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
        """从旧 SessionData 迁移到 UnifiedSession"""
        messages = [
            ChatMessage(
                role=MessageRole(m.role.value if hasattr(m.role, "value") else m.role),
                content=m.content,
            )
            for m in old.messages
        ]
        bazi_cache = None
        if old.bazi_cache:
            bazi_cache = BaziCacheData(
                bazi_data=old.bazi_cache.bazi_data,
                analysis_result=old.bazi_cache.analysis_result,
                timestamp=getattr(old.bazi_cache, "timestamp", datetime.now()),
                user_query=getattr(old.bazi_cache, "user_query", None),
                response=getattr(old.bazi_cache, "response", None),
            )
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
        return f"{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
