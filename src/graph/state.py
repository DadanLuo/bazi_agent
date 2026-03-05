# src/graph/state.py
"""
LangGraph 状态定义 - 多轮对话增强版
使用 TypedDict 而非 Pydantic BaseModel
"""
from typing import Dict, Any, Optional, TypedDict, List
from enum import Enum


class ContextStrategy(str, Enum):
    """上下文策略枚举"""
    FULL_CONTEXT = "FULL_CONTEXT"  # 全量上下文
    SLIDING_WINDOW = "SLIDING_WINDOW"  # 滑动窗口
    HYBRID = "HYBRID"  # 混合策略


class RetrievalMode(str, Enum):
    """检索模式枚举"""
    VECTOR_ONLY = "vector_only"  # 仅向量检索
    BM25_ONLY = "bm25_only"  # 仅BM25检索
    HYBRID = "hybrid"  # 混合检索
    HYBRID_RERANK = "hybrid_rerank"  # 混合检索+重排序


class IntentType(str, Enum):
    """意图类型枚举"""
    NEW_ANALYSIS = "NEW_ANALYSIS"  # 新分析请求
    FOLLOW_UP = "FOLLOW_UP"  # 后续追问
    TOPIC_SWITCH = "TOPIC_SWITCH"  # 话题切换
    CLARIFICATION = "CLARIFICATION"  # 澄清请求
    GENERAL_QUERY = "GENERAL_QUERY"  # 通用查询


class BaziAgentState(TypedDict, total=False):
    """
    LangGraph 状态定义
    total=False 表示所有字段都是可选的
    """
    # ========== 基础输入 ==========
    user_input: Dict[str, Any]  # 用户输入的原始数据
    validated_input: Optional[Dict[str, Any]]  # 验证后的输入
    
    # ========== 八字分析结果 ==========
    bazi_result: Optional[Dict[str, Any]]  # 排盘结果
    wuxing_analysis: Optional[Dict[str, Any]]  # 五行分析
    geju_analysis: Optional[Dict[str, Any]]  # 格局分析
    yongshen_analysis: Optional[Dict[str, Any]]  # 喜用神分析
    liunian_analysis: Optional[Dict[str, Any]]  # 流年分析
    
    # ========== 大运分析 ==========
    dayun_analysis: Optional[Dict[str, Any]]  # 大运分析结果
    
    # ========== RAG检索 ==========
    knowledge_context: Optional[str]  # RAG检索到的知识上下文
    retrieved_docs: Optional[List[Dict]]  # 检索到的文档列表
    llm_response: Optional[str]  # LLM生成的回复
    
    # ========== 最终输出 ==========
    final_report: Optional[Dict[str, Any]]  # 最终报告
    safe_output: Optional[Dict[str, Any]]  # 安全输出
    error: Optional[str]  # 错误信息
    status: str  # 当前状态
    
    # ========== 多轮对话支持 ==========
    # 会话标识
    session_id: Optional[str]  # 会话ID
    conversation_id: Optional[str]  # 对话ID
    user_id: Optional[str]  # 用户ID
    
    # 消息历史（OpenAI 标准格式）
    messages: List[Dict[str, str]]  # 对话历史
    
    # 意图识别结果
    intent: Optional[str]  # 检测到的意图
    intent_confidence: Optional[float]  # 意图置信度
    intent_slots: Optional[Dict[str, Any]]  # 槽位信息
    
    # 上下文策略
    context_strategy: Optional[str]  # 上下文策略
    retrieval_mode: Optional[str]  # 检索模式
    
    # 上下文信息
    context_text: Optional[str]  # 构建的上下文文本
    context_token_count: Optional[int]  # 上下文token数
    
    # 检索结果
    retrieval_results: Optional[List[Dict]]  # 检索结果列表
    reranked_results: Optional[List[Dict]]  # 重排序结果
    
    # 八字缓存
    bazi_cache: Optional[Dict[str, Any]]  # 八字缓存数据
    
    # 对话元数据
    message_count: Optional[int]  # 消息数量
    token_count: Optional[int]  # token数量
    created_at: Optional[str]  # 创建时间
    updated_at: Optional[str]  # 更新时间
    
    # 流程控制
    next_node: Optional[str]  # 下一个节点
    route_decision: Optional[str]  # 路由决策
    
    # 额外信息
    extra_info: Optional[Dict[str, Any]]  # 额外信息
    metadata: Optional[Dict[str, Any]]  # 元数据


# 状态辅助函数
def create_initial_state(
    user_id: str = "default",
    session_id: Optional[str] = None,
    context_strategy: str = "FULL_CONTEXT",
    retrieval_mode: str = "hybrid_rerank"
) -> BaziAgentState:
    """创建初始状态"""
    return BaziAgentState(
        user_id=user_id,
        session_id=session_id,
        context_strategy=context_strategy,
        retrieval_mode=retrieval_mode,
        messages=[],
        message_count=0,
        token_count=0,
        created_at="",
        updated_at="",
        status="initialized"
    )


def update_state_with_message(
    state: BaziAgentState,
    role: str,
    content: str
) -> BaziAgentState:
    """更新状态，添加消息"""
    if "messages" not in state:
        state["messages"] = []
    
    state["messages"].append({"role": role, "content": content})
    
    if "message_count" not in state:
        state["message_count"] = 0
    state["message_count"] = state["message_count"] + 1
    
    if "token_count" not in state:
        state["token_count"] = 0
    
    # 简单估算token数量
    state["token_count"] = state["token_count"] + len(content) // 3
    
    return state


def get_current_messages(state: BaziAgentState) -> List[Dict[str, str]]:
    """获取当前消息列表"""
    return state.get("messages", [])


def get_last_user_message(state: BaziAgentState) -> Optional[str]:
    """获取最后一条用户消息"""
    messages = state.get("messages", [])
    for msg in reversed(messages):
        if msg.get("role") == "user":
            return msg.get("content")
    return None


def get_last_assistant_message(state: BaziAgentState) -> Optional[str]:
    """获取最后一条助手消息"""
    messages = state.get("messages", [])
    for msg in reversed(messages):
        if msg.get("role") == "assistant":
            return msg.get("content")
    return None
