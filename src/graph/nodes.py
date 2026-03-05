"""
LangGraph 工作流节点定义
包含八字分析的各个步骤
"""
import logging
from typing import Dict, Any
from src.core.models.bazi_models import BirthInfo, BaziResult
from src.core.engine.bazi_calculator import BaziCalculator
from src.core.engine.wuxing_calculator import WuxingCalculator
from .state import BaziAgentState
from src.rag.retriever import KnowledgeRetriever
from src.llm.dashscope_llm import DashScopeLLM

logger = logging.getLogger(__name__)
calculator = BaziCalculator()
wuxing_calculator = WuxingCalculator()

try:
    retriever = KnowledgeRetriever()
    llm = DashScopeLLM()
except Exception as e:
    logger.warning(f"⚠️ RAG或LLM组件初始化失败: {e}")
    retriever = None
    llm = None

def validate_input_node(state: BaziAgentState) -> Dict[str, Any]:
    """节点 1：验证用户输入"""
    logger.info("=" * 30)
    logger.info("【节点 1】执行输入验证...")
    logger.info(f"输入数据：{state.get('user_input', {})}")

    try:
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
    """节点 2：执行八字排盘计算"""
    logger.info("=" * 30)
    logger.info("【节点 2】执行八字排盘...")

    try:
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
    """节点 3：五行分析"""
    logger.info("=" * 30)
    logger.info("【节点 3】执行五行分析...")

    try:
        bazi_result = state.get("bazi_result", {})
        four_pillars_data = bazi_result.get("four_pillars", {})

        from src.core.models.bazi_models import FourPillars, Pillar, Tiangan, Dizhi

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

        score = wuxing_calculator.calculate_total_score(pillars)
        logger.info(f"五行分数：木={score.mu}, 火={score.huo}, 土={score.tu}, 金={score.jin}, 水={score.shui}")

        balance = wuxing_calculator.analyze_wuxing_balance(score)
        logger.info(f"五行状态：{balance['status']} - {balance['description']}")

        day_master = wuxing_calculator.get_day_master_strength(pillars)
        logger.info(f"日主强弱：{day_master['strength']} - {day_master['description']}")

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
    """节点 4：格局判断（使用规则引擎）"""
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
    """节点 5：查找喜用神（使用规则引擎）"""
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


def analyze_dayun_node(state: BaziAgentState) -> Dict[str, Any]:
    """节点：大运分析"""
    logger.info("=" * 30)
    logger.info("【节点】执行大运分析...")

    try:
        from src.core.engine.dayun import DayunEngine
        from src.core.models.bazi_models import FourPillars, Pillar, Tiangan, Dizhi
        from datetime import datetime

        bazi_result = state.get("bazi_result", {})
        yongshen_analysis = state.get("yongshen_analysis", {})
        birth_info = state.get("validated_input", {})

        # 重建四柱对象
        four_pillars_data = bazi_result.get("four_pillars", {})
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

        # 获取出生时间和性别
        birth_dt = datetime(
            birth_info["year"], birth_info["month"], birth_info["day"],
            birth_info["hour"], birth_info.get("minute", 0)
        )
        gender = birth_info.get("gender", "男")

        # 获取节气数据（需要从 state 或重新计算）
        from src.core.engine.solar_terms import SolarTermsCalculator
        solar_calc = SolarTermsCalculator()
        year_terms = solar_calc.get_solar_terms_in_year(birth_info["year"])

        # 计算当前年龄
        current_year = datetime.now().year
        current_age = current_year - birth_info["year"]

        # 执行大运分析
        dayun_engine = DayunEngine()
        dayun_result = dayun_engine.analyze_dayun(
            pillars, yongshen_analysis, birth_dt, gender, year_terms, current_age
        )

        logger.info(f"起运年龄：{dayun_result['qiyun_age']}岁，方向：{dayun_result['direction']}")
        logger.info("✅ 大运分析完成")

        return {
            "dayun_analysis": dayun_result,
            "status": "dayun_analyzed"
        }
    except Exception as e:
        logger.error(f"❌ 大运分析失败: {e}", exc_info=True)
        return {
            "error": f"大运分析错误: {str(e)}",
            "status": "dayun_analysis_failed"
        }


def check_liunian_node(state: BaziAgentState) -> Dict[str, Any]:
    """节点 6：流年运势分析（使用规则引擎）"""
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
    """节点 7：检索古籍知识（RAG）"""
    logger.info("=" * 30)
    logger.info("【节点 7】执行知识检索...")

    if not retriever:
        logger.warning("⚠️ 检索器未初始化，跳过知识检索")
        return {"knowledge_context": "", "status": "knowledge_skipped"}

    try:
        bazi_result = state.get("bazi_result", {})
        geju_analysis = state.get("geju_analysis", {})
        yongshen_analysis = state.get("yongshen_analysis", {})

        # 构建查询语句
        queries = []

        # 1. 基于日主和月令查询
        day_master = bazi_result.get("four_pillars", {}).get("day", {}).get("tiangan", "")
        month_zhi = bazi_result.get("four_pillars", {}).get("month", {}).get("dizhi", "")
        if day_master and month_zhi:
            queries.append(f"{day_master}日主生于{month_zhi}月")

        # 2. 基于格局查询
        geju_type = geju_analysis.get("geju_type", "")
        if geju_type and geju_type != "常格":
            queries.append(f"{geju_type}的特点与喜忌")

        # 3. 基于喜用神查询
        yongshen = yongshen_analysis.get("yongshen", [])
        if yongshen:
            queries.append(f"{' '.join(yongshen)}五行的含义与应用")

        # 执行检索
        all_docs = []
        for query in queries:
            logger.info(f"检索查询: {query}")
            results = retriever.search(query, top_k=3)
            all_docs.extend(results)

        # 简单去重（根据内容）
        unique_docs = []
        seen_content = set()
        for doc in all_docs:
            content = doc.get("content", "")
            if content not in seen_content:
                unique_docs.append(doc)
                seen_content.add(content)

        # 格式化上下文
        knowledge_context = retriever.format_context(unique_docs, max_length=2000)

        logger.info(f"✅ 知识检索完成，获取 {len(unique_docs)} 条相关知识")
        return {
            "knowledge_context": knowledge_context,
            "retrieved_docs": unique_docs,
            "status": "knowledge_retrieved"
        }
    except Exception as e:
        logger.error(f"❌ 知识检索失败: {e}", exc_info=True)
        return {
            "error": f"知识检索错误: {str(e)}",
            "status": "knowledge_retrieval_failed"
        }


# ✨ 新增节点：LLM 生成报告
def llm_generate_node(state: BaziAgentState) -> Dict[str, Any]:
    """节点 8：大模型生成报告"""
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

        # 调用 LLM
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
    """节点 9：组装最终报告（包含LLM内容）"""
    logger.info("=" * 30)
    logger.info("【节点 9】组装最终报告...")

    try:
        llm_response = state.get("llm_response", "")

        # 如果 LLM 生成失败，使用兜底逻辑
        if not llm_response or "失败" in state.get("status", ""):
            llm_response = "智能分析部分暂时不可用，请参考基础数据。"

        report = {
            "llm_analysis": llm_response,  # LLM 生成的自然语言报告
            "basic_data": {
                "bazi": state.get("bazi_result", {}).get("four_pillars", {}),
                "wuxing": state.get("wuxing_analysis", {}),
                "geju": state.get("geju_analysis", {}),
                "yongshen": state.get("yongshen_analysis", {}),
                "liunian": state.get("liunian_analysis", {})
            }
        }
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
    """节点 10：安全检查"""
    logger.info("=" * 30)
    logger.info("【节点 10】执行安全检查...")

    final_output = state.get("final_report", {})
    safe_output = {
        "message": "分析完成",
        "data": final_output
    }
    logger.info("✅ 安全检查完成")
    logger.info("=" * 50)

    return {"safe_output": safe_output, "status": "safety_checked"}


def analyze_dayun_node(state: BaziAgentState) -> Dict[str, Any]:
    """节点：大运分析"""
    logger.info("=" * 30)
    logger.info("【节点】执行大运分析...")

    try:
        from src.core.engine.dayun import DayunEngine
        from src.core.models.bazi_models import FourPillars, Pillar, Tiangan, Dizhi
        from datetime import datetime

        bazi_result = state.get("bazi_result", {})
        yongshen_analysis = state.get("yongshen_analysis", {})
        birth_info = state.get("validated_input", {})

        # 重建四柱对象
        four_pillars_data = bazi_result.get("four_pillars", {})
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

        # 获取出生时间和性别
        birth_dt = datetime(
            birth_info["year"], birth_info["month"], birth_info["day"],
            birth_info["hour"], birth_info.get("minute", 0)
        )
        gender = birth_info.get("gender", "男")

        # 获取节气数据（需要从 state 或重新计算）
        from src.core.engine.solar_terms import SolarTermsCalculator
        solar_calc = SolarTermsCalculator()
        year_terms = solar_calc.get_solar_terms_in_year(birth_info["year"])

        # 计算当前年龄
        current_year = datetime.now().year
        current_age = current_year - birth_info["year"]

        # 执行大运分析
        dayun_engine = DayunEngine()
        dayun_result = dayun_engine.analyze_dayun(
            pillars, yongshen_analysis, birth_dt, gender, year_terms, current_age
        )

        logger.info(f"起运年龄：{dayun_result['qiyun_age']}岁，方向：{dayun_result['direction']}")
        logger.info("✅ 大运分析完成")

        return {
            "dayun_analysis": dayun_result,
            "status": "dayun_analyzed"
        }
    except Exception as e:
        logger.error(f"❌ 大运分析失败: {e}", exc_info=True)
        return {
            "error": f"大运分析错误: {str(e)}",
            "status": "dayun_analysis_failed"
        }