"""
==============================================================================
LangGraph 工作流节点定义
==============================================================================

功能说明：
    本模块定义了八字分析 LangGraph 工作流的所有节点，每个节点负责八字分析
    流程中的一个特定步骤。节点按照分析流程顺序执行，形成完整的八字分析链。

工作流节点：
    1. validate_input_node - 输入验证节点
    2. calculate_bazi_node - 八字排盘节点
    3. analyze_wuxing_node - 五行分析节点
    4. determine_geju_node - 格局判断节点
    5. find_yongshen_node - 喜用神查找节点
    6. check_liunian_node - 流年运势分析节点
    7. retrieve_knowledge_node - 知识检索节点
    8. llm_generate_node - LLM 生成节点
    9. generate_report_node - 报告生成节点
    10. safety_check_node - 安全检查节点
    11. agentic_rag_node - Agentic RAG 节点（新增）

==============================================================================
"""

import json
import logging
from typing import Dict, Any, List
from src.core.models.bazi_models import BirthInfo, BaziResult
from src.core.engine.bazi_calculator import BaziCalculator
from src.core.engine.wuxing_calculator import WuxingCalculator
from .state import BaziAgentState
from src.rag.retriever import KnowledgeRetriever
from src.rag.relevance import (
    build_bazi_query_plans,
    is_high_signal_doc,
    relax_where_condition,
    score_rag_doc,
    select_rag_documents,
)
from src.graph.report_trace import attach_traceability
from src.llm.dashscope_llm import DashScopeLLM
from src.safety.disclaimer import build_safety_policy
from src.safety.safety import SafetyChecker, SafetyInput, SafetyLevel
from src.safety.scene_strategy import SceneType

logger = logging.getLogger(__name__)

# 初始化核心引擎组件
calculator = BaziCalculator()
wuxing_calculator = WuxingCalculator()

# 尝试初始化 RAG、LLM 和安全检查器
try:
    retriever = KnowledgeRetriever()
    llm = DashScopeLLM()
    safety_checker = SafetyChecker()
except Exception as e:
    logger.warning(f"⚠️ RAG或LLM组件初始化失败: {e}")
    retriever = None
    llm = None
    safety_checker = None

# 尝试初始化 Agentic RAG 组件
try:
    from src.rag.agentic import (
        create_agentic_rag_graph,
        QueryAnalyzer,
        RetrievalPlanner,
        ResultEvaluator,
        ReflectionEngine,
        KnowledgeSynthesizer,
        QueryCompleter
    )
    agentic_rag_graph = create_agentic_rag_graph()
    logger.info("✅ Agentic RAG 图工作流初始化成功")
except ImportError as e:
    logger.warning(f"⚠️ Agentic RAG 组件初始化失败: {e}")
    agentic_rag_graph = None


def validate_input_node(state: BaziAgentState) -> Dict[str, Any]:
    """
    ==============================================================================
    节点 1：验证用户输入
    ==============================================================================
    
    功能说明：
        验证用户输入的出生信息是否符合要求。使用 Pydantic 模型进行数据验证，
        确保所有字段都符合预期格式和类型。
    
    参数说明：
        state (BaziAgentState): 当前工作流状态，包含：
            - user_input: 用户输入的出生信息
    
    返回值：
        Dict[str, Any]: 更新后的状态，包含：
            - validated_input: 验证后的出生信息
            - status: "input_validated" 或 "input_validation_failed"
            - error: 错误信息（如果验证失败）
    
    验证内容：
        - 出生年份：四位数字
        - 出生月份：1-12
        - 出生日期：1-31
        - 性别：男或女
        - 出生时辰：0-23（可选）
        - 出生地点：中文地名（可选）
    
    ==============================================================================
    """
    logger.info("=" * 30)
    logger.info("【节点 1】执行输入验证...")
    logger.info(f"输入数据：{state.get('user_input', {})}")

    try:
        # 使用 Pydantic 模型验证输入
        birth_info = BirthInfo(**state["user_input"])
        logger.info("✅ 输入验证通过")
        return {
            "validated_input": birth_info.model_dump(),
            "status": "input_validated"
        }
    except Exception as e:
        logger.error(f"❌ 输入验证失败：{e}")
        return {
            "error": f"输入格式错误：{str(e)}",
            "status": "input_validation_failed"
        }


def calculate_bazi_node(state: BaziAgentState) -> Dict[str, Any]:
    """
    ==============================================================================
    节点 2：执行八字排盘计算
    ==============================================================================
    
    功能说明：
        根据验证后的出生信息计算八字四柱（年柱、月柱、日柱、时柱）。
        使用八字计算引擎进行干支推算。
    
    参数说明：
        state (BaziAgentState): 当前工作流状态，包含：
            - validated_input: 验证后的出生信息
    
    返回值：
        Dict[str, Any]: 更新后的状态，包含：
            - bazi_result: 八字排盘结果
            - status: "calculation_completed" 或 "calculation_failed"
            - error: 错误信息（如果计算失败）
    
    计算内容：
        - 年柱：根据出生年份计算干支
        - 月柱：根据年干和月份计算干支（五虎遁）
        - 日柱：根据公历日期计算干支
        - 时柱：根据日干和时辰计算干支（五鼠遁）
    
    ==============================================================================
    """
    logger.info("=" * 30)
    logger.info("【节点 2】执行八字排盘...")

    try:
        # 使用验证后的输入计算八字
        birth_info = BirthInfo(**state["validated_input"])
        result = calculator.calculate(birth_info)
        logger.info(f"✅ 八字排盘完成")
        return {
            "bazi_result": result.model_dump(),
            "status": "calculation_completed"
        }
    except Exception as e:
        logger.error(f"❌ 排盘计算失败：{e}", exc_info=True)
        return {
            "error": f"排盘计算错误：{str(e)}",
            "status": "calculation_failed"
        }


def analyze_wuxing_node(state: BaziAgentState) -> Dict[str, Any]:
    """
    ==============================================================================
    节点 3：五行分析
    ==============================================================================
    
    功能说明：
        分析八字中五行的分布情况，计算五行分数，判断五行平衡状态，
        并评估日主强弱。
    
    参数说明：
        state (BaziAgentState): 当前工作流状态，包含：
            - bazi_result: 八字排盘结果
    
    返回值：
        Dict[str, Any]: 更新后的状态，包含：
            - wuxing_analysis: 五行分析结果
            - status: "wuxing_analyzed" 或 "wuxing_analysis_failed"
            - error: 错误信息（如果分析失败）
    
    分析内容：
        1. 五行分数计算：
           - 天干五行：每个天干计 100 分
           - 地支五行：按藏干权重分配
        2. 五行平衡分析：
           - 判断五行是否缺失
           - 判断五行过旺或过弱
        3. 日主强弱评估：
           - 根据五行分数和月令判断
           - 提供强、弱、中等三种评估
    
    ==============================================================================
    """
    logger.info("=" * 30)
    logger.info("【节点 3】执行五行分析...")

    try:
        bazi_result = state.get("bazi_result", {})
        four_pillars_data = bazi_result.get("four_pillars", {})

        from src.core.models.bazi_models import FourPillars, Pillar, Tiangan, Dizhi

        # 重建四柱对象
        pillars = FourPillars(
            year=Pillar(
                tiangan=Tiangan(four_pillars_data["year"]["tiangan"]),
                dizhi=Dizhi(four_pillars_data["year"]["dizhi"])
            ),
            month=Pillar(
                tiangan=Tiangan(four_pillars_data["month"]["tiangan"]),
                dizhi=Dizhi(four_pillars_data["month"]["dizhi"])
            ),
            day=Pillar(
                tiangan=Tiangan(four_pillars_data["day"]["tiangan"]),
                dizhi=Dizhi(four_pillars_data["day"]["dizhi"])
            ),
            hour=Pillar(
                tiangan=Tiangan(four_pillars_data["hour"]["tiangan"]),
                dizhi=Dizhi(four_pillars_data["hour"]["dizhi"])
            )
        )

        # 计算五行分数
        score = wuxing_calculator.calculate_total_score(pillars)
        logger.info(f"五行分数：木={score.mu}, 火={score.huo}, 土={score.tu}, 金={score.jin}, 水={score.shui}")

        # 分析五行平衡
        balance = wuxing_calculator.analyze_wuxing_balance(score)
        logger.info(f"五行状态：{balance['status']} - {balance['description']}")

        # 评估日主强弱
        day_master = wuxing_calculator.get_day_master_strength(pillars)
        logger.info(f"日主强弱：{day_master['strength']} - {day_master['description']}")

        # 构建分析结果
        analysis = {
            "score": {
                "mu": score.mu,
                "huo": score.huo,
                "tu": score.tu,
                "jin": score.jin,
                "shui": score.shui,
                "total": score.total()
            },
            "balance": balance,
            "day_master": day_master,
            "description": f"日主{day_master['day_master']}({day_master['day_master_wx']}), {day_master['description']}"
        }

        logger.info("✅ 五行分析完成")
        return {
            "wuxing_analysis": analysis,
            "status": "wuxing_analyzed"
        }
    except Exception as e:
        logger.error(f"❌ 五行分析失败：{e}", exc_info=True)
        return {
            "error": f"五行分析错误：{str(e)}",
            "status": "wuxing_analysis_failed"
        }


def determine_geju_node(state: BaziAgentState) -> Dict[str, Any]:
    """
    ==============================================================================
    节点 4：格局判断（使用规则引擎）
    ==============================================================================
    
    功能说明：
        根据八字四柱和五行分析结果，判断命局的格局类型。
        使用格局判断引擎进行规则匹配。
    
    参数说明：
        state (BaziAgentState): 当前工作流状态，包含：
            - bazi_result: 八字排盘结果
            - wuxing_analysis: 五行分析结果
    
    返回值：
        Dict[str, Any]: 更新后的状态，包含：
            - geju_analysis: 格局判断结果
            - status: "geju_determined" 或 "geju_determination_failed"
            - error: 错误信息（如果判断失败）
    
    判断内容：
        1. 检查从格（特殊格局）
        2. 检查杂格（魁罡、金神等）
        3. 判断正格（八正格）：
           - 财格、官格、印格、食伤格
           - 从财、从官、从印、从食伤
           - 从强、从弱
    
    ==============================================================================
    """
    logger.info("=" * 30)
    logger.info("【节点 4】执行格局判断...")

    try:
        from src.core.engine.geju import GejuEngine
        from src.core.models.bazi_models import FourPillars, Pillar, Tiangan, Dizhi

        bazi_result = state.get("bazi_result", {})
        four_pillars_data = bazi_result.get("four_pillars", {})
        wuxing_analysis = state.get("wuxing_analysis", {})

        # 重建四柱对象
        pillars = FourPillars(
            year=Pillar(
                tiangan=Tiangan(four_pillars_data["year"]["tiangan"]),
                dizhi=Dizhi(four_pillars_data["year"]["dizhi"])
            ),
            month=Pillar(
                tiangan=Tiangan(four_pillars_data["month"]["tiangan"]),
                dizhi=Dizhi(four_pillars_data["month"]["dizhi"])
            ),
            day=Pillar(
                tiangan=Tiangan(four_pillars_data["day"]["tiangan"]),
                dizhi=Dizhi(four_pillars_data["day"]["dizhi"])
            ),
            hour=Pillar(
                tiangan=Tiangan(four_pillars_data["hour"]["tiangan"]),
                dizhi=Dizhi(four_pillars_data["hour"]["dizhi"])
            )
        )

        # 格局判断
        geju_engine = GejuEngine()
        day_master_strength = wuxing_analysis.get("day_master", {})
        geju_result = geju_engine.determine_geju(pillars, day_master_strength)

        logger.info(f"格局判断结果：{geju_result['geju_type']}")
        logger.info(f"格局描述：{geju_result.get('description', '')}")
        logger.info("✅ 格局判断完成")

        return {
            "geju_analysis": geju_result,
            "status": "geju_determined"
        }
    except Exception as e:
        logger.error(f"❌ 格局判断失败：{e}", exc_info=True)
        return {
            "error": f"格局判断错误：{str(e)}",
            "status": "geju_determination_failed"
        }


def find_yongshen_node(state: BaziAgentState) -> Dict[str, Any]:
    """
    ==============================================================================
    节点 5：查找喜用神（使用规则引擎）
    ==============================================================================
    
    功能说明：
        根据日主强弱、格局类型和调候需求，推导出命局的喜用神和忌神。
        使用喜用神推导引擎进行综合判断。
    
    参数说明：
        state (BaziAgentState): 当前工作流状态，包含：
            - bazi_result: 八字排盘结果
            - wuxing_analysis: 五行分析结果
            - geju_analysis: 格局判断结果
    
    返回值：
        Dict[str, Any]: 更新后的状态，包含：
            - yongshen_analysis: 喜用神推导结果
            - status: "yongshen_found" 或 "yongshen_finding_failed"
            - error: 错误信息（如果查找失败）
    
    推导逻辑：
        1. 根据日主强弱确定基本喜忌
        2. 根据格局类型调整喜用神
        3. 根据调候需求调整喜用神
        4. 综合得出最终喜用神
    
    ==============================================================================
    """
    logger.info("=" * 30)
    logger.info("【节点 5】执行喜用神查找...")

    try:
        from src.core.engine.yongshen import YongshenEngine
        from src.core.models.bazi_models import FourPillars, Pillar, Tiangan, Dizhi

        bazi_result = state.get("bazi_result", {})
        four_pillars_data = bazi_result.get("four_pillars", {})
        wuxing_analysis = state.get("wuxing_analysis", {})
        geju_analysis = state.get("geju_analysis", {})

        # 重建四柱对象
        pillars = FourPillars(
            year=Pillar(
                tiangan=Tiangan(four_pillars_data["year"]["tiangan"]),
                dizhi=Dizhi(four_pillars_data["year"]["dizhi"])
            ),
            month=Pillar(
                tiangan=Tiangan(four_pillars_data["month"]["tiangan"]),
                dizhi=Dizhi(four_pillars_data["month"]["dizhi"])
            ),
            day=Pillar(
                tiangan=Tiangan(four_pillars_data["day"]["tiangan"]),
                dizhi=Dizhi(four_pillars_data["day"]["dizhi"])
            ),
            hour=Pillar(
                tiangan=Tiangan(four_pillars_data["hour"]["tiangan"]),
                dizhi=Dizhi(four_pillars_data["hour"]["dizhi"])
            )
        )

        # 喜用神推导
        yongshen_engine = YongshenEngine()
        day_master_strength = wuxing_analysis.get("day_master", {})
        yongshen_result = yongshen_engine.determine_yongshen(
            pillars, day_master_strength, geju_analysis
        )

        logger.info(f"喜用神：{yongshen_result['yongshen']}, 忌神：{yongshen_result['jishen']}")
        logger.info(f"推导理由：{yongshen_result.get('reason', '')}")
        logger.info("✅ 喜用神查找完成")

        return {
            "yongshen_analysis": yongshen_result,
            "status": "yongshen_found"
        }
    except Exception as e:
        logger.error(f"❌ 喜用神查找失败：{e}", exc_info=True)
        return {
            "error": f"喜用神查找错误：{str(e)}",
            "status": "yongshen_finding_failed"
        }


def check_liunian_node(state: BaziAgentState) -> Dict[str, Any]:
    """
    ==============================================================================
    节点 6：流年运势分析（使用规则引擎）
    ==============================================================================
    
    功能说明：
        分析当前流年的运势，结合命局的喜用神，判断流年的吉凶趋势。
        提供流年的详细分析和建议。
    
    参数说明：
        state (BaziAgentState): 当前工作流状态，包含：
            - bazi_result: 八字排盘结果
            - yongshen_analysis: 喜用神推导结果
    
    返回值：
        Dict[str, Any]: 更新后的状态，包含：
            - liunian_analysis: 流年运势分析结果
            - status: "liunian_checked" 或 "liunian_checking_failed"
            - error: 错误信息（如果分析失败）
    
    分析内容：
        1. 计算当前流年干支
        2. 分析流年与命局的关系
        3. 判断流年吉凶（大吉、吉、平、凶、大凶）
        4. 提供流年运势分析和建议
    
    ==============================================================================
    """
    logger.info("=" * 30)
    logger.info("【节点 6】执行流年运势分析...")

    try:
        from src.core.engine.liunian import LiunianEngine
        from src.core.models.bazi_models import FourPillars, Pillar, Tiangan, Dizhi
        from datetime import datetime

        bazi_result = state.get("bazi_result", {})
        four_pillars_data = bazi_result.get("four_pillars", {})
        yongshen_analysis = state.get("yongshen_analysis", {})

        # 重建四柱对象
        pillars = FourPillars(
            year=Pillar(
                tiangan=Tiangan(four_pillars_data["year"]["tiangan"]),
                dizhi=Dizhi(four_pillars_data["year"]["dizhi"])
            ),
            month=Pillar(
                tiangan=Tiangan(four_pillars_data["month"]["tiangan"]),
                dizhi=Dizhi(four_pillars_data["month"]["dizhi"])
            ),
            day=Pillar(
                tiangan=Tiangan(four_pillars_data["day"]["tiangan"]),
                dizhi=Dizhi(four_pillars_data["day"]["dizhi"])
            ),
            hour=Pillar(
                tiangan=Tiangan(four_pillars_data["hour"]["tiangan"]),
                dizhi=Dizhi(four_pillars_data["hour"]["dizhi"])
            )
        )

        # 流年分析
        liunian_engine = LiunianEngine()
        current_year = datetime.now().year

        # 分析当前年份
        liunian_result = liunian_engine.analyze_liunian(
            pillars, yongshen_analysis, current_year
        )

        # 也可以分析未来 3 年
        # future_years = liunian_engine.analyze_multiple_years(
        #     pillars, yongshen_analysis, current_year, current_year + 3
        # )

        logger.info(f"流年：{liunian_result['ganzhi']}, 吉凶：{liunian_result['jixiong']['level']}")
        logger.info(f"流年分析：{liunian_result['analysis']}")
        logger.info(f"建议：{liunian_result['advice']}")
        logger.info("✅ 流年运势分析完成")

        return {
            "liunian_analysis": liunian_result,
            "status": "liunian_checked"
        }
    except Exception as e:
        logger.error(f"❌ 流年分析失败：{e}", exc_info=True)
        return {
            "error": f"流年分析错误：{str(e)}",
            "status": "liunian_checking_failed"
        }


def retrieve_knowledge_node(state: BaziAgentState) -> Dict[str, Any]:
    """
    ==============================================================================
    节点 7：检索古籍知识（RAG）
    ==============================================================================
    
    功能说明：
        根据八字分析结果，从知识库中检索相关的古籍知识和命理规则，
        为 LLM 生成报告提供参考依据。
    
    参数说明：
        state (BaziAgentState): 当前工作流状态，包含：
            - bazi_result: 八字排盘结果
            - geju_analysis: 格局判断结果
            - yongshen_analysis: 喜用神推导结果
    
    返回值：
        Dict[str, Any]: 更新后的状态，包含：
            - knowledge_context: 格式化的知识上下文
            - retrieved_docs: 检索到的相关文档
            - status: "knowledge_retrieved"、"knowledge_skipped" 或 "knowledge_retrieval_failed"
    
    检索策略：
        1. 基于日主和月令查询
        2. 基于格局查询
        3. 基于喜用神查询
    
    ==============================================================================
    """
    logger.info("=" * 30)
    logger.info("【节点 7】执行知识检索...")

    if not retriever:
        logger.warning("⚠️ 检索器未初始化，跳过知识检索")
        return {
            "knowledge_context": "",
            "retrieved_docs": [],
            "rag_info": {
                "status": "skipped",
                "reason": "检索器未初始化",
                "queries": [],
                "documents": [],
                "doc_count": 0
            },
            "status": "knowledge_skipped"
        }

    try:
        bazi_result = state.get("bazi_result", {})
        geju_analysis = state.get("geju_analysis", {})
        yongshen_analysis = state.get("yongshen_analysis", {})
        excluded_sources = {"treelist"}
        query_plans = build_bazi_query_plans(
            bazi_result=bazi_result,
            geju_analysis=geju_analysis,
            yongshen_analysis=yongshen_analysis,
        )

        if not query_plans:
            logger.info("未生成有效检索查询，跳过 RAG")
            return {
                "knowledge_context": "",
                "retrieved_docs": [],
                "rag_info": {
                    "status": "skipped",
                    "reason": "未生成有效检索查询",
                    "queries": [],
                    "documents": [],
                    "doc_count": 0
                },
                "status": "knowledge_skipped"
            }

        # 执行检索
        all_docs = []
        for plan in query_plans:
            query = plan.query
            where_condition = retriever.build_where_from_query(query)
            logger.info(f"检索查询: {query}")
            logger.info(f"检索过滤条件: {where_condition}")
            attempts = [
                (where_condition if where_condition else None, 4),
                (
                    relax_where_condition(
                        where_condition,
                        drop_topic=False,
                        drop_sub_topic=True,
                        drop_keywords=True,
                    )
                    if where_condition
                    else None,
                    5,
                ),
                (
                    relax_where_condition(
                        where_condition,
                        drop_topic=False,
                        drop_sub_topic=True,
                        drop_keywords=False,
                    )
                    if where_condition
                    else None,
                    6,
                ),
            ]

            route_docs = []
            seen_contents = set()
            seen_attempts = set()

            for current_where, top_k in attempts:
                attempt_key = (
                    json.dumps(current_where, ensure_ascii=False, sort_keys=True)
                    if current_where
                    else "__no_where__"
                )
                if attempt_key in seen_attempts:
                    continue
                seen_attempts.add(attempt_key)

                candidate_docs = retriever.search(query, top_k=top_k, where=current_where)
                high_signal_docs = [
                    doc
                    for doc in candidate_docs
                    if is_high_signal_doc(doc, plan, excluded_sources=excluded_sources)
                ]

                for doc in high_signal_docs:
                    content = doc.get("content", "")
                    if not content or content in seen_contents:
                        continue
                    enriched_doc = dict(doc)
                    enriched_doc["_route"] = plan.route
                    enriched_doc["_route_weight"] = plan.weight
                    enriched_doc["_tokens"] = plan.tokens
                    enriched_doc["_score"] = score_rag_doc(enriched_doc, plan)
                    route_docs.append(enriched_doc)
                    seen_contents.add(content)

                if len(route_docs) >= 3:
                    break

            logger.info("RAG 路由 %s 命中高信号片段 %s 条", plan.route, len(route_docs))
            all_docs.extend(route_docs)
        unique_docs = select_rag_documents(all_docs, max_docs=4, min_score=1.0, fallback_score=0.72)

        cleaned_docs = []
        for doc in unique_docs:
            cleaned_doc = {
                "evidence_id": f"rag-{len(cleaned_docs) + 1}",
                "content": doc.get("content", ""),
                "metadata": doc.get("metadata", {}),
                "distance": doc.get("distance"),
                "route": doc.get("_route"),
                "route_weight": doc.get("_route_weight"),
                "tokens": doc.get("_tokens", []),
                "score": doc.get("_score"),
            }
            cleaned_docs.append(cleaned_doc)

        # 格式化上下文
        knowledge_context = retriever.format_context(cleaned_docs, max_length=2800)

        logger.info(f"✅ 知识检索完成，获取 {len(cleaned_docs)} 条相关知识")
        return {
            "knowledge_context": knowledge_context,
            "retrieved_docs": cleaned_docs,
            "rag_info": {
                "status": "success" if cleaned_docs else "skipped",
                "reason": "" if cleaned_docs else "未命中相关知识片段",
                "queries": [f"[{plan.route}] {plan.query}" for plan in query_plans],
                "documents": cleaned_docs,
                "doc_count": len(cleaned_docs)
            },
            "status": "knowledge_retrieved"
        }
    except Exception as e:
        logger.error(f"❌ 知识检索失败: {e}", exc_info=True)
        return {
            "knowledge_context": "",
            "retrieved_docs": [],
            "rag_info": {
                "status": "failed",
                "reason": str(e),
                "queries": [f"[{plan.route}] {plan.query}" for plan in query_plans] if 'query_plans' in locals() else [],
                "documents": [],
                "doc_count": 0
            },
            "status": "knowledge_skipped"
        }


# ✨ 新增节点：LLM 生成报告
def llm_generate_node(state: BaziAgentState) -> Dict[str, Any]:
    """
    ==============================================================================
    节点 8：大模型生成报告
    ==============================================================================
    
    功能说明：
        调用大语言模型，结合八字分析结果和检索到的知识，生成自然语言的
        八字分析报告。这是整个分析流程的核心输出节点。
    
    参数说明：
        state (BaziAgentState): 当前工作流状态，包含：
            - bazi_result: 八字排盘结果
            - wuxing_analysis: 五行分析结果
            - geju_analysis: 格局判断结果
            - yongshen_analysis: 喜用神推导结果
            - liunian_analysis: 流年运势分析结果
            - knowledge_context: 检索到的知识上下文
    
    返回值：
        Dict[str, Any]: 更新后的状态，包含：
            - llm_response: LLM 生成的自然语言报告
            - status: "llm_generated"、"llm_skipped" 或 "llm_generation_failed"
    
    生成内容：
        1. 命局概述
        2. 四柱分析
        3. 五行分析
        4. 格局判断
        5. 喜用神分析
        6. 流年运势
        7. 综合建议
    
    ==============================================================================
    """
    logger.info("=" * 30)
    logger.info("【节点 8】执行大模型报告生成...")

    if not llm:
        logger.warning("⚠️ LLM未初始化，跳过智能生成")
        return {"llm_response": "系统配置错误，无法生成智能报告。", "status": "llm_skipped"}

    try:
        # 准备数据
        bazi_data = {
            "birth_info": state.get("bazi_result", {}).get("birth_info", {}),
            "four_pillars": state.get("bazi_result", {}).get("four_pillars", {}),
            "wuxing_analysis": state.get("wuxing_analysis", {}),
            "geju_analysis": state.get("geju_analysis", {}),
            "yongshen_analysis": state.get("yongshen_analysis", {}),
            "liunian_analysis": state.get("liunian_analysis", {})
        }

        knowledge_context = state.get("knowledge_context", "")

        # 调用 LLM 生成报告
        report_content = llm.generate_bazi_report(bazi_data, knowledge_context)

        logger.info("✅ 大模型报告生成完成")
        return {
            "llm_response": report_content,
            "status": "llm_generated"
        }
    except Exception as e:
        logger.error(f"❌ LLM生成失败: {e}", exc_info=True)
        return {
            "error": f"LLM生成错误: {str(e)}",
            "status": "llm_generation_failed"
        }


# 原有的节点编号顺延
def generate_report_node(state: BaziAgentState) -> Dict[str, Any]:
    """
    ==============================================================================
    节点 9：组装最终报告（包含LLM内容）
    ==============================================================================
    
    功能说明：
        将 LLM 生成的自然语言报告和基础数据分析组装成最终的报告结构。
        如果 LLM 生成失败，使用兜底逻辑生成基础报告。
    
    参数说明：
        state (BaziAgentState): 当前工作流状态，包含：
            - llm_response: LLM 生成的自然语言报告
            - bazi_result: 八字排盘结果
            - wuxing_analysis: 五行分析结果
            - geju_analysis: 格局判断结果
            - yongshen_analysis: 喜用神推导结果
            - liunian_analysis: 流年运势分析结果
    
    返回值：
        Dict[str, Any]: 更新后的状态，包含：
            - final_report: 最终报告结构
            - status: "report_generated" 或 "report_generation_failed"
    
    报告结构：
        {
            "llm_analysis": "LLM 生成的自然语言报告",
            "basic_data": {
                "bazi": "四柱八字",
                "wuxing": "五行分析",
                "geju": "格局判断",
                "yongshen": "喜用神分析",
                "liunian": "流年运势"
            }
        }
    
    ==============================================================================
    """
    logger.info("=" * 30)
    logger.info("【节点 9】组装最终报告...")

    try:
        llm_response = state.get("llm_response", "")

        # 如果 LLM 生成失败，使用兜底逻辑
        if not llm_response or "失败" in state.get("status", ""):
            llm_response = "智能分析部分暂时不可用，请参考基础数据。"

        report = {
            "message": "分析完成",
            "time_info": state.get("bazi_result", {}).get("time_info", {}),
            "llm_analysis": llm_response,  # LLM 生成的自然语言报告
            "basic_data": {
                "bazi": state.get("bazi_result", {}).get("four_pillars", {}),
                "wuxing": state.get("wuxing_analysis", {}),
                "geju": state.get("geju_analysis", {}),
                "yongshen": state.get("yongshen_analysis", {}),
                "liunian": state.get("liunian_analysis", {}),
                "dayun": state.get("dayun_analysis", {})
            },
            "rag_info": state.get("rag_info", {
                "status": "skipped",
                "reason": "本次分析未使用知识检索",
                "queries": [],
                "documents": [],
                "doc_count": 0
            })
        }
        attach_traceability(report, state)
        logger.info("✅ 最终报告组装完成")
        return {
            "final_report": report,
            "status": "report_generated"
        }
    except Exception as e:
        logger.error(f"❌ 报告组装失败: {e}", exc_info=True)
        return {
            "error": f"报告组装错误: {str(e)}",
            "status": "report_generation_failed"
        }


def safety_check_node(state: BaziAgentState) -> Dict[str, Any]:
    """
    ==============================================================================
    节点 10：安全检查 - 集成输入和输出内容审核
    ==============================================================================
    
    功能说明：
        在报告生成完成后进行最终的安全检查，确保输出内容符合安全要求。
        包括用户输入审核和最终输出审核两部分。
    
    参数说明：
        state (BaziAgentState): 当前工作流状态，包含：
            - user_input: 用户原始输入
            - user_query: 用户查询文本
            - final_report: 最终报告
            - llm_response: LLM 生成的回复
    
    返回值：
        Dict[str, Any]: 更新后的状态，包含：
            - safe_output: 安全输出结果
            - status: "safety_checked" 或 "safety_blocked"
            - error: 错误信息（如果被阻断）
    
    安全检查流程：
        1. 检查用户原始输入
        2. 检查最终输出内容
        3. 如果通过审核，返回安全结果
        4. 如果被阻断，返回安全兜底回复
    
    ==============================================================================
    """
    logger.info("=" * 30)
    logger.info("【节点 10】执行安全检查...")
    
    # 检查用户原始输入
    user_input = state.get("user_input", {})
    user_query = state.get("user_query", "")
    
    if safety_checker and (user_input or user_query):
        # 检查用户输入
        input_text = user_query or str(user_input)
        input_result = safety_checker.check_scene_input(input_text, SceneType.BAZI)
        
        if input_result.blocked:
            logger.warning(f"❌ 用户输入被阻断: {input_result.matched_keywords}")
            return {
                "safe_output": {
                    "message": input_result.message,
                    "data": None,
                    "blocked": True,
                    "blocked_category": input_result.category.value if input_result.category else None,
                },
                "status": "safety_blocked",
                "error": input_result.message,
            }
        
        if input_result.level == SafetyLevel.WARNING:
            logger.warning(f"⚠️ 用户输入有风险: {input_result.matched_keywords}")
    
    # 检查最终输出
    final_output = state.get("final_report", {})
    llm_response = state.get("llm_response", "")
    
    if safety_checker and (final_output or llm_response):
        output_text = llm_response or str(final_output)
        output_result = safety_checker.check_scene_output(output_text, SceneType.BAZI)
        
        if output_result.blocked:
            logger.warning(f"❌ LLM输出被阻断: {output_result.matched_keywords}")
            safe_response = safety_checker.get_safe_response(
                output_result.category,
                SafetyLevel.BLOCK
            )
            sanitized_output = final_output.copy() if isinstance(final_output, dict) else {}
            if isinstance(sanitized_output, dict):
                sanitized_output["llm_analysis"] = safe_response
                sanitized_output["message"] = safe_response
            return {
                "safe_output": {
                    "message": safe_response,
                    "data": sanitized_output if sanitized_output else None,
                    "blocked": True,
                    "blocked_category": output_result.category.value if output_result.category else None,
                },
                "status": "safety_blocked",
                "error": "输出内容存在风险，已使用安全兜底回复",
            }
    
    # 通过安全检查
    if isinstance(final_output, dict):
        final_output = final_output.copy()
        final_output["safety_policy"] = build_safety_policy(SceneType.BAZI)

    safe_output = {
        "message": "分析完成",
        "data": final_output,
        "blocked": False,
    }
    logger.info("✅ 安全检查通过")
    logger.info("=" * 50)

    return {"safe_output": safe_output, "status": "safety_checked"}


def agentic_rag_node(state: BaziAgentState) -> Dict[str, Any]:
    """
    ==============================================================================
    节点 11：Agentic RAG 检索
    ==============================================================================
    
    功能说明：
        使用 Agentic RAG 工作流进行智能检索，支持多轮迭代优化。
    
    参数说明：
        state (BaziAgentState): 当前工作流状态，包含：
            - user_query: 用户查询文本
            - knowledge_context: 知识上下文（可选）
            - retrieved_docs: 检索到的文档（可选）
    
    返回值：
        Dict[str, Any]: 更新后的状态，包含：
            - knowledge_context: 检索到的知识上下文
            - retrieved_docs: 检索到的文档列表
            - reasoning_trace: 推理轨迹
            - status: "agentic_rag_completed" 或 "agentic_rag_failed"
    
    ==============================================================================
    """
    logger.info("=" * 30)
    logger.info("【节点 11】执行 Agentic RAG 检索...")
    
    try:
        # 获取查询
        query = state.get("user_query", "")
        if not query:
            logger.error("查询为空")
            return {
                "error": "查询不能为空",
                "status": "agentic_rag_failed"
            }
        
        # 检查 Agentic RAG 图是否可用
        if agentic_rag_graph is None:
            logger.warning("Agentic RAG 图不可用，使用传统检索")
            # 使用传统检索作为兜底
            if retriever:
                where_condition = retriever.build_where_from_query(query)
                docs = retriever.search(
                    query,
                    top_k=5,
                    where=where_condition if where_condition else None,
                )
                context = retriever.format_context(docs)
                logger.info("✅ 传统检索完成")
                return {
                    "knowledge_context": context,
                    "retrieved_docs": docs,
                    "reasoning_trace": [f"传统检索: {query}"],
                    "status": "agentic_rag_completed"
                }
            else:
                return {
                    "error": "检索器不可用",
                    "status": "agentic_rag_failed"
                }
        
        # 运行 Agentic RAG
        result = agentic_rag_graph.invoke({
            "original_query": query,
            "current_query": query,
            "graph_state": dict(state),
            "max_iterations": 3,
            "iteration": 0,
            "current_action": "analyze",
            "state": "initialized",
            "reasoning_trace": [f"开始查询: {query}"]
        })
        
        # 提取结果
        context = result.get("final_context", "")
        docs = result.get("retrieved_docs", [])
        trace = result.get("reasoning_trace", [])
        
        logger.info(f"✅ Agentic RAG 检索完成，状态: {result.get('state')}")
        
        return {
            "knowledge_context": context,
            "retrieved_docs": docs,
            "reasoning_trace": trace,
            "status": "agentic_rag_completed"
        }
        
    except Exception as e:
        logger.error(f"❌ Agentic RAG 检索失败: {e}")
        return {
            "error": f"Agentic RAG 检索失败: {str(e)}",
            "status": "agentic_rag_failed"
        }
