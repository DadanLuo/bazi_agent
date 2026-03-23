# src/graph/tarot_state.py
"""塔罗牌 ReAct Agent 状态定义"""
from typing import Dict, Any, Optional, TypedDict, List


class TarotAgentState(TypedDict, total=False):
    """塔罗牌 ReAct Agent 状态"""

    # ========== 输入 ==========
    user_input: Dict[str, Any]       # {question_type, spread_type?, specific_question?}
    user_query: str                  # 用户原始问题文本

    # ========== ReAct Loop ==========
    messages: List[Dict[str, Any]]   # 完整消息历史（含 tool calls/results）
    pending_tool_calls: List[Dict]   # 待执行的 tool calls
    executor_state: Dict[str, Any]   # TarotToolExecutor 序列化状态
    iteration: int                   # 当前迭代次数

    # ========== 牌阵 & 抽牌（从 executor 同步）==========
    spread_id: str
    spread_info: Dict[str, Any]
    drawn_cards: List[Dict[str, Any]]

    # ========== LLM 输出 ==========
    llm_response: str                # 最终给用户的回复

    # ========== RAG 占位 ==========
    knowledge_context: Optional[str]
    retrieved_docs: Optional[List[Dict]]

    # ========== 输出 ==========
    tarot_result: Optional[Dict[str, Any]]
    safe_output: Optional[Dict[str, Any]]
    error: Optional[str]
    status: str

    # ========== 会话标识 ==========
    conversation_id: Optional[str]
    user_id: Optional[str]
