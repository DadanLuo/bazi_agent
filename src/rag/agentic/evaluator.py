"""
==============================================================================
结果评估器
==============================================================================

功能说明：
    本模块实现了结果评估器，用于评估检索结果的质量，判断是否满足查询需求，
    为反思优化提供依据。

核心功能：
    - 相关性评估：评估文档与查询的相关程度
    - 覆盖度评估：评估是否覆盖查询的所有方面
    - 多样性评估：评估结果是否多样化
    - 新鲜度评估：评估信息是否过时
    - 综合评分：计算综合分数

==============================================================================
"""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from .state import Document, EvaluationResult, QueryAnalysis

logger = logging.getLogger(__name__)


class ResultEvaluator:
    """
    ==============================================================================
    结果评估器
    ==============================================================================
    
    功能说明：
        评估检索结果的质量，判断是否满足查询需求，为反思优化提供依据。
    
    核心方法：
        - evaluate(): 评估检索结果
    
    评估维度：
        1. 相关性：文档与查询的相关程度
        2. 覆盖度：是否覆盖查询的所有方面
        3. 多样性：结果是否多样化
        4. 新鲜度：信息是否过时
    
    评估阈值：
        - >= 0.8: 优秀，直接使用
        - 0.6 - 0.8: 良好，可用，可选优化
        - 0.4 - 0.6: 一般，触发反思优化
        - < 0.4: 较差，必须优化
    
    ==============================================================================
    """

    def __init__(self):
        """初始化结果评估器"""
        logger.info("ResultEvaluator 初始化完成")

    def evaluate(
        self,
        query: str,
        docs: List[Document],
        analysis: QueryAnalysis
    ) -> EvaluationResult:
        """
        ==============================================================================
        评估检索结果
        ==============================================================================
        
        功能说明：
            评估检索结果的质量，判断是否满足查询需求。
        
        参数说明：
            query: 用户查询文本
            docs: 检索到的文档列表
            analysis: 查询分析结果
        
        返回值：
            EvaluationResult: 评估结果
        
        处理流程：
            1. 相关性评估
            2. 覆盖度评估
            3. 多样性评估
            4. 新鲜度评估
            5. 综合评分
            6. 信息缺口分析
        
        ==============================================================================
        """
        logger.info(f"开始评估检索结果，文档数量: {len(docs)}")
        
        if not docs:
            logger.warning("没有检索到文档，返回低分评估")
            return EvaluationResult(
                relevance_score=0.0,
                coverage_score=0.0,
                diversity_score=0.0,
                freshness_score=0.0,
                overall_score=0.0,
                need_more=True,
                gaps=["没有检索到任何相关文档"],
                suggestions=["尝试使用更简单的查询", "检查查询中的关键词"]
            )
        
        # 1. 相关性评估
        relevance = self._compute_relevance(query, docs)
        logger.info(f"相关性分数: {relevance:.2f}")
        
        # 2. 覆盖度评估
        coverage = self._compute_coverage(query, docs, analysis.key_entities)
        logger.info(f"覆盖度分数: {coverage:.2f}")
        
        # 3. 多样性评估
        diversity = self._compute_diversity(docs)
        logger.info(f"多样性分数: {diversity:.2f}")
        
        # 4. 新鲜度评估
        freshness = self._compute_freshness(docs)
        logger.info(f"新鲜度分数: {freshness:.2f}")
        
        # 5. 综合评分
        overall = self._compute_overall(relevance, coverage, diversity, freshness)
        logger.info(f"综合分数: {overall:.2f}")
        
        # 6. 信息缺口分析
        gaps = self._analyze_gaps(query, docs, analysis)
        logger.info(f"信息缺口数量: {len(gaps)}")
        
        # 7. 优化建议
        suggestions = self._generate_suggestions(relevance, coverage, diversity, gaps)
        
        return EvaluationResult(
            relevance_score=relevance,
            coverage_score=coverage,
            diversity_score=diversity,
            freshness_score=freshness,
            overall_score=overall,
            need_more=len(gaps) > 0,
            gaps=gaps,
            suggestions=suggestions
        )

    def _compute_relevance(self, query: str, docs: List[Document]) -> float:
        """
        ==============================================================================
        相关性评估
        ==============================================================================
        
        功能说明：
            评估文档与查询的相关程度。
        
        参数说明：
            query: 用户查询文本
            docs: 检索到的文档列表
        
        返回值：
            float: 相关性分数 (0-1)
        
        评估方法：
            - 基于检索分数
            - 基于关键词匹配
        
        ==============================================================================
        """
        if not docs:
            return 0.0
        
        # 基于检索分数
        avg_score = sum(doc.score for doc in docs) / len(docs)
        
        # 归一化分数（假设分数范围是 0-1）
        normalized_score = avg_score
        
        # 基于关键词匹配
        query_keywords = set(query.lower().split())
        keyword_matches = []
        
        for doc in docs:
            doc_keywords = set(doc.content.lower().split())
            matches = len(query_keywords & doc_keywords)
            keyword_matches.append(matches / max(len(query_keywords), 1))
        
        avg_keyword_match = sum(keyword_matches) / len(keyword_matches)
        
        # 综合评分（70% 检索分数 + 30% 关键词匹配）
        relevance = 0.7 * normalized_score + 0.3 * avg_keyword_match
        
        return min(max(relevance, 0.0), 1.0)

    def _compute_coverage(self, query: str, docs: List[Document], entities: List[str]) -> float:
        """
        ==============================================================================
        覆盖度评估
        ==============================================================================
        
        功能说明：
            评估检索结果是否覆盖查询的所有方面。
        
        参数说明：
            query: 用户查询文本
            docs: 检索到的文档列表
            entities: 查询中的关键实体
        
        返回值：
            float: 覆盖度分数 (0-1)
        
        评估方法：
            - 实体覆盖：检查是否覆盖了查询中的所有实体
            - 主题覆盖：检查文档是否覆盖了查询的主要主题
        
        ==============================================================================
        """
        if not docs:
            return 0.0
        
        # 实体覆盖
        query_lower = query.lower()
        entity_coverage = 0.0
        
        for entity in entities:
            if entity.lower() in query_lower:
                entity_coverage += 1.0
        
        if entities:
            entity_coverage /= len(entities)
        
        # 主题覆盖
        # 提取查询中的主要主题词
        query_words = set(query.lower().split())
        topic_coverage = []
        
        for doc in docs:
            doc_words = set(doc.content.lower().split())
            coverage = len(query_words & doc_words) / max(len(query_words), 1)
            topic_coverage.append(coverage)
        
        avg_topic_coverage = sum(topic_coverage) / len(topic_coverage) if topic_coverage else 0.0
        
        # 综合评分（50% 实体覆盖 + 50% 主题覆盖）
        coverage = 0.5 * entity_coverage + 0.5 * avg_topic_coverage
        
        return min(max(coverage, 0.0), 1.0)

    def _compute_diversity(self, docs: List[Document]) -> float:
        """
        ==============================================================================
        多样性评估
        ==============================================================================
        
        功能说明：
            评估检索结果的多样性。
        
        参数说明：
            docs: 检索到的文档列表
        
        返回值：
            float: 多样性分数 (0-1)
        
        评估方法：
            - 基于内容相似度
            - 基于来源多样性
        
        ==============================================================================
        """
        if len(docs) <= 1:
            return 1.0
        
        # 计算文档之间的相似度
        similarities = []
        for i, doc1 in enumerate(docs):
            for doc2 in docs[i+1:]:
                # 基于内容相似度
                content1 = set(doc1.content.lower().split())
                content2 = set(doc2.content.lower().split())
                jaccard = len(content1 & content2) / len(content1 | content2)
                similarities.append(jaccard)
        
        if not similarities:
            return 1.0
        
        avg_similarity = sum(similarities) / len(similarities)
        
        # 相似度越低，多样性越高
        diversity = 1.0 - avg_similarity
        
        return min(max(diversity, 0.0), 1.0)

    def _compute_freshness(self, docs: List[Document]) -> float:
        """
        ==============================================================================
        新鲜度评估
        ==============================================================================
        
        功能说明：
            评估检索结果的新鲜度。
        
        参数说明：
            docs: 检索到的文档列表
        
        返回值：
            float: 新鲜度分数 (0-1)
        
        评估方法：
            - 基于文档元数据中的时间信息
        
        ==============================================================================
        """
        if not docs:
            return 0.0
        
        # 检查是否有时间信息
        has_time_info = any(
            "timestamp" in doc.metadata or "date" in doc.metadata
            for doc in docs
        )
        
        if not has_time_info:
            # 如果没有时间信息，默认中等新鲜度
            return 0.7
        
        # 基于时间信息计算新鲜度
        fresh_scores = []
        for doc in docs:
            timestamp = doc.metadata.get("timestamp") or doc.metadata.get("date")
            if timestamp:
                # 简单处理：有时间信息就认为较新
                fresh_scores.append(0.9)
            else:
                fresh_scores.append(0.5)
        
        return sum(fresh_scores) / len(fresh_scores)

    def _compute_overall(
        self,
        relevance: float,
        coverage: float,
        diversity: float,
        freshness: float
    ) -> float:
        """
        ==============================================================================
        综合评分
        ==============================================================================
        
        功能说明：
            计算综合评分。
        
        参数说明：
            relevance: 相关性分数
            coverage: 覆盖度分数
            diversity: 多样性分数
            freshness: 新鲜度分数
        
        返回值：
            float: 综合分数 (0-1)
        
        评分权重：
            - 相关性: 40%
            - 覆盖度: 30%
            - 多样性: 20%
            - 新鲜度: 10%
        
        ==============================================================================
        """
        return (
            0.4 * relevance +
            0.3 * coverage +
            0.2 * diversity +
            0.1 * freshness
        )

    def _analyze_gaps(
        self,
        query: str,
        docs: List[Document],
        analysis: QueryAnalysis
    ) -> List[str]:
        """
        ==============================================================================
        信息缺口分析
        ==============================================================================
        
        功能说明：
            分析检索结果中的信息缺口。
        
        参数说明：
            query: 用户查询文本
            docs: 检索到的文档列表
            analysis: 查询分析结果
        
        返回值：
            List[str]: 信息缺口列表
        
        ==============================================================================
        """
        gaps = []
        
        # 检查实体覆盖
        query_lower = query.lower()
        for entity in analysis.key_entities:
            entity_found = False
            for doc in docs:
                if entity.lower() in doc.content.lower():
                    entity_found = True
                    break
            if not entity_found:
                gaps.append(f"缺少实体 '{entity}' 的相关信息")
        
        # 检查意图覆盖
        if analysis.intent == "INFERENCE":
            # 推理类查询需要更多上下文
            if len(docs) < 3:
                gaps.append("检索结果较少，可能需要更多上下文信息")
        
        elif analysis.intent == "COMPARISON":
            # 比较类查询需要多个比较对象
            if len(docs) < 2:
                gaps.append("检索结果较少，难以进行比较")
        
        return gaps

    def _generate_suggestions(
        self,
        relevance: float,
        coverage: float,
        diversity: float,
        gaps: List[str]
    ) -> List[str]:
        """
        ==============================================================================
        生成优化建议
        ==============================================================================
        
        功能说明：
            根据评估结果，生成优化建议。
        
        参数说明：
            relevance: 相关性分数
            coverage: 覆盖度分数
            diversity: 多样性分数
            gaps: 信息缺口列表
        
        返回值：
            List[str]: 优化建议列表
        
        ==============================================================================
        """
        suggestions = []
        
        if relevance < 0.6:
            suggestions.append("尝试使用更具体的关键词")
            suggestions.append("考虑使用同义词扩展查询")
        
        if coverage < 0.6:
            suggestions.append("增加检索的文档数量")
            suggestions.append("尝试使用不同的检索策略")
        
        if diversity < 0.5:
            suggestions.append("尝试使用不同的检索工具")
            suggestions.append("调整检索参数以获取更多样化的结果")
        
        for gap in gaps:
            suggestions.append(f"补充信息: {gap}")
        
        return suggestions
