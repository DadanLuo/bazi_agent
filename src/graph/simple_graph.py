"""
================================================================================
简化版八字分析图 - 不依赖 RAG 和 LLM
================================================================================

功能说明：
    本模块提供了一个简化版的八字分析工作流，仅执行核心计算节点，
    不包含 RAG 检索、LLM 生成和安全检查等依赖外部服务的节点。

使用场景：
    - 演示和测试核心八字计算功能
    - 在 LLM/RAG 服务不可用时提供降级方案
    - 快速验证八字排盘结果

调用方式：
    在 BaziAgent.handle_analysis() 中通过 mode="simple" 参数启用：
    - result = await simple_app.ainvoke(graph_input)

注意事项：
    - 不生成 AI 解读报告，仅返回排盘结果
    - 不进行安全检查，生产环境慎用
    - 输出格式与完整版不同，需注意兼容性

================================================================================
"""
import logging
from typing import Literal
from langgraph.graph import StateGraph, END
from src.graph.state import BaziAgentState
from src.graph.nodes import (
    validate_input_node, calculate_bazi_node, analyze_wuxing_node,
    determine_geju_node, find_yongshen_node, check_liunian_node
)

logger = logging.getLogger(__name__)


def route_after_validation(state: BaziAgentState) -> Literal["calculate_bazi", "end"]:
    """验证后路由"""
    if state.get("status") == "input_validation_failed":
        return "end"
    return "calculate_bazi"


def route_after_calculation(state: BaziAgentState) -> Literal["analyze_wuxing", "end"]:
    """排盘后路由"""
    if state.get("status") == "calculation_failed":
        return "end"
    return "analyze_wuxing"


def route_after_analysis(state: BaziAgentState) -> Literal["determine_geju", "end"]:
    """五行分析后路由"""
    if state.get("status", "").endswith("_failed"):
        return "end"
    return "determine_geju"


def route_after_geju(state: BaziAgentState) -> Literal["find_yongshen", "end"]:
    """格局判断后路由"""
    if state.get("status", "").endswith("_failed"):
        return "end"
    return "find_yongshen"


def route_after_yongshen(state: BaziAgentState) -> Literal["check_liunian", "end"]:
    """喜用神查找后路由"""
    if state.get("status", "").endswith("_failed"):
        return "end"
    return "check_liunian"


def route_after_liunian(state: BaziAgentState) -> Literal["generate_report", "end"]:
    """流年分析后路由"""
    if state.get("status", "").endswith("_failed"):
        return "end"
    return "generate_report"


def simple_report_node(state: BaziAgentState):
    """简化的报告生成节点"""
    logger.info("=" * 30)
    logger.info("【简化报告】组装基础数据...")

    report = {
        "basic_data": {
            "bazi": state.get("bazi_result", {}).get("four_pillars", {}),
            "wuxing": state.get("wuxing_analysis", {}),
            "geju": state.get("geju_analysis", {}),
            "yongshen": state.get("yongshen_analysis", {}),
            "liunian": state.get("liunian_analysis", {}),
            "dayun": state.get("dayun_analysis", {})
        },
        "time_info": state.get("bazi_result", {}).get("time_info", {}),
        "llm_analysis": "",
        "rag_info": {
            "status": "skipped",
            "reason": "快速分析模式未启用 RAG 检索",
            "queries": [],
            "documents": [],
            "doc_count": 0
        },
        "message": "八字分析完成（快速模式）"
    }

    logger.info("报告组装完成")
    return {
        "safe_output": report,
        "status": "completed"
    }


def create_simple_bazi_graph() -> StateGraph:
    """创建简化版八字分析图"""
    logger.info("正在构建简化版 LangGraph...")

    workflow = StateGraph(BaziAgentState)

    # 添加节点
    workflow.add_node("validate_input", validate_input_node)
    workflow.add_node("calculate_bazi", calculate_bazi_node)
    workflow.add_node("analyze_wuxing", analyze_wuxing_node)
    workflow.add_node("determine_geju", determine_geju_node)
    workflow.add_node("find_yongshen", find_yongshen_node)
    workflow.add_node("check_liunian", check_liunian_node)
    workflow.add_node("generate_report", simple_report_node)

    # 设置入口
    workflow.set_entry_point("validate_input")

    # 添加边
    workflow.add_conditional_edges(
        "validate_input",
        route_after_validation,
        {"calculate_bazi": "calculate_bazi", "end": END}
    )

    workflow.add_conditional_edges(
        "calculate_bazi",
        route_after_calculation,
        {"analyze_wuxing": "analyze_wuxing", "end": END}
    )

    workflow.add_conditional_edges(
        "analyze_wuxing",
        route_after_analysis,
        {"determine_geju": "determine_geju", "end": END}
    )

    workflow.add_conditional_edges(
        "determine_geju",
        route_after_geju,
        {"find_yongshen": "find_yongshen", "end": END}
    )

    workflow.add_conditional_edges(
        "find_yongshen",
        route_after_yongshen,
        {"check_liunian": "check_liunian", "end": END}
    )

    workflow.add_conditional_edges(
        "check_liunian",
        route_after_liunian,
        {"generate_report": "generate_report", "end": END}
    )

    workflow.add_edge("generate_report", END)

    logger.info("简化版 LangGraph 构建完成")
    return workflow


# 实例化简化版图
simple_bazi_graph = create_simple_bazi_graph()
simple_app = simple_bazi_graph.compile()
