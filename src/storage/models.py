# src/storage/models.py
"""存储层数据模型定义"""
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class MessageRole(str, Enum):
    """消息角色枚举"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class Message(BaseModel):
    """OpenAI 标准消息格式"""
    role: MessageRole
    content: str
    name: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    
    class Config:
        use_enum_values = True


class BaziCache(BaseModel):
    """八字缓存数据"""
    bazi_data: Dict[str, Any]
    analysis_result: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.now)
    user_query: Optional[str] = None
    response: Optional[str] = None


class ConversationMetadata(BaseModel):
    """对话元数据"""
    conversation_id: str
    user_id: str
    session_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    message_count: int = 0
    token_count: int = 0
    context_strategy: str = "FULL_CONTEXT"  # FULL_CONTEXT, SLIDING_WINDOW, HYBRID
    retrieval_mode: str = "hybrid_rerank"  # vector_only, bm25_only, hybrid, hybrid_rerank


class SessionData(BaseModel):
    """会话数据模型"""
    conversation_id: str
    user_id: str
    messages: List[Message] = Field(default_factory=list)
    bazi_cache: Optional[BaziCache] = None
    metadata: ConversationMetadata = Field(default_factory=ConversationMetadata)
    
    def add_message(self, role: MessageRole, content: str, **kwargs) -> None:
        """添加消息"""
        message = Message(role=role, content=content, **kwargs)
        self.messages.append(message)
        self.metadata.message_count += 1
    
    def get_openai_format(self) -> List[Dict[str, str]]:
        """转换为 OpenAI 标准格式"""
        return [
            {"role": msg.role.value, "content": msg.content}
            for msg in self.messages
        ]
    
    def get_alpaca_format(self) -> Dict[str, Any]:
        """转换为 Alpaca 格式"""
        # 提取 system prompt
        system_prompt = ""
        for msg in self.messages:
            if msg.role == MessageRole.SYSTEM:
                system_prompt = msg.content
                break
        
        # 提取对话历史
        conversations = []
        for msg in self.messages:
            if msg.role == MessageRole.USER:
                conversations.append({
                    "from": "human",
                    "value": msg.content
                })
            elif msg.role == MessageRole.ASSISTANT:
                conversations.append({
                    "from": "gpt",
                    "value": msg.content
                })
        
        return {
            "conversations": conversations,
            "system": system_prompt
        }


class StorageConfig(BaseModel):
    """存储配置"""
    storage_path: str = "data/memory"
    bm25_index_path: str = "data/bm25_index"
    max_conversations: int = 100
    max_messages_per_conversation: int = 100
    auto_save: bool = True
    compression: bool = True