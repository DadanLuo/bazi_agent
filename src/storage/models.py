# src/storage/models.py
"""
================================================================================
⚠️ 旧版数据模型 - 用于向后兼容，新代码请使用 src.core.contracts
================================================================================

本模块包含旧版数据模型，主要用于：
1. FileStorage 的文件读写（兼容旧格式文件）
2. SessionContext 的向后兼容转换

新代码应使用以下替代：
- SessionData → UnifiedSession (src.core.contracts)
- Message → ChatMessage (src.core.contracts)
- BaziCache → BaziCacheData (src.core.contracts)
- ConversationMetadata → SessionMetadata (src.core.contracts)

废弃日期: 2026-03-29
替代模块: src.core.contracts
================================================================================
"""

from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum
import warnings

# 发出废弃警告
warnings.warn(
    "storage.models 中的数据模型已废弃，新代码请使用 src.core.contracts",
    DeprecationWarning,
    stacklevel=2
)


class MessageRole(str, Enum):
    """消息角色 - 与新模型保持一致"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class Message(BaseModel):
    """消息模型 - 旧版格式，请使用 ChatMessage 替代"""
    role: MessageRole
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)
    name: Optional[str] = None


class ConversationMetadata(BaseModel):
    """会话元数据 - 旧版格式，请使用 SessionMetadata 替代"""
    conversation_id: str
    user_id: str
    session_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    message_count: int = 0
    token_count: int = 0
    context_strategy: str = "FULL_CONTEXT"
    retrieval_mode: str = "hybrid_rerank"
    slots: Dict[str, Any] = Field(default_factory=dict)


class BaziCache(BaseModel):
    """八字缓存 - 旧版格式，请使用 BaziCacheData 替代"""
    bazi_data: Dict[str, Any]
    analysis_result: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)
    user_query: Optional[str] = None
    response: Optional[str] = None
    llm_response: Optional[str] = None


class StorageConfig(BaseModel):
    """存储配置"""
    storage_path: str = "data/memory"
    compression: bool = True
    backup_enabled: bool = True
    backup_path: str = "data/backup"


class SessionData(BaseModel):
    """会话数据 - 旧版格式，请使用 UnifiedSession 替代"""
    conversation_id: str
    user_id: str
    messages: List[Message] = Field(default_factory=list)
    bazi_cache: Optional[BaziCache] = None
    metadata: ConversationMetadata

    def add_message(self, role: MessageRole, content: str) -> None:
        """添加消息"""
        self.messages.append(Message(role=role, content=content))
        self.metadata.message_count = len(self.messages)
        self.metadata.updated_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.model_dump()


__all__ = [
    "MessageRole",
    "Message",
    "ConversationMetadata",
    "BaziCache",
    "StorageConfig",
    "SessionData"
]