"""
==============================================================================
Agentic RAG LangGraph 工作流
==============================================================================

功能说明：
    本模块定义了 Agentic RAG 的 LangGraph 工作流，使用状态机驱动的检索流程。

工作流节点：
    1. analyze_query - 查询分析
    2. plan_retrieval - 检索规划
    3. execute_retrieval - 检索执行
    4. evaluate_results - 结果评估
    5. reflect - 反思优化
    6. synthesize - 知识整合

==============================================================================
"""

import logging
from typing import Dict, Any, Literal

try:
    from langgraph.graph import StateGraph, END
    from langgraph.graph.state import CompiledStateGraph
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("langgraph 未安装，无法创建工作流")

from src.rag.agentic.state import AgenticRAGState, AgentState
from src.rag.agentic.nodes import (
    analyze_query_node,
    plan_retrieval_node,
    execute_retrieval_node,
    evaluate_results_node,
    reflect_node,
    synthesize_node,
    route_after_evaluation,
    route_after_reflection
)

logger = logging.getLogger(__name__)


def create_agentic_rag_graph() -> "CompiledStateGraph":
    """
    ==============================================================================
    创建 Agentic RAG 工作流图
    ==============================================================================
    
    功能说明：
        创建并编译 Agentic RAG 的 LangGraph 工作流。
    
    返回值：
        CompiledStateGraph: 编译后的状态图
    
    工作流流程：
        1. analyze_query - 查询分析
        2. plan_retrieval - 检索规划
        3. execute_retrieval - 检索执行
        4. evaluate_results - 结果评估
        5. reflect - 反思优化（条件执行）
        6. synthesize - 知识整合
    
    路由逻辑：
        - 评估后：根据分数决定是否继续反思
        - 反思后：根据迭代次数决定是否重试
    
    ==============================================================================
    """
    if not LANGGRAPH_AVAILABLE:
        logger.error("langgraph 未安装")
        raise ImportError("请安装 langgraph: pip install langgraph")
    
    logger.info("开始创建 Agentic RAG 工作流...")
    
    # 创建工作流
    workflow = StateGraph(AgenticRAGState)
    
    # 添加节点
    workflow.add_node("analyze_query", analyze_query_node)
    workflow.add_node("plan_retrieval", plan_retrieval_node)
    workflow.add_node("execute_retrieval", execute_retrieval_node)
    workflow.add_node("evaluate_results", evaluate_results_node)
    workflow.add_node("reflect", reflect_node)
    workflow.add_node("synthesize", synthesize_node)
    
    # 设置入口
    workflow.set_entry_point("analyze_query")
    
    # 添加边
    workflow.add_edge("analyze_query", "plan_retrieval")
    workflow.add_edge("plan_retrieval", "execute_retrieval")
    workflow.add_edge("execute_retrieval", "evaluate_results")
    
    # 条件边：评估后
    workflow.add_conditional_edges(
        "evaluate_results",
        route_after_evaluation,
        {
            "continue": "reflect",
            "finish": "synthesize"
        }
    )
    
    # 条件边：反思后
    workflow.add_conditional_edges(
        "reflect",
        route_after_reflection,
        {
            "retry": "execute_retrieval",  # 重试时从检索开始
            "finish": "synthesize"
        }
    )
    
    workflow.add_edge("synthesize", END)
    
    # 编译工作流
    app = workflow.compile()
    
    logger.info("Agentic RAG 工作流创建完成")
    
    return app


def run_agentic_rag(
    query: str,
    graph: "CompiledStateGraph" = None,
    max_iterations: int = 3,
    conversation_context: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    ==============================================================================
    运行 Agentic RAG
    ==============================================================================
    
    功能说明：
        运行 Agentic RAG 工作流，返回检索结果。
    
    参数说明：
        query: 用户查询文本
        graph: 工作流图（可选）
        max_iterations: 最大迭代次数
        conversation_context: 对话上下文（可选）
    
    返回值：
        Dict[str, Any]: 检索结果
    
    ==============================================================================
    """
    if not LANGGRAPH_AVAILABLE:
        logger.error("langgraph 未安装")
        raise ImportError("请安装 langgraph: pip install langgraph")
    
    # 创建或使用传入的工作流
    if graph is None:
        graph = create_agentic_rag_graph()
    
    # 构建初始状态
    state: AgenticRAGState = {
        "original_query": query,
        "current_query": query,
        "max_iterations": max_iterations,
        "iteration": 0,
        "current_action": "analyze",
        "state": AgentState.INITIALIZED,
        "reasoning_trace": [f"开始查询: {query}"]
    }
    
    if conversation_context:
        state["conversation_context"] = conversation_context
    
    try:
        # 运行工作流
        result = graph.invoke(state)
        
        logger.info(f"Agentic RAG 完成，状态: {result.get('state')}")
        
        return result
        
    except Exception as e:
        logger.error(f"Agentic RAG 运行失败: {e}")
        return {
            "error": str(e),
            "state": AgentState.FAILED
        }


def run_agentic_rag_stream(
    query: str,
    graph: "CompiledStateGraph" = None,
    max_iterations: int = 3
):
    """
    ==============================================================================
    流式运行 Agentic RAG
    ==============================================================================
    
    功能说明：
        流式运行 Agentic RAG 工作流，实时返回中间结果。
    
    参数说明：
        query: 用户查询文本
        graph: 工作流图（可选）
        max_iterations: 最大迭代次数
    
    返回值：
        Generator[Dict[str, Any], None, None]: 中间结果流
    
    ==============================================================================
    """
    if not LANGGRAPH_AVAILABLE:
        logger.error("langgraph 未安装")
        raise ImportError("请安装 langgraph: pip install langgraph")
    
    # 创建或使用传入的工作流
    if graph is None:
        graph = create_agentic_rag_graph()
    
    # 构建初始状态
    state: AgenticRAGState = {
        "original_query": query,
        "current_query": query,
        "max_iterations": max_iterations,
        "iteration": 0,
        "current_action": "analyze",
        "state": AgentState.INITIALIZED,
        "reasoning_trace": [f"开始查询: {query}"]
    }
    
    try:
        # 流式运行工作流
        for output in graph.stream(state):
            yield output
        
    except Exception as e:
        logger.error(f"Agentic RAG 流式运行失败: {e}")
        yield {
            "error": str(e),
            "state": AgentState.FAILED
        }
