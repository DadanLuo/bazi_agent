"""
==============================================================================
八字分析 LangGraph 主图定义
==============================================================================

功能说明：
    本模块定义了八字分析的 LangGraph 工作流，通过状态图（StateGraph）组织
    八字分析的各个步骤节点，实现完整的八字排盘、分析、报告生成流程。

工作流节点：
    1. validate_input - 输入验证节点
    2. calculate_bazi - 八字排盘节点
    3. analyze_wuxing - 五行分析节点
    4. determine_geju - 格局判断节点
    5. find_yongshen - 喜用神查找节点
    6. check_liunian - 流年分析节点
    7. retrieve_knowledge - 知识检索节点
    8. llm_generate - LLM 生成节点
    9. generate_report - 报告生成节点
    10. safety_check - 安全检查节点

执行流程：
    validate_input → calculate_bazi → analyze_wuxing → determine_geju
        → find_yongshen → check_liunian → retrieve_knowledge
        → llm_generate → generate_report → safety_check → END

安全机制：
    每个节点失败后都会跳转到 safety_check 节点，确保异常情况下的安全处理。

==============================================================================
"""

import logging
from typing import Literal
from langgraph.graph import StateGraph, END
from .state import BaziAgentState
from .nodes import (
    validate_input_node, calculate_bazi_node, analyze_wuxing_node,
    determine_geju_node, find_yongshen_node, check_liunian_node,
    # ✨ 新增节点导入
    retrieve_knowledge_node, llm_generate_node,
    generate_report_node, safety_check_node,
    agentic_rag_node
)
from src.safety.safety import SafetyChecker, SafetyLevel

logger = logging.getLogger(__name__)

# 全局安全检查器 - 在模块加载时初始化
_safety_checker = None
try:
    _safety_checker = SafetyChecker()
except Exception as e:
    logger.warning(f"⚠️ 安全检查器初始化失败: {e}")


def route_after_validation(state: BaziAgentState) -> Literal["calculate_bazi", "safety_check"]:
    """
    ==============================================================================
    验证后路由 - 根据输入验证结果决定下一步
    ==============================================================================
    
    功能说明：
        在输入验证节点执行后，根据验证结果决定下一步执行的节点。
        验证成功则进入八字排盘，验证失败则进入安全检查节点。
    
    参数说明：
        state (BaziAgentState): 当前工作流状态
    
    返回值：
        Literal["calculate_bazi", "safety_check"]: 下一步执行的节点名称
    
    路由逻辑：
        - status == "input_validation_failed" → "safety_check"
        - 其他情况 → "calculate_bazi"
    
    ==============================================================================
    """
    if state.get("status") == "input_validation_failed":
        logger.warning("输入验证失败，跳转至安全节点")
        return "safety_check"
    return "calculate_bazi"


def route_after_calculation(state: BaziAgentState) -> Literal["analyze_wuxing", "safety_check"]:
    """
    ==============================================================================
    排盘后路由 - 根据排盘结果决定下一步
    ==============================================================================
    
    功能说明：
        在八字排盘节点执行后，根据排盘结果决定下一步执行的节点。
        排盘成功则进入五行分析，排盘失败则进入安全检查节点。
    
    参数说明：
        state (BaziAgentState): 当前工作流状态
    
    返回值：
        Literal["analyze_wuxing", "safety_check"]: 下一步执行的节点名称
    
    路由逻辑：
        - status == "calculation_failed" → "safety_check"
        - 其他情况 → "analyze_wuxing"
    
    ==============================================================================
    """
    if state.get("status") == "calculation_failed":
        logger.warning("排盘计算失败，跳转至安全节点")
        return "safety_check"
    return "analyze_wuxing"


def route_after_analysis(state: BaziAgentState) -> Literal["determine_geju", "safety_check"]:
    """
    ==============================================================================
    五行分析后路由 - 根据五行分析结果决定下一步
    ==============================================================================
    
    功能说明：
        在五行分析节点执行后，根据分析结果决定下一步执行的节点。
        分析成功则进入格局判断，分析失败则进入安全检查节点。
    
    参数说明：
        state (BaziAgentState): 当前工作流状态
    
    返回值：
        Literal["determine_geju", "safety_check"]: 下一步执行的节点名称
    
    路由逻辑：
        - status 以 "_failed" 结尾 → "safety_check"
        - 其他情况 → "determine_geju"
    
    ==============================================================================
    """
    if state.get("status", "").endswith("_failed"):
        logger.warning("分析过程失败，跳转至安全节点")
        return "safety_check"
    return "determine_geju"


def route_after_geju(state: BaziAgentState) -> Literal["find_yongshen", "safety_check"]:
    """
    ==============================================================================
    格局判断后路由 - 根据格局判断结果决定下一步
    ==============================================================================
    
    功能说明：
        在格局判断节点执行后，根据判断结果决定下一步执行的节点。
        判断成功则进入喜用神查找，判断失败则进入安全检查节点。
    
    参数说明：
        state (BaziAgentState): 当前工作流状态
    
    返回值：
        Literal["find_yongshen", "safety_check"]: 下一步执行的节点名称
    
    路由逻辑：
        - status 以 "_failed" 结尾 → "safety_check"
        - 其他情况 → "find_yongshen"
    
    ==============================================================================
    """
    if state.get("status", "").endswith("_failed"):
        logger.warning("格局判断失败，跳转至安全节点")
        return "safety_check"
    return "find_yongshen"


def route_after_yongshen(state: BaziAgentState) -> Literal["check_liunian", "safety_check"]:
    """
    ==============================================================================
    喜用神查找后路由 - 根据查找结果决定下一步
    ==============================================================================
    
    功能说明：
        在喜用神查找节点执行后，根据查找结果决定下一步执行的节点。
        查找成功则进入流年分析，查找失败则进入安全检查节点。
    
    参数说明：
        state (BaziAgentState): 当前工作流状态
    
    返回值：
        Literal["check_liunian", "safety_check"]: 下一步执行的节点名称
    
    路由逻辑：
        - status 以 "_failed" 结尾 → "safety_check"
        - 其他情况 → "check_liunian"
    
    ==============================================================================
    """
    if state.get("status", "").endswith("_failed"):
        logger.warning("喜用神查找失败，跳转至安全节点")
        return "safety_check"
    return "check_liunian"


# ✨ 新增路由：流年分析后进入知识检索
def route_after_liunian(state: BaziAgentState) -> Literal["retrieve_knowledge", "safety_check"]:
    """
    ==============================================================================
    流年分析后路由 - 根据流年分析结果决定下一步
    ==============================================================================
    
    功能说明：
        在流年分析节点执行后，根据分析结果决定下一步执行的节点。
        分析成功则进入知识检索，分析失败则进入安全检查节点。
    
    参数说明：
        state (BaziAgentState): 当前工作流状态
    
    返回值：
        Literal["retrieve_knowledge", "safety_check"]: 下一步执行的节点名称
    
    路由逻辑：
        - status 以 "_failed" 结尾 → "safety_check"
        - 其他情况 → "retrieve_knowledge"
    
    ==============================================================================
    """
    if state.get("status", "").endswith("_failed"):
        logger.warning("流年分析失败，跳转至安全节点")
        return "safety_check"
    return "retrieve_knowledge"


# ✨ 新增路由：知识检索后进入LLM生成
def route_after_retrieval(state: BaziAgentState) -> Literal["llm_generate", "safety_check"]:
    """
    ==============================================================================
    知识检索后路由 - 根据检索结果决定下一步
    ==============================================================================
    
    功能说明：
        在知识检索节点执行后，根据检索结果决定下一步执行的节点。
        检索成功或跳过（skipped）则进入 LLM 生成，严重错误则进入安全检查节点。
    
    参数说明：
        state (BaziAgentState): 当前工作流状态
    
    返回值：
        Literal["llm_generate", "safety_check"]: 下一步执行的节点名称
    
    路由逻辑：
        - status == "knowledge_retrieval_failed" → "safety_check"
        - 其他情况（包括 skipped）→ "llm_generate"
    
    设计说明：
        即使检索失败（skipped），通常也希望能继续生成（使用默认提示词），
        除非发生严重错误。这样可以保证用户体验不中断。
    
    ==============================================================================
    """
    # 即使检索失败（skipped），通常也希望能继续生成（使用默认提示词），除非发生严重错误
    if state.get("status") == "knowledge_retrieval_failed":
        logger.warning("知识检索严重错误，跳转至安全节点")
        return "safety_check"
    return "llm_generate"


# ✨ 新增路由：LLM生成后进入报告组装
def route_after_llm(state: BaziAgentState) -> Literal["generate_report", "safety_check"]:
    """
    ==============================================================================
    LLM生成后路由 - 根据生成结果决定下一步
    ==============================================================================
    
    功能说明：
        在 LLM 生成节点执行后，根据生成结果决定下一步执行的节点。
        生成成功则进入报告生成，生成失败则进入安全检查节点。
    
    参数说明：
        state (BaziAgentState): 当前工作流状态
    
    返回值：
        Literal["generate_report", "safety_check"]: 下一步执行的节点名称
    
    路由逻辑：
        - status == "llm_generation_failed" → "safety_check"
        - 其他情况 → "generate_report"
    
    ==============================================================================
    """
    if state.get("status") == "llm_generation_failed":
        logger.warning("LLM生成失败，跳转至安全节点")
        return "safety_check"
    return "generate_report"


def route_after_report(state: BaziAgentState) -> Literal["safety_check", END]:
    """
    ==============================================================================
    报告生成后路由 - 报告生成完成后进入安全检查
    ==============================================================================
    
    功能说明：
        在报告生成节点执行后，进入安全检查节点进行最终的内容审核。
        安全检查通过后，工作流结束。
    
    参数说明：
        state (BaziAgentState): 当前工作流状态
    
    返回值：
        Literal["safety_check", END]: 下一步执行的节点名称
    
    路由逻辑：
        - 始终返回 "safety_check"
    
    ==============================================================================
    """
    return "safety_check"


def create_bazi_graph() -> StateGraph:
    """
    ==============================================================================
    创建八字分析 LangGraph
    ==============================================================================
    
    功能说明：
        构建八字分析的 LangGraph 工作流，定义所有节点和条件边。
        工作流按照八字分析的标准流程组织，确保每个步骤的正确执行。
    
    返回值：
        StateGraph: 构建完成的状态图对象
    
    工作流结构：
        1. validate_input (入口节点)
        2. calculate_bazi
        3. analyze_wuxing
        4. determine_geju
        5. find_yongshen
        6. check_liunian
        7. retrieve_knowledge
        8. llm_generate
        9. generate_report
        10. safety_check (终点)
    
    安全机制：
        每个节点失败后都会跳转到 safety_check 节点，确保异常情况下的安全处理。
    
    ==============================================================================
    """
    logger.info("正在构建 LangGraph...")

    # 初始化状态图
    workflow = StateGraph(BaziAgentState)

    # 添加所有节点
    workflow.add_node("validate_input", validate_input_node)
    workflow.add_node("calculate_bazi", calculate_bazi_node)
    workflow.add_node("analyze_wuxing", analyze_wuxing_node)
    workflow.add_node("determine_geju", determine_geju_node)
    workflow.add_node("find_yongshen", find_yongshen_node)
    workflow.add_node("check_liunian", check_liunian_node)

    # ✨ 添加新节点
    workflow.add_node("retrieve_knowledge", retrieve_knowledge_node)
    workflow.add_node("llm_generate", llm_generate_node)

    workflow.add_node("generate_report", generate_report_node)
    workflow.add_node("safety_check", safety_check_node)

    # 设置入口节点
    workflow.set_entry_point("validate_input")

    # 添加条件边 - 验证后路由
    workflow.add_conditional_edges(
        "validate_input",
        route_after_validation,
        {
            "calculate_bazi": "calculate_bazi",
            "safety_check": "safety_check"
        }
    )

    # 添加条件边 - 排盘后路由
    workflow.add_conditional_edges(
        "calculate_bazi",
        route_after_calculation,
        {
            "analyze_wuxing": "analyze_wuxing",
            "safety_check": "safety_check"
        }
    )

    # 添加条件边 - 五行分析后路由
    workflow.add_conditional_edges(
        "analyze_wuxing",
        route_after_analysis,
        {
            "determine_geju": "determine_geju",
            "safety_check": "safety_check"
        }
    )

    # 添加条件边 - 格局判断后路由
    workflow.add_conditional_edges(
        "determine_geju",
        route_after_geju,
        {
            "find_yongshen": "find_yongshen",
            "safety_check": "safety_check"
        }
    )

    # 添加条件边 - 喜用神查找后路由
    workflow.add_conditional_edges(
        "find_yongshen",
        route_after_yongshen,
        {
            "check_liunian": "check_liunian",
            "safety_check": "safety_check"
        }
    )

    # ✨ 更新流年分析后的指向：指向 retrieve_knowledge
    workflow.add_conditional_edges(
        "check_liunian",
        route_after_liunian,
        {
            "retrieve_knowledge": "retrieve_knowledge",
            "safety_check": "safety_check"
        }
    )

    # ✨ 新增知识检索后的指向：指向 llm_generate
    workflow.add_conditional_edges(
        "retrieve_knowledge",
        route_after_retrieval,
        {
            "llm_generate": "llm_generate",
            "safety_check": "safety_check"
        }
    )

    # ✨ 新增LLM生成后的指向：指向 generate_report
    workflow.add_conditional_edges(
        "llm_generate",
        route_after_llm,
        {
            "generate_report": "generate_report",
            "safety_check": "safety_check"
        }
    )

    # 添加条件边 - 报告生成后路由
    workflow.add_conditional_edges(
        "generate_report",
        route_after_report,
        {
            "safety_check": "safety_check"
        }
    )

    # 安全节点指向结束
    workflow.add_edge("safety_check", END)

    logger.info("LangGraph 构建完成")
    return workflow


def check_user_input_safety(user_input: dict, user_query: str = "") -> dict:
    """
    ==============================================================================
    检查用户输入的安全性（在进入 graph 之前）
    ==============================================================================
    
    功能说明：
        在用户输入进入 LangGraph 之前进行安全检查，防止不安全的输入
        被处理。这是第一道安全防线，可以快速拒绝明显不安全的请求。
    
    参数说明：
        user_input (dict): 用户输入的原始数据
        user_query (str): 用户查询文本
    
    返回值：
        dict: 安全检查结果，包含：
            - blocked (bool): 是否被阻断
            - message (str): 阻断原因
            - category (str, 可选): 安全类别
    
    异常处理：
        如果安全检查器未初始化，返回允许通过的结果
    
    ==============================================================================
    """
    if not _safety_checker:
        return {"blocked": False, "message": ""}
    
    input_text = user_query or str(user_input)
    result = _safety_checker.check_input(input_text)
    
    if result.blocked:
        return {
            "blocked": True,
            "message": result.message,
            "category": result.category.value if result.category else None,
        }
    
    return {"blocked": False, "message": ""}


# 实例化图 - 在模块加载时创建并编译图
bazi_graph = create_bazi_graph()
app = bazi_graph.compile()
