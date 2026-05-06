"""
==============================================================================
查询补全器
==============================================================================

功能说明：
    本模块实现了查询补全器，用于补全不完整的追问查询，使其能够进行有效的
    检索。

核心功能：
    - 追问类型检测：检测追问的类型
    - 实体补全：补全缺失的实体信息
    - 查询扩展：扩展查询以获取更多信息
    - 上下文添加：添加对话上下文

==============================================================================
"""

import logging
from typing import List, Dict, Any, Optional

from .state import ConversationContext, Document

logger = logging.getLogger(__name__)


class QueryCompleter:
    """
    ==============================================================================
    查询补全器
    ==============================================================================
    
    功能说明：
        补全不完整的追问查询，使其能够进行有效的检索。
    
    核心方法：
        - complete_query(): 补全查询
    
    追问类型：
        - topic_continue: 话题延续（"那格局呢？"）
        - deep_dive: 深入追问（"能详细说说吗？"）
        - clarification: 澄清追问（"什么意思？"）
    
    ==============================================================================
    """

    def __init__(self):
        """初始化查询补全器"""
        logger.info("QueryCompleter 初始化完成")

    def complete_query(
        self,
        query: str,
        conversation_state: ConversationContext
    ) -> str:
        """
        ==============================================================================
        补全不完整的追问查询
        ==============================================================================
        
        功能说明：
            补全不完整的追问查询，使其能够进行有效的检索。
        
        参数说明：
            query: 用户查询文本
            conversation_state: 对话状态
        
        返回值：
            str: 补全后的查询
        
        处理流程：
            1. 检测追问类型
            2. 根据类型进行补全
        
        ==============================================================================
        """
        logger.info(f"开始补全查询: {query}")
        
        # 检测追问类型
        followup_type = self._detect_followup_type(query)
        logger.info(f"检测到追问类型: {followup_type}")
        
        if followup_type == "topic_continue":
            # 话题延续：补全实体
            return self._complete_entities(query, conversation_state)
        elif followup_type == "deep_dive":
            # 深入追问：扩展查询
            return self._expand_query(query, conversation_state)
        elif followup_type == "clarification":
            # 澄清追问：添加上下文
            return self._add_context(query, conversation_state)
        
        return query

    def _detect_followup_type(self, query: str) -> str:
        """
        ==============================================================================
        检测追问类型
        ==============================================================================
        
        功能说明：
            检测用户查询是否为追问，以及追问的类型。
        
        参数说明：
            query: 用户查询文本
        
        返回值：
            str: 追问类型
        
        ==============================================================================
        """
        # 话题延续
        if any(w in query for w in ["那", "然后", "接着", "然后呢", "那呢"]):
            return "topic_continue"
        
        # 深入追问
        if any(w in query for w in ["详细", "具体", "深入", "再", "继续"]):
            return "deep_dive"
        
        # 澄清追问
        if any(w in query for w in ["什么意思", "为什么", "怎么理解", "解释"]):
            return "clarification"
        
        return "normal"

    def _complete_entities(
        self,
        query: str,
        conversation_state: ConversationContext
    ) -> str:
        """
        ==============================================================================
        补全实体
        ==============================================================================
        
        功能说明：
            为话题延续类追问补全缺失的实体信息。
        
        参数说明：
            query: 用户查询文本
            conversation_state: 对话状态
        
        返回值：
            str: 补全后的查询
        
        示例：
            - 用户: "那格局呢？"
            - 补全: "甲午年辛巳月丙午日丁酉时的格局判断"
        
        ==============================================================================
        """
        if not conversation_state.bazi_result:
            return query
        
        # 从八字结果中提取信息
        four_pillars = conversation_state.bazi_result.get("four_pillars", [])
        if not four_pillars:
            return query
        
        # 构建八字信息字符串
        bazi_info = self._build_bazi_info(four_pillars)
        
        # 如果查询很短，直接补全
        if len(query) <= 3:
            return f"{bazi_info}的{query}"
        
        # 否则在查询前添加八字信息
        return f"{bazi_info} {query}"

    def _build_bazi_info(self, four_pillars: List[Dict[str, Any]]) -> str:
        """
        ==============================================================================
        构建八字信息字符串
        ==============================================================================
        
        功能说明：
            将八字四柱转换为字符串。
        
        参数说明：
            four_pillars: 四柱列表
        
        返回值：
            str: 八字信息字符串
        
        ==============================================================================
        """
        parts = []
        for pillar in four_pillars:
            tiangan = pillar.get("tiangan", "")
            dizhi = pillar.get("dizhi", "")
            parts.append(f"{tiangan}{dizhi}")
        
        return "".join(parts)

    def _expand_query(
        self,
        query: str,
        conversation_state: ConversationContext
    ) -> str:
        """
        ==============================================================================
        扩展查询
        ==============================================================================
        
        功能说明：
            为深入追问扩展查询关键词。
        
        参数说明：
            query: 用户查询文本
            conversation_state: 对话状态
        
        返回值：
            str: 扩展后的查询
        
        ==============================================================================
        """
        # 添加上下文信息
        context_parts = []
        
        if conversation_state.geju:
            context_parts.append(f"格局: {conversation_state.geju}")
        
        if conversation_state.yongshen:
            context_parts.append(f"喜用神: {', '.join(conversation_state.yongshen)}")
        
        if conversation_state.wuxing_analysis:
            wuxing = conversation_state.wuxing_analysis
            context_parts.append(f"五行: {wuxing}")
        
        # 构建扩展查询
        if context_parts:
            return f"{query} {' '.join(context_parts)}"
        
        return query

    def _add_context(
        self,
        query: str,
        conversation_state: ConversationContext
    ) -> str:
        """
        ==============================================================================
        添加上下文
        ==============================================================================
        
        功能说明：
            为澄清追问添加对话上下文。
        
        参数说明：
            query: 用户查询文本
            conversation_state: 对话状态
        
        返回值：
            str: 添加上下文后的查询
        
        ==============================================================================
        """
        # 构建上下文
        context_parts = []
        
        if conversation_state.last_topic:
            context_parts.append(f"上一个话题: {conversation_state.last_topic}")
        
        if conversation_state.bazi_result:
            four_pillars = conversation_state.bazi_result.get("four_pillars", [])
            if four_pillars:
                bazi_info = self._build_bazi_info(four_pillars)
                context_parts.append(f"八字: {bazi_info}")
        
        # 构建完整查询
        if context_parts:
            context_str = "，".join(context_parts)
            return f"{query}（{context_str}）"
        
        return query

    def get_last_topic(
        self,
        conversation_state: ConversationContext
    ) -> str:
        """
        ==============================================================================
        获取上一个话题
        ==============================================================================
        
        功能说明：
            从对话状态中获取上一个话题。
        
        参数说明：
            conversation_state: 对话状态
        
        返回值：
            str: 上一个话题
        
        ==============================================================================
        """
        if conversation_state.last_topic:
            return conversation_state.last_topic
        
        if conversation_state.bazi_result:
            return "八字分析"
        
        return ""

    def update_conversation_state(
        self,
        conversation_state: ConversationContext,
        query: str,
        analysis_result: Dict[str, Any]
    ) -> ConversationContext:
        """
        ==============================================================================
        更新对话状态
        ==============================================================================
        
        功能说明：
            根据分析结果更新对话状态。
        
        参数说明：
            conversation_state: 对话状态
            query: 用户查询文本
            analysis_result: 分析结果
        
        返回值：
            ConversationContext: 更新后的对话状态
        
        ==============================================================================
        """
        # 更新轮数
        conversation_state.turn_count += 1
        
        # 更新搜索历史
        conversation_state.search_queries.append(query)
        
        # 更新上一个话题
        conversation_state.last_topic = self._extract_topic(query, analysis_result)
        
        # 更新八字结果
        if "bazi_result" in analysis_result:
            conversation_state.bazi_result = analysis_result["bazi_result"]
        
        # 更新五行分析
        if "wuxing_analysis" in analysis_result:
            conversation_state.wuxing_analysis = analysis_result["wuxing_analysis"]
        
        # 更新格局
        if "geju" in analysis_result:
            conversation_state.geju = analysis_result["geju"]
        
        # 更新喜用神
        if "yongshen" in analysis_result:
            conversation_state.yongshen = analysis_result["yongshen"]
        
        return conversation_state

    def _extract_topic(
        self,
        query: str,
        analysis_result: Dict[str, Any]
    ) -> str:
        """
        ==============================================================================
        提取话题
        ==============================================================================
        
        功能说明：
            从查询和分析结果中提取话题。
        
        参数说明：
            query: 用户查询文本
            analysis_result: 分析结果
        
        返回值：
            str: 话题
        
        ==============================================================================
        """
        # 从分析结果中提取
        if "intent" in analysis_result:
            intent = analysis_result["intent"]
            if intent == "FACT_QUERY":
                return "事实查询"
            elif intent == "INFERENCE":
                return "推理分析"
            elif intent == "COMPARISON":
                return "比较评估"
        
        # 从查询中提取
        if "格局" in query:
            return "格局分析"
        elif "喜用神" in query or "用神" in query:
            return "喜用神分析"
        elif "五行" in query:
            return "五行分析"
        elif "十神" in query:
            return "十神分析"
        
        return "一般咨询"
