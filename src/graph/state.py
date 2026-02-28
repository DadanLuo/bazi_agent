"""
LangGraph 状态定义
使用 TypedDict 而非 Pydantic BaseModel
"""
from typing import Dict, Any, Optional, TypedDict
from typing import Dict, Any, Optional, TypedDict, List


class BaziAgentState(TypedDict, total=False):
    """
    LangGraph 状态定义
    total=False 表示所有字段都是可选的
    """
    user_input: Dict[str, Any]  # 用户输入的原始数据
    validated_input: Optional[Dict[str, Any]]  # 验证后的输入
    bazi_result: Optional[Dict[str, Any]]  # 排盘结果
    wuxing_analysis: Optional[Dict[str, Any]]  # 五行分析
    geju_analysis: Optional[Dict[str, Any]]  # 格局分析
    yongshen_analysis: Optional[Dict[str, Any]]  # 喜用神分析
    liunian_analysis: Optional[Dict[str, Any]]  # 流年分析

    # ✨ 新增字段
    knowledge_context: Optional[str]  # RAG检索到的知识上下文
    retrieved_docs: Optional[List[Dict]]  # 检索到的文档列表
    llm_response: Optional[str]  # LLM生成的回复

    final_report: Optional[Dict[str, Any]]  # 最终报告
    safe_output: Optional[Dict[str, Any]]  # 安全输出
    error: Optional[str]  # 错误信息
    status: str  # 当前状态
    messages: list  # 对话历史