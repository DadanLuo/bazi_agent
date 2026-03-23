# src/core/contracts.py
"""
统一数据契约 — 项目唯一的数据模型定义
替代 storage/models.py 的 SessionData + graph/state.py 的 BaziAgentState 双重表示
"""
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class MessageRole(str, Enum):
    """消息角色"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ContextStrategy(str, Enum):
    """上下文策略"""
    FULL_CONTEXT = "FULL_CONTEXT"
    SLIDING_WINDOW = "SLIDING_WINDOW"
    HYBRID = "HYBRID"


class RetrievalMode(str, Enum):
    """检索模式"""
    VECTOR_ONLY = "vector_only"
    BM25_ONLY = "bm25_only"
    HYBRID = "hybrid"
    HYBRID_RERANK = "hybrid_rerank"


class IntentType(str, Enum):
    """意图类型"""
    NEW_ANALYSIS = "NEW_ANALYSIS"
    FOLLOW_UP = "FOLLOW_UP"
    TOPIC_SWITCH = "TOPIC_SWITCH"
    CLARIFICATION = "CLARIFICATION"
    GENERAL_QUERY = "GENERAL_QUERY"


class ChatMessage(BaseModel):
    """统一消息格式 — 替代 Message + Dict[str, str] 双格式"""
    role: MessageRole
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)
    name: Optional[str] = None

    class Config:
        use_enum_values = True

    def to_openai(self) -> Dict[str, str]:
        return {"role": self.role if isinstance(self.role, str) else self.role.value, "content": self.content}


class BaziCacheData(BaseModel):
    """八字缓存 — 全字段保留，无序列化丢失"""
    bazi_data: Dict[str, Any]
    analysis_result: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)
    user_query: Optional[str] = None
    response: Optional[str] = None
    llm_response: Optional[str] = None


class TarotCacheData(BaseModel):
    """塔罗缓存 — 保存抽牌结果和解读"""
    drawn_cards: List[Dict[str, Any]] = Field(default_factory=list)
    spread_info: Dict[str, Any] = Field(default_factory=dict)
    synthesis: str = ""
    timestamp: datetime = Field(default_factory=datetime.now)
    user_query: Optional[str] = None
    llm_response: Optional[str] = None


class SessionMetadata(BaseModel):
    """会话元数据"""
    conversation_id: str
    user_id: str
    session_id: Optional[str] = None
    agent_id: str = "bazi"
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    message_count: int = 0
    token_count: int = 0
    context_strategy: str = "FULL_CONTEXT"
    retrieval_mode: str = "hybrid_rerank"
    slots: Dict[str, Any] = Field(default_factory=dict)


# LangGraph 需要的分析中间结果 key 列表
ANALYSIS_STATE_KEYS = [
    "bazi_result", "wuxing_analysis", "geju_analysis",
    "yongshen_analysis", "liunian_analysis", "dayun_analysis",
    "knowledge_context", "retrieved_docs", "rag_queries",
    "llm_response", "final_report", "safe_output",
]

TAROT_ANALYSIS_STATE_KEYS = [
    "drawn_cards", "spread_id", "spread_info",
    "card_interpretations", "synthesis",
    "knowledge_context", "retrieved_docs",
    "llm_response", "tarot_result", "safe_output",
]


class UnifiedSession(BaseModel):
    """
    统一会话模型 — 替代 SessionData + BaziAgentState 双重表示
    - 持久化用 Pydantic（Redis / 文件）
    - LangGraph 用 to_graph_state() 生成 TypedDict 视图
    """
    metadata: SessionMetadata
    messages: List[ChatMessage] = Field(default_factory=list)
    bazi_cache: Optional[BaziCacheData] = None
    tarot_cache: Optional[TarotCacheData] = None
    analysis_state: Dict[str, Any] = Field(default_factory=dict)

    # ---- 消息操作 ----

    def add_message(self, role: str, content: str) -> None:
        role_enum = MessageRole(role) if isinstance(role, str) else role
        self.messages.append(ChatMessage(role=role_enum, content=content))
        self.metadata.message_count = len(self.messages)
        from src.core.tokenizer import estimate_tokens
        self.metadata.token_count += estimate_tokens(content)
        self.metadata.updated_at = datetime.now()

    def get_openai_format(self) -> List[Dict[str, str]]:
        return [m.to_openai() for m in self.messages]

    def get_alpaca_format(self) -> Dict[str, Any]:
        system_prompt = ""
        conversations = []
        for m in self.messages:
            role = m.role if isinstance(m.role, str) else m.role.value
            if role == "system":
                system_prompt = m.content
            elif role == "user":
                conversations.append({"from": "human", "value": m.content})
            elif role == "assistant":
                conversations.append({"from": "gpt", "value": m.content})
        return {"conversations": conversations, "system": system_prompt}

    # ---- LangGraph 互操作 ----

    def to_graph_state(self) -> Dict[str, Any]:
        """生成 BaziAgentState 兼容的 dict，供 LangGraph 使用"""
        state: Dict[str, Any] = {
            "conversation_id": self.metadata.conversation_id,
            "user_id": self.metadata.user_id,
            "session_id": self.metadata.session_id,
            "messages": self.get_openai_format(),
            "message_count": self.metadata.message_count,
            "token_count": self.metadata.token_count,
            "context_strategy": self.metadata.context_strategy,
            "retrieval_mode": self.metadata.retrieval_mode,
            "intent_slots": self.metadata.slots,
            "created_at": self.metadata.created_at.isoformat(),
            "updated_at": self.metadata.updated_at.isoformat(),
            "status": "loaded",
        }
        if self.bazi_cache:
            state["bazi_cache"] = self.bazi_cache.model_dump(mode="json")
        state.update(self.analysis_state)
        return state

    def absorb_graph_result(self, graph_output: Dict[str, Any]) -> None:
        """从 LangGraph 输出合并回 session — 无数据丢失"""
        # 八字分析结果
        for key in ANALYSIS_STATE_KEYS:
            if key in graph_output:
                self.analysis_state[key] = graph_output[key]

        if graph_output.get("bazi_result"):
            self.bazi_cache = BaziCacheData(
                bazi_data=graph_output["bazi_result"],
                analysis_result=graph_output.get("final_report", {}),
                llm_response=graph_output.get("llm_response"),
            )

        # 塔罗分析结果
        for key in TAROT_ANALYSIS_STATE_KEYS:
            if key in graph_output:
                self.analysis_state[key] = graph_output[key]

        if graph_output.get("drawn_cards"):
            self.tarot_cache = TarotCacheData(
                drawn_cards=graph_output["drawn_cards"],
                spread_info=graph_output.get("spread_info", {}),
                synthesis=graph_output.get("synthesis", ""),
                llm_response=graph_output.get("llm_response"),
            )

        self.metadata.updated_at = datetime.now()


class ApiResponse(BaseModel):
    """统一 API 响应信封 — 替代 BaziResponse / ChatResponse / 裸 dict"""
    success: bool
    message: str
    data: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    trace_id: Optional[str] = None
