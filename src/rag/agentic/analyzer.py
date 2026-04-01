"""
==============================================================================
查询分析器
==============================================================================

功能说明：
    本模块实现了查询分析器，用于分析用户查询的意图、复杂度和检索需求，
    为后续检索规划提供依据。

核心功能：
    - 意图分类：识别用户查询的意图类型
    - 复杂度评估：评估查询的复杂程度
    - 实体识别：提取查询中的关键实体
    - 检索需求判断：判断是否需要检索
    - 知识源建议：建议使用哪些知识源

==============================================================================
"""

import re
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from .state import QueryAnalysis, Document, ConversationContext

logger = logging.getLogger(__name__)


class QueryAnalyzer:
    """
    ==============================================================================
    查询分析器
    ==============================================================================
    
    功能说明：
        分析用户查询的意图、复杂度和检索需求，为后续检索规划提供依据。
    
    核心方法：
        - analyze(): 分析查询并返回分析结果
    
    意图分类：
        - FACT_QUERY: 事实查询（"甲木是什么五行？"）
        - INFERENCE: 推理分析（"这个八字格局如何？"）
        - COMPARISON: 比较评估（"甲木和乙木有什么区别？"）
        - CLARIFICATION: 澄清追问（"你说的正官是什么意思？"）
        - FOLLOW_UP: 深入追问（"能详细说说吗？"）
    
    复杂度评估：
        - 简单：单跳查询，直接检索即可回答
        - 中等：2-3跳查询，需要多次检索或简单推理
        - 复杂：多跳查询，需要复杂推理或多源整合
    
    ==============================================================================
    """

    # 意图关键词
    INTENT_KEYWORDS = {
        "FACT_QUERY": [
            "是什么", "属于", "代表", "含义", "定义", "解释", "怎么理解",
            "五行", "十神", "格局", "喜用神"
        ],
        "INFERENCE": [
            "如何", "怎么样", "怎么样", "原因", "为什么", "因为", "所以",
            "判断", "分析", "评估", "评价", "解读"
        ],
        "COMPARISON": [
            "区别", "比较", "不同", "哪个", " vs ", " versus ",
            "和", "与", "还是", "或者"
        ],
        "CLARIFICATION": [
            "什么意思", "什么是", "解释", "说明", "详细说说", "具体点"
        ],
        "FOLLOW_UP": [
            "然后", "接着", "然后呢", "那", "那呢", "还有", "继续"
        ]
    }

    # 复杂度关键词
    COMPLEXITY_KEYWORDS = {
        "complexity_words": ["为什么", "怎么", "如何", "原因", "因为", "所以"],
        "comparison_words": ["区别", "比较", "哪个", " vs ", " versus "],
        "multi_hop_words": ["和", "与", "以及", "还有", "并且"]
    }

    def __init__(self):
        """初始化查询分析器"""
        logger.info("QueryAnalyzer 初始化完成")

    def analyze(
        self,
        query: str,
        context: Optional[ConversationContext] = None
    ) -> QueryAnalysis:
        """
        ==============================================================================
        分析查询
        ==============================================================================
        
        功能说明：
            分析用户查询的意图、复杂度和检索需求。
        
        参数说明：
            query: 用户查询文本
            context: 对话上下文（多轮对话时使用）
        
        返回值：
            QueryAnalysis: 分析结果
        
        处理流程：
            1. 意图分类
            2. 复杂度评估
            3. 实体识别
            4. 检索需求判断
            5. 知识源建议
        
        ==============================================================================
        """
        logger.info(f"开始分析查询: {query}")
        
        # 1. 意图分类
        intent = self._classify_intent(query, context)
        logger.info(f"识别意图: {intent}")
        
        # 2. 复杂度评估
        complexity = self._assess_complexity(query, intent)
        logger.info(f"评估复杂度: {complexity}")
        
        # 3. 实体识别
        entities = self._extract_entities(query, context)
        logger.info(f"提取实体: {entities}")
        
        # 4. 检索需求判断
        need_retrieval = self._check_retrieval_need(query, intent, context)
        logger.info(f"需要检索: {need_retrieval}")
        
        # 5. 知识源建议
        sources = self._suggest_sources(intent, complexity, entities)
        logger.info(f"建议知识源: {sources}")
        
        # 计算置信度
        confidence = self._calculate_confidence(intent, entities)
        
        return QueryAnalysis(
            intent=intent,
            complexity=complexity,
            need_retrieval=need_retrieval,
            suggested_sources=sources,
            key_entities=[e["name"] for e in entities],
            reasoning_type=self._determine_reasoning_type(intent, complexity),
            confidence=confidence,
            entities=entities,
            query_type=self._determine_query_type(query, intent)
        )

    def _classify_intent(self, query: str, context: Optional[ConversationContext] = None) -> str:
        """
        ==============================================================================
        意图分类
        ==============================================================================
        
        功能说明：
            根据查询文本和上下文，判断用户查询的意图类型。
        
        参数说明：
            query: 用户查询文本
            context: 对话上下文
        
        返回值：
            str: 意图类型
        
        ==============================================================================
        """
        query_lower = query.lower()
        
        # 检查是否为追问
        if context and self._is_followup_query(query):
            return "FOLLOW_UP"
        
        # 检查是否为澄清
        if any(kw in query for kw in self.INTENT_KEYWORDS["CLARIFICATION"]):
            return "CLARIFICATION"
        
        # 检查比较意图
        if any(kw in query for kw in self.INTENT_KEYWORDS["COMPARISON"]):
            return "COMPARISON"
        
        # 检查推理意图
        if any(kw in query for kw in self.INTENT_KEYWORDS["INFERENCE"]):
            return "INFERENCE"
        
        # 默认为事实查询
        return "FACT_QUERY"

    def _is_followup_query(self, query: str) -> bool:
        """判断是否为追问"""
        followup_patterns = [
            r"^那", r"^然后", r"^接着", r"^然后呢", r"^那呢",
            r"^还有", r"^继续", r"^再", r"^也", r"^同样"
        ]
        return any(re.match(pattern, query) for pattern in followup_patterns)

    def _assess_complexity(self, query: str, intent: str) -> str:
        """
        ==============================================================================
        复杂度评估
        ==============================================================================
        
        功能说明：
            根据查询内容和意图，评估查询的复杂程度。
        
        参数说明：
            query: 用户查询文本
            intent: 意图类型
        
        返回值：
            str: 复杂度（简单/中等/复杂）
        
        评估规则：
            - 简单：单跳查询，直接检索即可回答
            - 中等：2-3跳查询，需要多次检索或简单推理
            - 复杂：多跳查询，需要复杂推理或多源整合
        
        ==============================================================================
        """
        # 实体数量
        entity_count = len(self._extract_entities(query))
        
        # 是否包含推理词
        has_inference = any(
            kw in query 
            for kw in self.COMPLEXITY_KEYWORDS["complexity_words"]
        )
        
        # 是否需要比较
        has_comparison = any(
            kw in query 
            for kw in self.COMPLEXITY_KEYWORDS["comparison_words"]
        )
        
        # 是否多跳
        has_multi_hop = any(
            kw in query 
            for kw in self.COMPLEXITY_KEYWORDS["multi_hop_words"]
        )
        
        # 综合判断
        if entity_count <= 2 and not has_inference and not has_comparison:
            return "简单"
        elif entity_count <= 4 or has_inference or has_comparison or has_multi_hop:
            return "中等"
        else:
            return "复杂"

    def _extract_entities(self, query: str, context: Optional[ConversationContext] = None) -> List[Dict[str, Any]]:
        """
        ==============================================================================
        实体识别
        ==============================================================================
        
        功能说明：
            从查询中提取关键实体，包括天干、地支、五行、十神、格局、用神等。
            利用丰富的元数据字段进行更精确的实体识别。
        
        参数说明：
            query: 用户查询文本
            context: 对话上下文
        
        返回值：
            List[Dict[str, Any]]: 实体列表，每个实体包含名称、类型、位置等信息
        
        ==============================================================================
        """
        entities = []
        
        # 天干
        tiangan_pattern = r"[甲乙丙丁戊己庚辛壬癸]"
        for match in re.finditer(tiangan_pattern, query):
            entities.append({
                "name": match.group(),
                "type": "tiangan",
                "position": match.start()
            })
        
        # 地支
        dizhi_pattern = r"[子丑寅卯辰巳午未申酉戌亥]"
        for match in re.finditer(dizhi_pattern, query):
            entities.append({
                "name": match.group(),
                "type": "dizhi",
                "position": match.start()
            })
        
        # 五行
        wuxing_pattern = r"[金木水火土]"
        for match in re.finditer(wuxing_pattern, query):
            entities.append({
                "name": match.group(),
                "type": "wuxing",
                "position": match.start()
            })
        
        # 十神（改进模式）
        shishen_patterns = [
            r"正官", r"七杀", r"偏官", r"正印", r"偏印", 
            r"正财", r"偏财", r"食神", r"伤官", r"比肩", 
            r"劫财", r"比劫"
        ]
        for pattern in shishen_patterns:
            for match in re.finditer(pattern, query):
                entities.append({
                    "name": match.group(),
                    "type": "shensha",
                    "position": match.start()
                })
        
        # 格局
        geju_patterns = [
            r"正官格", r"七杀格", r"偏官格", r"正印格", r"偏印格",
            r"正财格", r"偏财格", r"食神格", r"伤官格", r"建禄格",
            r"羊刃格", r"从格", r"化气格", r"财格", r"官格", r"印格"
        ]
        for pattern in geju_patterns:
            for match in re.finditer(pattern, query):
                entities.append({
                    "name": match.group(),
                    "type": "geju",
                    "position": match.start()
                })
        
        # 用神相关
        yongshen_patterns = [r"用神", r"喜神", r"忌神", r"仇神", r"闲神"]
        for pattern in yongshen_patterns:
            for match in re.finditer(pattern, query):
                entities.append({
                    "name": match.group(),
                    "type": "yongshen",
                    "position": match.start()
                })
        
        # 流年相关
        liunian_patterns = [r"流年", r"大运", r"小运", r"岁运", r"太岁"]
        for pattern in liunian_patterns:
            for match in re.finditer(pattern, query):
                entities.append({
                    "name": match.group(),
                    "type": "liunian",
                    "position": match.start()
                })
        
        # 长生十二神
        changsheng_patterns = [
            r"长生", r"沐浴", r"冠带", r"临官", r"帝旺", 
            r"衰", r"病", r"死", r"墓", r"绝", r"胎", r"养"
        ]
        for pattern in changsheng_patterns:
            for match in re.finditer(pattern, query):
                entities.append({
                    "name": match.group(),
                    "type": "changsheng",
                    "position": match.start()
                })
        
        # 如果没有提取到实体，从上下文中获取
        if not entities and context and context.bazi_result:
            # 从八字结果中提取四柱
            if "four_pillars" in context.bazi_result:
                pillars = context.bazi_result["four_pillars"]
                for pillar in pillars:
                    if pillar.get("tiangan"):
                        entities.append({
                            "name": pillar.get("tiangan", ""),
                            "type": "tiangan",
                            "position": -1
                        })
                    if pillar.get("dizhi"):
                        entities.append({
                            "name": pillar.get("dizhi", ""),
                            "type": "dizhi",
                            "position": -1
                        })
        
        return entities

    def _check_retrieval_need(
        self,
        query: str,
        intent: str,
        context: Optional[ConversationContext] = None
    ) -> bool:
        """
        ==============================================================================
        检索需求判断
        ==============================================================================
        
        功能说明：
            判断查询是否需要检索知识库。
        
        参数说明：
            query: 用户查询文本
            intent: 意图类型
            context: 对话上下文
        
        返回值：
            bool: 是否需要检索
        
        ==============================================================================
        """
        # 澄清类查询可能不需要检索
        if intent == "CLARIFICATION":
            return False
        
        # 追问类查询可能需要检索
        if intent == "FOLLOW_UP":
            return True
        
        # 事实查询通常需要检索
        if intent == "FACT_QUERY":
            return True
        
        # 推理和比较查询通常需要检索
        if intent in ["INFERENCE", "COMPARISON"]:
            return True
        
        return False

    def _suggest_sources(
        self,
        intent: str,
        complexity: str,
        entities: List[Dict[str, Any]]
    ) -> List[str]:
        """
        ==============================================================================
        知识源建议
        ==============================================================================
        
        功能说明：
            根据查询意图和复杂度，建议使用哪些知识源。
        
        参数说明：
            intent: 意图类型
            complexity: 复杂度
            entities: 实体列表
        
        返回值：
            List[str]: 建议的知识源列表
        
        ==============================================================================
        """
        sources = []
        
        # 向量检索：适用于语义检索
        sources.append("vector")
        
        # BM25：适用于关键词精确匹配
        if intent == "FACT_QUERY" or len(entities) > 0:
            sources.append("bm25")
        
        # 图谱检索：适用于复杂推理和关系查询
        if complexity == "复杂" or intent == "COMPARISON":
            sources.append("graph")
        
        return sources

    def _calculate_confidence(self, intent: str, entities: List[Dict[str, Any]]) -> float:
        """
        ==============================================================================
        计算分析置信度
        ==============================================================================
        
        功能说明：
            根据分析结果的确定性，计算置信度分数。
        
        参数说明：
            intent: 意图类型
            entities: 实体列表
        
        返回值：
            float: 置信度 (0-1)
        
        ==============================================================================
        """
        # 基础置信度
        base_confidence = 0.8
        
        # 实体数量影响
        if len(entities) >= 2:
            base_confidence += 0.1
        elif len(entities) == 0:
            base_confidence -= 0.1
        
        # 意图确定性
        if intent in ["FACT_QUERY", "CLARIFICATION"]:
            base_confidence += 0.1
        elif intent == "FOLLOW_UP":
            base_confidence -= 0.1
        
        return min(max(base_confidence, 0.0), 1.0)

    def _determine_reasoning_type(self, intent: str, complexity: str) -> str:
        """
        ==============================================================================
        确定推理类型
        ==============================================================================
        
        功能说明：
            根据查询意图和复杂度，确定推理类型。
        
        参数说明：
            intent: 意图类型
            complexity: 复杂度
        
        返回值：
            str: 推理类型
        
        ==============================================================================
        """
        if complexity == "简单":
            return "direct"
        elif complexity == "中等":
            if intent == "INFERENCE":
                return "inference"
            elif intent == "COMPARISON":
                return "comparison"
            else:
                return "multi_hop"
        else:  # 复杂
            return "complex_reasoning"

    def _determine_query_type(self, query: str, intent: str) -> str:
        """
        ==============================================================================
        确定查询类型
        ==============================================================================
        
        功能说明：
            根据查询内容和意图，确定查询类型。
        
        参数说明：
            query: 用户查询文本
            intent: 意图类型
        
        返回值：
            str: 查询类型
        
        ==============================================================================
        """
        if intent == "FOLLOW_UP":
            return "follow_up"
        elif intent == "CLARIFICATION":
            return "clarification"
        elif intent == "COMPARISON":
            return "comparison"
        elif intent == "INFERENCE":
            return "inference"
        else:
            return "fact_query"
