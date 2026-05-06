"""
==============================================================================
检索规划器
==============================================================================

功能说明：
    本模块实现了检索规划器，用于根据查询分析结果，制定最优的检索策略，
    包括选择检索工具、确定检索顺序、设置检索参数。

核心功能：
    - 制定检索计划：根据查询复杂度和意图选择策略
    - 简单查询计划：单一向量检索
    - 中等查询计划：向量 + BM25 混合检索
    - 复杂查询计划：多源检索 + 图谱增强

==============================================================================
"""

import logging
from typing import List, Dict, Any, Optional

from .state import QueryAnalysis, RetrievalPlan

logger = logging.getLogger(__name__)


class RetrievalPlanner:
    """
    ==============================================================================
    检索规划器
    ==============================================================================
    
    功能说明：
        根据查询分析结果，制定最优的检索策略，包括选择检索工具、
        确定检索顺序、设置检索参数。
    
    核心方法：
        - plan(): 制定检索计划
    
    检索策略：
        - 简单查询：单一向量检索
        - 中等查询：向量 + BM25 混合检索
        - 复杂查询：多源检索 + 图谱增强
    
    融合策略：
        - none: 不融合，使用单一结果
        - rrf: Reciprocal Rank Fusion
        - adaptive: 自适应权重融合
        - llm_rerank: LLM 重排序
    
    ==============================================================================
    """

    def __init__(self, max_iterations: int = 3):
        """
        ==============================================================================
        初始化检索规划器
        ==============================================================================
        
        参数说明：
            max_iterations: 最大迭代次数
        
        ==============================================================================
        """
        self.max_iterations = max_iterations
        logger.info(f"RetrievalPlanner 初始化完成，最大迭代次数: {max_iterations}")

    def plan(self, analysis: QueryAnalysis) -> RetrievalPlan:
        """
        ==============================================================================
        制定检索计划
        ==============================================================================
        
        功能说明：
            根据查询分析结果，制定最优的检索策略。
        
        参数说明：
            analysis: 查询分析结果
        
        返回值：
            RetrievalPlan: 检索计划
        
        处理流程：
            1. 根据复杂度选择策略
            2. 确定使用的检索工具
            3. 设置检索参数
            4. 选择融合策略
        
        ==============================================================================
        """
        logger.info(f"开始制定检索计划，复杂度: {analysis.complexity}")
        
        if analysis.complexity == "简单":
            return self._simple_plan(analysis)
        elif analysis.complexity == "中等":
            return self._medium_plan(analysis)
        else:
            return self._complex_plan(analysis)

    def _simple_plan(self, analysis: QueryAnalysis) -> RetrievalPlan:
        """
        ==============================================================================
        简单查询计划
        ==============================================================================
        
        功能说明：
            为简单查询制定检索计划，使用单一向量检索。
        
        参数说明：
            analysis: 查询分析结果
        
        返回值：
            RetrievalPlan: 检索计划
        
        ==============================================================================
        """
        logger.info("生成简单查询计划")
        
        return RetrievalPlan(
            tools=["vector"],
            order=["vector"],
            params={
                "top_k": 3,
                "threshold": 0.7,
                "filter": self._build_filter(analysis)
            },
            fusion_strategy="none",
            max_iterations=1
        )

    def _medium_plan(self, analysis: QueryAnalysis) -> RetrievalPlan:
        """
        ==============================================================================
        中等查询计划
        ==============================================================================
        
        功能说明：
            为中等查询制定检索计划，使用向量 + BM25 混合检索。
        
        参数说明：
            analysis: 查询分析结果
        
        返回值：
            RetrievalPlan: 检索计划
        
        ==============================================================================
        """
        logger.info("生成中等查询计划")
        
        return RetrievalPlan(
            tools=["vector", "bm25"],
            order=["vector", "bm25"],
            params={
                "top_k": 5,
                "threshold": 0.6,
                "filter": self._build_filter(analysis)
            },
            fusion_strategy="rrf",  # Reciprocal Rank Fusion
            max_iterations=2
        )

    def _complex_plan(self, analysis: QueryAnalysis) -> RetrievalPlan:
        """
        ==============================================================================
        复杂查询计划
        ==============================================================================
        
        功能说明：
            为复杂查询制定检索计划，使用多源检索 + 图谱增强。
        
        参数说明：
            analysis: 查询分析结果
        
        返回值：
            RetrievalPlan: 检索计划
        
        ==============================================================================
        """
        logger.info("生成复杂查询计划")
        
        return RetrievalPlan(
            tools=["vector", "bm25", "graph"],
            order=["graph", "vector", "bm25"],  # 图谱优先，因为需要实体信息
            params={
                "top_k": 10,
                "threshold": 0.5,
                "filter": self._build_filter(analysis)
            },
            fusion_strategy="adaptive",
            max_iterations=self.max_iterations
        )

    def _build_filter(self, analysis: QueryAnalysis) -> Dict[str, Any]:
        """
        ==============================================================================
        构建检索过滤器
        ==============================================================================
        
        功能说明：
            根据查询分析结果，构建检索过滤器，用于限制检索范围。
            充分利用丰富的元数据字段进行精确过滤。
        
        参数说明：
            analysis: 查询分析结果
        
        返回值：
            Dict[str, Any]: 过滤器
        
        ==============================================================================
        """
        filter_dict = {}
        
        # 如果有关键实体，尝试将其映射到八字领域特定的字段
        if analysis.key_entities:
            for entity in analysis.key_entities:
                # 检查是否为天干
                if entity in ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]:
                    filter_dict["tiangan"] = {"$contains": entity}
                # 检查是否为地支
                elif entity in ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]:
                    filter_dict["dizhi"] = {"$contains": entity}
                # 检查是否为五行
                elif entity in ["金", "木", "水", "火", "土"]:
                    filter_dict["wuxing"] = {"$contains": entity}
                # 检查是否为十神
                elif entity in ["正官", "七杀", "正财", "偏财", "食神", "伤官", "比肩", "劫财", "正印", "偏印"]:
                    filter_dict["shensha"] = {"$contains": entity}
                # 检查是否为格局
                elif "格" in entity:
                    filter_dict["geju"] = {"$contains": entity}
                # 检查是否为用神相关
                elif entity in ["用神", "喜神", "忌神", "仇神", "闲神"]:
                    filter_dict["yongshen"] = {"$contains": entity}
                # 检查是否为流年相关
                elif entity in ["流年", "大运", "小运", "岁运", "太岁"]:
                    filter_dict["liunian"] = {"$contains": entity}
                # 检查是否为长生十二神
                elif entity in ["长生", "沐浴", "冠带", "临官", "帝旺", "衰", "病", "死", "墓", "绝", "胎", "养"]:
                    filter_dict["changsheng"] = {"$contains": entity}
        
        # 根据意图类型添加过滤
        if analysis.intent == "FACT_QUERY":
            filter_dict["chunk_type"] = "theory"  # 事实查询偏向理论
        elif analysis.intent == "INFERENCE":
            filter_dict["chunk_type"] = "rule"  # 推理查询偏向规则
        elif analysis.intent == "COMPARISON":
            filter_dict["chunk_type"] = "example"  # 比较查询偏向示例
        
        # 根据主题添加过滤（如果分析中包含主题信息）
        topic_keywords = {
            "格局": ["格局", "成格", "破格", "正官格", "财格", "印格", "食神格", "七杀格"],
            "用神": ["用神", "喜神", "忌神", "调候", "扶抑", "通关"],
            "五行": ["五行", "生克", "制化", "旺衰", "强弱"],
            "神煞": ["神煞", "贵人", "桃花", "驿马", "华盖", "文昌"],
            "流年": ["流年", "大运", "小运", "岁运", "太岁"],
            "十神": ["十神", "正官", "七杀", "正财", "偏财", "食神", "伤官", "比肩", "劫财", "正印", "偏印"],
            "长生": ["长生", "沐浴", "冠带", "临官", "帝旺", "衰", "病", "死", "墓", "绝", "胎", "养"]
        }
        
        # 检查查询文本中是否包含特定主题关键词
        query_text = getattr(analysis, 'query_text', '') if hasattr(analysis, 'query_text') else ''
        if query_text:
            for topic, keywords in topic_keywords.items():
                if any(kw in query_text for kw in keywords):
                    filter_dict["topic"] = topic
                    break
        
        return filter_dict

    def adjust_plan(
        self,
        plan: RetrievalPlan,
        reflection: Optional[Dict[str, Any]] = None
    ) -> RetrievalPlan:
        """
        ==============================================================================
        调整检索计划
        ==============================================================================
        
        功能说明：
            根据反思结果，调整检索计划。
        
        参数说明：
            plan: 原始检索计划
            reflection: 反思结果
        
        返回值：
            RetrievalPlan: 调整后的检索计划
        
        ==============================================================================
        """
        logger.info("调整检索计划")
        
        if not reflection:
            return plan
        
        # 获取调整建议
        adjustment = reflection.get("strategy_adjustment", {})
        action = adjustment.get("action", "")
        
        if action == "query_rewrite":
            # 查询重写：调整阈值
            new_params = plan.params.copy()
            new_params["threshold"] = max(0.5, plan.params.get("threshold", 0.6) - 0.1)
            return RetrievalPlan(
                tools=plan.tools,
                order=plan.order,
                params=new_params,
                fusion_strategy=plan.fusion_strategy,
                max_iterations=plan.max_iterations
            )
        
        elif action == "query_expand":
            # 查询扩展：增加 top_k
            new_params = plan.params.copy()
            new_params["top_k"] = plan.params.get("top_k", 5) + 3
            return RetrievalPlan(
                tools=plan.tools,
                order=plan.order,
                params=new_params,
                fusion_strategy=plan.fusion_strategy,
                max_iterations=plan.max_iterations
            )
        
        elif action == "adjust_params":
            # 参数调整
            new_params = plan.params.copy()
            new_params.update(adjustment.get("params", {}))
            return RetrievalPlan(
                tools=plan.tools,
                order=plan.order,
                params=new_params,
                fusion_strategy=plan.fusion_strategy,
                max_iterations=plan.max_iterations
            )
        
        elif action == "switch_source":
            # 切换知识源
            new_tools = ["vector", "bm25"]
            if "graph" not in plan.tools:
                new_tools.append("graph")
            return RetrievalPlan(
                tools=new_tools,
                order=new_tools,
                params=plan.params,
                fusion_strategy=plan.fusion_strategy,
                max_iterations=plan.max_iterations
            )
        
        return plan
