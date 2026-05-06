"""
==============================================================================
反思引擎
==============================================================================

功能说明：
    本模块实现了反思引擎，用于分析检索失败的原因，生成优化方案，
    支持多轮迭代优化。

核心功能：
    - 失败原因分析：分析检索失败的根本原因
    - 查询优化：生成查询重写建议
    - 策略调整：调整检索策略
    - 迭代控制：控制迭代次数

==============================================================================
"""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from .state import Document, EvaluationResult, ReflectionResult, SearchRecord

logger = logging.getLogger(__name__)


class ReflectionEngine:
    """
    ==============================================================================
    反思引擎
    ==============================================================================
    
    功能说明：
        分析检索失败的原因，生成优化方案，支持多轮迭代优化。
    
    核心方法：
        - reflect(): 反思检索失败原因，生成优化方案
    
    失败原因分析：
        1. 相关性低 → 查询重写
        2. 覆盖度低 → 查询扩展
        3. 多样性低 → 参数调整
        4. 知识库缺失 → 切换知识源
    
    优化策略：
        - 查询重写：使用同义词替换、关键词扩展
        - 查询扩展：添加相关关键词
        - 参数调整：增加 top_k、降低阈值
        - 切换知识源：向量→BM25、本地→网络
    
    ==============================================================================
    """

    def __init__(self, max_iterations: int = 3):
        """
        ==============================================================================
        初始化反思引擎
        ==============================================================================
        
        参数说明：
            max_iterations: 最大迭代次数
        
        ==============================================================================
        """
        self.max_iterations = max_iterations
        logger.info(f"ReflectionEngine 初始化完成，最大迭代次数: {max_iterations}")

    def reflect(
        self,
        query: str,
        docs: List[Document],
        evaluation: EvaluationResult,
        history: List[SearchRecord]
    ) -> ReflectionResult:
        """
        ==============================================================================
        反思检索失败原因，生成优化方案
        ==============================================================================
        
        功能说明：
            分析检索失败的原因，生成优化方案。
        
        参数说明：
            query: 用户查询文本
            docs: 检索到的文档列表
            evaluation: 评估结果
            history: 搜索历史
        
        返回值：
            ReflectionResult: 反思结果
        
        处理流程：
            1. 分析失败原因
            2. 生成优化方案
            3. 确定下一步动作
        
        ==============================================================================
        """
        logger.info("开始反思检索结果")
        
        # 分析失败原因
        reason = self._analyze_failure(evaluation, history)
        logger.info(f"失败原因: {reason}")
        
        # 生成优化方案
        refinement, adjustment = self._generate_optimization(
            query, docs, evaluation, reason
        )
        
        # 确定下一步动作
        next_action = self._determine_next_action(adjustment)
        
        return ReflectionResult(
            failure_reason=reason,
            query_refinement=refinement,
            strategy_adjustment=adjustment,
            next_action=next_action
        )

    def _analyze_failure(
        self,
        evaluation: EvaluationResult,
        history: List[SearchRecord]
    ) -> str:
        """
        ==============================================================================
        分析失败原因
        ==============================================================================
        
        功能说明：
            分析检索失败的根本原因。
        
        参数说明：
            evaluation: 评估结果
            history: 搜索历史
        
        返回值：
            str: 失败原因
        
        ==============================================================================
        """
        # 检查综合分数
        if evaluation.overall_score < 0.4:
            return "整体质量较差，需要大幅优化"
        
        # 检查相关性
        if evaluation.relevance_score < 0.5:
            return "相关性低，查询与文档不匹配"
        
        # 检查覆盖度
        if evaluation.coverage_score < 0.5:
            return "覆盖度低，缺少关键信息"
        
        # 检查多样性
        if evaluation.diversity_score < 0.4:
            return "多样性低，结果过于相似"
        
        # 检查新鲜度
        if evaluation.freshness_score < 0.5:
            return "新鲜度低，信息可能过时"
        
        # 检查信息缺口
        if evaluation.need_more:
            return f"存在信息缺口: {', '.join(evaluation.gaps)}"
        
        return "未知原因"

    def _generate_optimization(
        self,
        query: str,
        docs: List[Document],
        evaluation: EvaluationResult,
        reason: str
    ) -> tuple:
        """
        ==============================================================================
        生成优化方案
        ==============================================================================
        
        功能说明：
            根据失败原因，生成优化方案。
        
        参数说明：
            query: 用户查询文本
            docs: 检索到的文档列表
            evaluation: 评估结果
            reason: 失败原因
        
        返回值：
            tuple: (查询优化建议, 策略调整)
        
        ==============================================================================
        """
        # 相关性低 → 查询重写
        if "相关性" in reason:
            refinement = self._refine_semantic_query(query, docs)
            adjustment = {"action": "query_rewrite"}
        
        # 覆盖度低 → 查询扩展
        elif "覆盖度" in reason:
            refinement = self._expand_query(query, evaluation.gaps)
            adjustment = {"action": "query_expand"}
        
        # 多样性低 → 参数调整
        elif "多样性" in reason:
            refinement = query
            adjustment = {
                "action": "adjust_params",
                "params": {"top_k": 10, "threshold": 0.5}
            }
        
        # 信息缺口 → 查询扩展
        elif evaluation.need_more:
            refinement = self._expand_query(query, evaluation.gaps)
            adjustment = {"action": "query_expand"}
        
        # 其他情况 → 切换知识源
        else:
            refinement = query
            adjustment = {"action": "switch_source"}
        
        return refinement, adjustment

    def _refine_semantic_query(self, query: str, docs: List[Document]) -> str:
        """
        ==============================================================================
        语义查询重写
        ==============================================================================
        
        功能说明：
            基于检索到的文档，重写查询以提高相关性。
        
        参数说明：
            query: 原始查询
            docs: 检索到的文档列表
        
        返回值：
            str: 重写后的查询
        
        ==============================================================================
        """
        # 提取文档中的关键词
        keywords = set()
        for doc in docs[:3]:  # 只使用前3个文档
            words = doc.content.lower().split()
            keywords.update(words[:20])  # 只取前20个词
        
        # 构建重写查询
        query_words = query.lower().split()
        refined_words = []
        
        for word in query_words:
            refined_words.append(word)
            # 添加相关词
            for kw in keywords:
                if self._is_similar(word, kw):
                    refined_words.append(kw)
        
        return " ".join(refined_words[:30])  # 限制长度

    def _is_similar(self, word1: str, word2: str) -> bool:
        """
        ==============================================================================
        判断两个词是否相似
        ==============================================================================
        
        功能说明：
            简单判断两个词是否相似（基于字符重叠）。
        
        参数说明：
            word1: 第一个词
            word2: 第二个词
        
        返回值：
            bool: 是否相似
        
        ==============================================================================
        """
        if len(word1) < 2 or len(word2) < 2:
            return False
        
        # 计算字符重叠
        set1 = set(word1)
        set2 = set(word2)
        overlap = len(set1 & set2)
        min_len = min(len(set1), len(set2))
        
        return overlap / min_len > 0.5 if min_len > 0 else False

    def _expand_query(self, query: str, gaps: List[str]) -> str:
        """
        ==============================================================================
        查询扩展
        ==============================================================================
        
        功能说明：
            基于信息缺口，扩展查询关键词。
        
        参数说明：
            query: 原始查询
            gaps: 信息缺口列表
        
        返回值：
            str: 扩展后的查询
        
        ==============================================================================
        """
        query_words = query.lower().split()
        
        # 从信息缺口提取关键词
        for gap in gaps:
            # 简单提取：移除常见词
            words = gap.lower().split()
            for word in words:
                if word not in ["的", "是", "了", "在", "有"]:
                    query_words.append(word)
        
        return " ".join(query_words[:30])  # 限制长度

    def _determine_next_action(self, adjustment: Dict[str, Any]) -> str:
        """
        ==============================================================================
        确定下一步动作
        ==============================================================================
        
        功能说明：
            根据策略调整，确定下一步动作。
        
        参数说明：
            adjustment: 策略调整
        
        返回值：
            str: 下一步动作
        
        ==============================================================================
        """
        action = adjustment.get("action", "")
        
        if action == "query_rewrite":
            return "retry_with_rewritten_query"
        elif action == "query_expand":
            return "retry_with_expanded_query"
        elif action == "adjust_params":
            return "retry_with_adjusted_params"
        elif action == "switch_source":
            return "switch_to_alternative_source"
        else:
            return "finish"

    def should_continue(
        self,
        iteration: int,
        reflection: ReflectionResult
    ) -> bool:
        """
        ==============================================================================
        判断是否继续迭代
        ==============================================================================
        
        功能说明：
            根据当前迭代次数和反思结果，判断是否继续迭代。
        
        参数说明：
            iteration: 当前迭代次数
            reflection: 反思结果
        
        返回值：
            bool: 是否继续迭代
        
        ==============================================================================
        """
        if iteration >= self.max_iterations:
            logger.info(f"达到最大迭代次数 {self.max_iterations}")
            return False
        
        if reflection.next_action == "finish":
            logger.info("反思建议结束迭代")
            return False
        
        return True
