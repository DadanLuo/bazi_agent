"""
==============================================================================
Agentic RAG 工作流节点
==============================================================================

功能说明：
    本模块定义了 Agentic RAG LangGraph 工作流的所有节点，每个节点负责
    检索流程中的一个特定步骤。

工作流节点：
    1. analyze_query_node - 查询分析节点
    2. plan_retrieval_node - 检索规划节点
    3. execute_retrieval_node - 检索执行节点
    4. evaluate_results_node - 结果评估节点
    5. reflect_node - 反思节点
    6. synthesize_node - 知识整合节点

==============================================================================
"""

import logging
from typing import Dict, Any, Literal, Optional

from src.rag.agentic.state import (
    AgenticRAGState,
    AgentState,
    QueryAnalysis,
    RetrievalPlan,
    Document,
    ConversationContext
)
from src.rag.agentic.analyzer import QueryAnalyzer
from src.rag.agentic.planner import RetrievalPlanner
from src.rag.agentic.evaluator import ResultEvaluator
from src.rag.agentic.reflection import ReflectionEngine
from src.rag.agentic.synthesizer import KnowledgeSynthesizer
from src.rag.agentic.completer import QueryCompleter
from src.rag.retriever import KnowledgeRetriever

logger = logging.getLogger(__name__)


# 初始化核心组件
try:
    query_analyzer = QueryAnalyzer()
    retrieval_planner = RetrievalPlanner()
    result_evaluator = ResultEvaluator()
    reflection_engine = ReflectionEngine()
    knowledge_synthesizer = KnowledgeSynthesizer()
    query_completer = QueryCompleter()
    knowledge_retriever = KnowledgeRetriever()
except Exception as e:
    logger.warning(f"Agentic RAG 组件初始化失败: {e}")
    query_analyzer = None
    retrieval_planner = None
    result_evaluator = None
    reflection_engine = None
    knowledge_synthesizer = None
    query_completer = None
    knowledge_retriever = None


def analyze_query_node(state: AgenticRAGState) -> Dict[str, Any]:
    """
    ==============================================================================
    节点 1：查询分析
    ==============================================================================
    
    功能说明：
        分析用户查询的意图、复杂度和检索需求。
    
    参数说明：
        state (AgenticRAGState): 当前工作流状态
    
    返回值：
        Dict[str, Any]: 更新后的状态
    
    ==============================================================================
    """
    logger.info("=" * 30)
    logger.info("【节点 1】执行查询分析...")
    
    try:
        # 获取查询
        query = state.get("current_query") or state.get("original_query", "")
        if not query:
            logger.error("查询为空")
            return {
                "error": "查询不能为空",
                "state": AgentState.FAILED
            }
        
        # 获取对话上下文
        context = state.get("conversation_context")
        
        # 分析查询
        if query_analyzer:
            analysis = query_analyzer.analyze(query, context)
            analysis_dict = {
                "intent": analysis.intent,
                "complexity": analysis.complexity,
                "need_retrieval": analysis.need_retrieval,
                "suggested_sources": analysis.suggested_sources,
                "key_entities": analysis.key_entities,
                "reasoning_type": analysis.reasoning_type,
                "confidence": analysis.confidence,
                "entities": analysis.entities,
                "query_type": analysis.query_type
            }
        else:
            # 模拟分析结果
            analysis_dict = {
                "intent": "FACT_QUERY",
                "complexity": "简单",
                "need_retrieval": True,
                "suggested_sources": ["vector"],
                "key_entities": [],
                "reasoning_type": "direct",
                "confidence": 0.8,
                "entities": [],
                "query_type": "fact_query"
            }
        
        logger.info(f"分析完成: {analysis_dict}")
        
        return {
            "query_analysis": analysis_dict,
            "state": AgentState.ANALYZING
        }
        
    except Exception as e:
        logger.error(f"查询分析失败: {e}")
        return {
            "error": f"查询分析失败: {str(e)}",
            "state": AgentState.FAILED
        }


def plan_retrieval_node(state: AgenticRAGState) -> Dict[str, Any]:
    """
    ==============================================================================
    节点 2：检索规划
    ==============================================================================
    
    功能说明：
        根据查询分析结果，制定检索计划。
    
    参数说明：
        state (AgenticRAGState): 当前工作流状态
    
    返回值：
        Dict[str, Any]: 更新后的状态
    
    ==============================================================================
    """
    logger.info("=" * 30)
    logger.info("【节点 2】执行检索规划...")
    
    try:
        # 获取分析结果
        analysis_dict = state.get("query_analysis")
        if not analysis_dict:
            logger.error("分析结果为空")
            return {
                "error": "分析结果为空",
                "state": AgentState.FAILED
            }
        
        # 转换为 QueryAnalysis 对象
        analysis = QueryAnalysis(
            intent=analysis_dict.get("intent", "FACT_QUERY"),
            complexity=analysis_dict.get("complexity", "简单"),
            need_retrieval=analysis_dict.get("need_retrieval", True),
            suggested_sources=analysis_dict.get("suggested_sources", []),
            key_entities=analysis_dict.get("key_entities", []),
            reasoning_type=analysis_dict.get("reasoning_type", "direct"),
            confidence=analysis_dict.get("confidence", 0.8),
            entities=analysis_dict.get("entities", []),
            query_type=analysis_dict.get("query_type", "fact_query")
        )
        
        # 制定检索计划
        if retrieval_planner:
            plan = retrieval_planner.plan(analysis)
            plan_dict = {
                "tools": plan.tools,
                "order": plan.order,
                "params": plan.params,
                "fusion_strategy": plan.fusion_strategy,
                "max_iterations": plan.max_iterations
            }
        else:
            # 模拟计划
            plan_dict = {
                "tools": ["vector"],
                "order": ["vector"],
                "params": {"top_k": 3, "threshold": 0.7},
                "fusion_strategy": "none",
                "max_iterations": 1
            }
        
        logger.info(f"计划完成: {plan_dict}")
        
        return {
            "retrieval_plan": plan_dict,
            "max_iterations": plan_dict.get("max_iterations", 3),
            "state": AgentState.PLANNING
        }
        
    except Exception as e:
        logger.error(f"检索规划失败: {e}")
        return {
            "error": f"检索规划失败: {str(e)}",
            "state": AgentState.FAILED
        }


def execute_retrieval_node(state: AgenticRAGState) -> Dict[str, Any]:
    """
    ==============================================================================
    节点 3：检索执行
    ==============================================================================
    
    功能说明：
        根据检索计划，执行多源检索，并充分利用丰富的元数据进行智能过滤。
    
    参数说明：
        state (AgenticRAGState): 当前工作流状态
    
    返回值：
        Dict[str, Any]: 更新后的状态
    
    ==============================================================================
    """
    logger.info("=" * 30)
    logger.info("【节点 3】执行检索...")
    
    try:
        # 获取查询和计划
        query = state.get("current_query") or state.get("original_query", "")
        plan_dict = state.get("retrieval_plan")
        
        if not query or not plan_dict:
            logger.error("查询或计划为空")
            return {
                "error": "查询或计划为空",
                "state": AgentState.FAILED
            }
        
        # 获取检索参数
        tools = plan_dict.get("tools", ["vector"])
        params = plan_dict.get("params", {})
        top_k = params.get("top_k", 5)
        threshold = params.get("threshold", 0.6)
        where_filter = params.get("filter", {})
        
        # 执行实际检索
        retrieved_docs = []
        if knowledge_retriever:
            try:
                # 构建 where 条件（结合计划中的过滤器和查询分析的元数据）
                where_condition = knowledge_retriever.build_where_from_query(query)
                
                # 合并过滤条件
                final_where = {}
                if where_condition:
                    final_where.update(where_condition)
                if where_filter:
                    final_where.update(where_filter)
                
                # 执行检索
                search_results = knowledge_retriever.search(
                    query=query,
                    top_k=top_k,
                    where=final_where if final_where else None
                )
                
                # 转换结果格式
                for result in search_results:
                    doc = {
                        "content": result["content"],
                        "metadata": result["metadata"],
                        "score": 1.0 - result["distance"],  # 转换距离为相似度分数
                        "source_type": "vector"
                    }
                    retrieved_docs.append(doc)
                    
            except Exception as e:
                logger.error(f"实际检索失败: {e}")
                # 回退到基本检索
                search_results = knowledge_retriever.search(query=query, top_k=top_k)
                for result in search_results:
                    doc = {
                        "content": result["content"],
                        "metadata": result["metadata"],
                        "score": 1.0 - result["distance"],  # 转换距离为相似度分数
                        "source_type": "vector"
                    }
                    retrieved_docs.append(doc)
        else:
            # 如果检索器不可用，返回空结果
            logger.warning("知识检索器不可用")
        
        logger.info(f"检索完成，返回 {len(retrieved_docs)} 个文档")
        
        # 更新搜索历史
        search_history = state.get("search_history", [])
        search_history.append({
            "query": query,
            "tools": tools,
            "docs_count": len(retrieved_docs),
            "timestamp": None,
            "where_filter": where_filter  # 记录使用的过滤条件
        })
        
        return {
            "retrieved_docs": retrieved_docs,
            "search_history": search_history,
            "state": AgentState.RETRIEVING
        }
        
    except Exception as e:
        logger.error(f"检索执行失败: {e}")
        return {
            "error": f"检索执行失败: {str(e)}",
            "state": AgentState.FAILED
        }


def evaluate_results_node(state: AgenticRAGState) -> Dict[str, Any]:
    """
    ==============================================================================
    节点 4：结果评估
    ==============================================================================
    
    功能说明：
        评估检索结果的质量。
    
    参数说明：
        state (AgenticRAGState): 当前工作流状态
    
    返回值：
        Dict[str, Any]: 更新后的状态
    
    ==============================================================================
    """
    logger.info("=" * 30)
    logger.info("【节点 4】评估检索结果...")
    
    try:
        # 获取查询、文档和分析结果
        query = state.get("current_query") or state.get("original_query", "")
        docs_dict = state.get("retrieved_docs", [])
        analysis_dict = state.get("query_analysis")
        
        if not query or not docs_dict:
            logger.error("查询或文档为空")
            return {
                "error": "查询或文档为空",
                "state": AgentState.FAILED
            }
        
        # 转换为 Document 对象
        docs = [
            Document(
                content=d.get("content", ""),
                metadata=d.get("metadata", {}),
                score=d.get("score", 0.0),
                source_type=d.get("source_type", "vector")
            )
            for d in docs_dict
        ]
        
        # 转换为 QueryAnalysis 对象
        analysis = QueryAnalysis(
            intent=analysis_dict.get("intent", "FACT_QUERY"),
            complexity=analysis_dict.get("complexity", "简单"),
            need_retrieval=analysis_dict.get("need_retrieval", True),
            suggested_sources=analysis_dict.get("suggested_sources", []),
            key_entities=analysis_dict.get("key_entities", []),
            reasoning_type=analysis_dict.get("reasoning_type", "direct"),
            confidence=analysis_dict.get("confidence", 0.8),
            entities=analysis_dict.get("entities", []),
            query_type=analysis_dict.get("query_type", "fact_query")
        )
        
        # 评估结果
        if result_evaluator:
            evaluation = result_evaluator.evaluate(query, docs, analysis)
            evaluation_dict = {
                "relevance_score": evaluation.relevance_score,
                "coverage_score": evaluation.coverage_score,
                "diversity_score": evaluation.diversity_score,
                "freshness_score": evaluation.freshness_score,
                "overall_score": evaluation.overall_score,
                "need_more": evaluation.need_more,
                "gaps": evaluation.gaps,
                "suggestions": evaluation.suggestions
            }
        else:
            # 模拟评估结果
            evaluation_dict = {
                "relevance_score": 0.8,
                "coverage_score": 0.7,
                "diversity_score": 0.6,
                "freshness_score": 0.9,
                "overall_score": 0.75,
                "need_more": False,
                "gaps": [],
                "suggestions": []
            }
        
        logger.info(f"评估完成: {evaluation_dict}")
        
        return {
            "evaluation": evaluation_dict,
            "state": AgentState.EVALUATING
        }
        
    except Exception as e:
        logger.error(f"结果评估失败: {e}")
        return {
            "error": f"结果评估失败: {str(e)}",
            "state": AgentState.FAILED
        }


def reflect_node(state: AgenticRAGState) -> Dict[str, Any]:
    """
    ==============================================================================
    节点 5：反思
    ==============================================================================
    
    功能说明：
        分析检索失败原因，生成优化方案。
    
    参数说明：
        state (AgenticRAGState): 当前工作流状态
    
    返回值：
        Dict[str, Any]: 更新后的状态
    
    ==============================================================================
    """
    logger.info("=" * 30)
    logger.info("【节点 5】执行反思...")
    
    try:
        # 获取查询、文档、评估结果和历史
        query = state.get("current_query") or state.get("original_query", "")
        docs_dict = state.get("retrieved_docs", [])
        evaluation_dict = state.get("evaluation")
        search_history = state.get("search_history", [])
        
        if not query or not docs_dict or not evaluation_dict:
            logger.error("必要数据为空")
            return {
                "error": "必要数据为空",
                "state": AgentState.FAILED
            }
        
        # 转换为 Document 对象
        docs = [
            Document(
                content=d.get("content", ""),
                metadata=d.get("metadata", {}),
                score=d.get("score", 0.0),
                source_type=d.get("source_type", "vector")
            )
            for d in docs_dict
        ]
        
        # 转换为 EvaluationResult 对象
        evaluation = evaluation_dict
        # 简化处理，直接使用字典
        
        # 转换为 SearchRecord 对象
        history = [
            {
                "query": h.get("query", ""),
                "timestamp": h.get("timestamp"),
                "tools": h.get("tools", []),
                "docs_count": h.get("docs_count", 0),
                "evaluation": None
            }
            for h in search_history
        ]
        
        # 执行反思
        if reflection_engine:
            # 简化处理，直接使用字典
            reflection = reflection_engine.reflect(
                query, docs, evaluation, history
            )
            reflection_dict = {
                "failure_reason": reflection.failure_reason,
                "query_refinement": reflection.query_refinement,
                "strategy_adjustment": reflection.strategy_adjustment,
                "next_action": reflection.next_action
            }
        else:
            # 模拟反思结果
            reflection_dict = {
                "failure_reason": "相关性较低",
                "query_refinement": query,
                "strategy_adjustment": {"action": "query_rewrite"},
                "next_action": "retry_with_rewritten_query"
            }
        
        logger.info(f"反思完成: {reflection_dict}")
        
        return {
            "reflection": reflection_dict,
            "state": AgentState.REFLECTING
        }
        
    except Exception as e:
        logger.error(f"反思失败: {e}")
        return {
            "error": f"反思失败: {str(e)}",
            "state": AgentState.FAILED
        }


def synthesize_node(state: AgenticRAGState) -> Dict[str, Any]:
    """
    ==============================================================================
    节点 6：知识整合
    ==============================================================================
    
    功能说明：
        整合多源检索结果，生成最终上下文。
    
    参数说明：
        state (AgenticRAGState): 当前工作流状态
    
    返回值：
        Dict[str, Any]: 更新后的状态
    
    ==============================================================================
    """
    logger.info("=" * 30)
    logger.info("【节点 6】整合知识...")
    
    try:
        # 获取查询、文档和计划
        query = state.get("current_query") or state.get("original_query", "")
        docs_dict = state.get("retrieved_docs", [])
        plan_dict = state.get("retrieval_plan")
        
        if not query or not docs_dict:
            logger.error("查询或文档为空")
            return {
                "error": "查询或文档为空",
                "state": AgentState.FAILED
            }
        
        # 获取知识源
        sources = plan_dict.get("tools", ["vector"]) if plan_dict else ["vector"]
        
        # 转换为 Document 对象
        docs = [
            Document(
                content=d.get("content", ""),
                metadata=d.get("metadata", {}),
                score=d.get("score", 0.0),
                source_type=d.get("source_type", "vector")
            )
            for d in docs_dict
        ]
        
        # 整合知识
        if knowledge_synthesizer:
            context = knowledge_synthesizer.synthesize(query, docs, sources)
        else:
            # 模拟整合结果
            context = f"整合后的知识上下文 - 查询: {query}"
        
        logger.info(f"知识整合完成")
        
        # 更新推理轨迹
        reasoning_trace = state.get("reasoning_trace", [])
        reasoning_trace.append(f"整合知识: {query}")
        
        return {
            "final_context": context,
            "reasoning_trace": reasoning_trace,
            "state": AgentState.COMPLETED
        }
        
    except Exception as e:
        logger.error(f"知识整合失败: {e}")
        return {
            "error": f"知识整合失败: {str(e)}",
            "state": AgentState.FAILED
        }


def route_after_evaluation(state: AgenticRAGState) -> Literal["continue", "finish"]:
    """
    ==============================================================================
    评估后路由
    ==============================================================================
    
    功能说明：
        根据评估结果，决定是继续反思还是结束检索。
    
    参数说明：
        state (AgenticRAGState): 当前工作流状态
    
    返回值：
        Literal["continue", "finish"]: 路由目标
    
    ==============================================================================
    """
    evaluation = state.get("evaluation", {})
    iteration = state.get("iteration", 0)
    max_iterations = state.get("max_iterations", 3)
    
    # 满足条件或达到最大迭代次数，结束
    if isinstance(evaluation, dict):
        overall_score = evaluation.get("overall_score", 0)
    else:
        overall_score = getattr(evaluation, "overall_score", 0) if evaluation else 0
    
    if overall_score >= 0.7:
        logger.info("评估分数高，结束检索")
        return "finish"
    if iteration >= max_iterations:
        logger.info("达到最大迭代次数，结束检索")
        return "finish"
    
    logger.info("评估分数低，继续反思")
    return "continue"


def route_after_reflection(state: AgenticRAGState) -> Literal["retry", "finish"]:
    """
    ==============================================================================
    反思后路由
    ==============================================================================
    
    功能说明：
        根据反思结果，决定是重试还是结束。
    
    参数说明：
        state (AgenticRAGState): 当前工作流状态
    
    返回值：
        Literal["retry", "finish"]: 路由目标
    
    ==============================================================================
    """
    iteration = state.get("iteration", 0)
    max_iterations = state.get("max_iterations", 3)
    
    if iteration < max_iterations:
        logger.info("迭代次数未超限，重试")
        return "retry"
    
    logger.info("达到最大迭代次数，结束")
    return "finish"
