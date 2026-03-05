"""
八字分析 LangGraph 主图定义
定义节点连接和条件转移
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
    generate_report_node, safety_check_node
)

logger = logging.getLogger(__name__)


def route_after_validation(state: BaziAgentState) -> Literal["calculate_bazi", "safety_check"]:
    """验证后路由"""
    if state.get("status") == "input_validation_failed":
        logger.warning("输入验证失败，跳转至安全节点")
        return "safety_check"
    return "calculate_bazi"


def route_after_calculation(state: BaziAgentState) -> Literal["analyze_wuxing", "safety_check"]:
    """排盘后路由"""
    if state.get("status") == "calculation_failed":
        logger.warning("排盘计算失败，跳转至安全节点")
        return "safety_check"
    return "analyze_wuxing"


def route_after_analysis(state: BaziAgentState) -> Literal["determine_geju", "safety_check"]:
    """五行分析后路由"""
    if state.get("status", "").endswith("_failed"):
        logger.warning("分析过程失败，跳转至安全节点")
        return "safety_check"
    return "determine_geju"


def route_after_geju(state: BaziAgentState) -> Literal["find_yongshen", "safety_check"]:
    """格局判断后路由"""
    if state.get("status", "").endswith("_failed"):
        logger.warning("格局判断失败，跳转至安全节点")
        return "safety_check"
    return "find_yongshen"


def route_after_yongshen(state: BaziAgentState) -> Literal["check_liunian", "safety_check"]:
    """喜用神查找后路由"""
    if state.get("status", "").endswith("_failed"):
        logger.warning("喜用神查找失败，跳转至安全节点")
        return "safety_check"
    return "check_liunian"


# ✨ 新增路由：流年分析后进入知识检索
def route_after_liunian(state: BaziAgentState) -> Literal["retrieve_knowledge", "safety_check"]:
    """流年分析后路由"""
    if state.get("status", "").endswith("_failed"):
        logger.warning("流年分析失败，跳转至安全节点")
        return "safety_check"
    return "retrieve_knowledge"


# ✨ 新增路由：知识检索后进入LLM生成
def route_after_retrieval(state: BaziAgentState) -> Literal["llm_generate", "safety_check"]:
    """知识检索后路由"""
    # 即使检索失败（skipped），通常也希望能继续生成（使用默认提示词），除非发生严重错误
    if state.get("status") == "knowledge_retrieval_failed":
        logger.warning("知识检索严重错误，跳转至安全节点")
        return "safety_check"
    return "llm_generate"


# ✨ 新增路由：LLM生成后进入报告组装
def route_after_llm(state: BaziAgentState) -> Literal["generate_report", "safety_check"]:
    """LLM生成后路由"""
    if state.get("status") == "llm_generation_failed":
        logger.warning("LLM生成失败，跳转至安全节点")
        return "safety_check"
    return "generate_report"


def route_after_report(state: BaziAgentState) -> Literal["safety_check", END]:
    """报告生成后路由"""
    return "safety_check"


def create_bazi_graph() -> StateGraph:
    """创建八字分析 LangGraph"""
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
    workflow.add_node("analyze_dayun", analyze_dayun_node)

    # ✨ 添加新节点
    workflow.add_node("retrieve_knowledge", retrieve_knowledge_node)
    workflow.add_node("llm_generate", llm_generate_node)

    workflow.add_node("generate_report", generate_report_node)
    workflow.add_node("safety_check", safety_check_node)

    # 设置入口节点
    workflow.set_entry_point("validate_input")

    # 添加条件边
    workflow.add_conditional_edges(
        "validate_input",
        route_after_validation,
        {
            "calculate_bazi": "calculate_bazi",
            "safety_check": "safety_check"
        }
    )

    workflow.add_conditional_edges(
        "calculate_bazi",
        route_after_calculation,
        {
            "analyze_wuxing": "analyze_wuxing",
            "safety_check": "safety_check"
        }
    )

    workflow.add_conditional_edges(
        "analyze_wuxing",
        route_after_analysis,
        {
            "determine_geju": "determine_geju",
            "safety_check": "safety_check"
        }
    )

    workflow.add_conditional_edges(
        "determine_geju",
        route_after_geju,
        {
            "find_yongshen": "find_yongshen",
            "safety_check": "safety_check"
        }
    )

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

    def route_after_liunian(state: BaziAgentState) -> Literal["analyze_dayun", "safety_check"]:
        """流年分析后路由"""
        if state.get("status", "").endswith("_failed"):
            logger.warning("流年分析失败，跳转至安全节点")
            return "safety_check"
        return "analyze_dayun"

    # 添加条件边
    workflow.add_conditional_edges(
        "check_liunian",
        route_after_liunian,
        {
            "analyze_dayun": "analyze_dayun",
            "safety_check": "safety_check"
        }
    )

    # 大运分析后进入知识检索
    workflow.add_conditional_edges(
        "analyze_dayun",
        route_after_retrieval,  # 复用之前的路由函数
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


# 实例化图
bazi_graph = create_bazi_graph()
app = bazi_graph.compile()
