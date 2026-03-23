# src/agents/bazi_agent.py
"""
八字 Agent — 从 chat_api.py 提取的八字分析和追问逻辑
"""
import logging
from typing import Dict, Any, List

from src.agents.base import BaseAgent, SlotSchema
from src.core.contracts import UnifiedSession
from src.core.city_coords import resolve_city_coords
from src.prompts.registry import PromptRegistry, BAZI_CONSTRAINTS

logger = logging.getLogger(__name__)

GENDER_TO_CHINESE = {"male": "男", "female": "女", "男": "男", "女": "女"}


class BaziAgent(BaseAgent):
    """八字命理分析 Agent"""

    @property
    def agent_id(self) -> str:
        return "bazi"

    @property
    def display_name(self) -> str:
        return "八字命理分析"

    @property
    def slot_schema(self) -> SlotSchema:
        return SlotSchema({
            "birth_year": {"required": True, "pattern": r"(\d{4})[年\-]", "keywords": ["出生", "年份", "年"]},
            "birth_month": {"required": True, "pattern": r"(\d{1,2})[月]", "keywords": ["月"]},
            "birth_day": {"required": True, "pattern": r"(\d{1,2})[日号]", "keywords": ["日", "号"]},
            "gender": {"required": True, "pattern": r"(男|女)", "keywords": ["性别", "男", "女"]},
            "birth_hour": {"required": False, "pattern": r"(\d{1,2})(?:点|时)", "keywords": ["点", "时"]},
            "birth_place": {"required": False, "pattern": r"(?:出生地|地点|在)([\u4e00-\u9fa5]{2,})", "keywords": ["出生地", "城市"]},
        })

    @property
    def intent_keywords(self) -> Dict[str, List[str]]:
        return {
            "NEW_ANALYSIS": [
                "分析一下", "算一下", "看看", "命理", "八字", "运势", "命运",
                "生辰八字", "排盘", "解读", "预测", "测算",
            ],
            "FOLLOW_UP": [
                "那", "然后", "接着", "继续", "还有", "再", "另外", "此外",
                "关于这个", "那这个", "具体", "详细", "进一步",
            ],
            "TOPIC_SWITCH": [
                "换一个", "换个话题", "说说", "聊聊", "谈谈", "讲讲",
            ],
            "CLARIFICATION": [
                "什么意思", "为什么", "怎么", "如何", "哪个", "什么",
                "解释", "说明",
            ],
            "GENERAL_QUERY": [
                "你好", "在吗", "谢谢", "感谢", "再见",
            ],
        }

    def get_domain_constraints(self) -> str:
        return BAZI_CONSTRAINTS

    async def handle_analysis(
        self,
        session: UnifiedSession,
        slots: Dict[str, Any],
        mode: str = "full",
    ) -> Dict[str, Any]:
        """执行八字排盘分析"""
        from src.dependencies import redis_cache, llm
        from src.graph.bazi_graph import app as bazi_app
        from src.graph.simple_graph import simple_app

        # 检查必要槽位
        missing = self.slot_schema.get_missing(slots)
        if missing:
            slot_names = {"birth_year": "出生年", "birth_month": "出生月", "birth_day": "出生日", "gender": "性别"}
            desc = [slot_names.get(s, s) for s in missing]
            return {"response": f"还需要以下信息：{', '.join(desc)}", "output": None}

        # 构建 birth_info
        gender_raw = slots.get("gender", "男")
        birth_info = {
            "year": slots.get("birth_year"),
            "month": slots.get("birth_month"),
            "day": slots.get("birth_day"),
            "hour": slots.get("birth_hour", 12),
            "gender": GENDER_TO_CHINESE.get(gender_raw, "男"),
        }
        if slots.get("longitude"):
            birth_info["longitude"] = slots["longitude"]
            birth_info["latitude"] = slots["latitude"]
        else:
            birth_place = slots.get("birth_place", "")
            coords = resolve_city_coords(birth_place)
            if coords:
                birth_info["longitude"] = coords[0]
                birth_info["latitude"] = coords[1]

        # 查 Redis 缓存
        if redis_cache:
            cached = redis_cache.get_bazi_result(birth_info)
            if cached and cached.get("bazi_result"):
                logger.info("命中八字 Redis 缓存")
                bazi_output = cached.get("final_report") or {}
                response = cached.get("llm_response", "") or bazi_output.get("report_text", "八字分析完成（缓存命中）。")
                return {"response": response, "output": bazi_output, "bazi_result": cached["bazi_result"]}

        # 调用 LangGraph
        graph_input = {
            "user_input": birth_info,
            "status": "initialized",
            "user_id": session.metadata.user_id,
            "conversation_id": session.metadata.conversation_id,
        }

        try:
            if mode == "simple":
                result = await simple_app.ainvoke(graph_input)
            else:
                result = await bazi_app.ainvoke(graph_input)

            bazi_output = None
            if result.get("bazi_result"):
                final_report = result.get("final_report")
                safe_output = result.get("safe_output")
                bazi_output = final_report if final_report else (safe_output if safe_output else None)

                # 回填 Redis
                if redis_cache:
                    redis_cache.cache_bazi_result(
                        birth_info=birth_info,
                        result={
                            "bazi_result": result.get("bazi_result"),
                            "final_report": bazi_output,
                            "llm_response": result.get("llm_response", ""),
                        },
                        ttl=7200,
                    )

            response = result.get("llm_response", "")
            if not response:
                if mode == "simple":
                    response = "八字排盘完成，您可以继续追问了解详细分析。"
                else:
                    report = result.get("final_report", {})
                    response = report.get("report_text", "八字分析完成。")

            return {
                "response": response,
                "output": bazi_output,
                "bazi_result": result.get("bazi_result"),
                "graph_result": result,
            }
        except Exception as e:
            logger.error(f"八字排盘失败: {e}", exc_info=True)
            return {"response": f"八字分析过程中出现错误: {str(e)}", "output": None}

    async def handle_followup(
        self,
        session: UnifiedSession,
        query: str,
    ) -> str:
        """处理八字相关追问"""
        from src.dependencies import llm, hybrid_retriever, context_skill, model_config
        from src.memory.summarizer import ConversationSummarizer

        max_tokens = model_config.get_max_history_tokens() if model_config else 30000

        # 会话摘要压缩
        if session.metadata.message_count > 10:
            try:
                summarizer = ConversationSummarizer(llm)
                openai_msgs = session.get_openai_format()
                summarizer.compress_conversation(openai_msgs, summary_threshold=10, keep_latest=5)
            except Exception as e:
                logger.warning(f"会话摘要失败: {e}")

        # RAG 检索
        retrieval_results = []
        try:
            retrieval_results = hybrid_retriever.retrieve(query) if hybrid_retriever else []
        except Exception as e:
            logger.warning(f"RAG 检索失败: {e}")

        # 构建上下文（兼容旧 context_skill 接口）
        try:
            # context_skill 需要旧 SessionData，这里构造兼容对象
            context_info = self._build_context_compat(session, query, retrieval_results, context_skill, max_tokens)
        except Exception as e:
            logger.warning(f"上下文构建失败: {e}")
            context_info = {"context_text": ""}

        # 构建 bazi_context
        bazi_context = self._build_bazi_context(session)

        # 使用 PromptRegistry
        full_context = context_info.get("context_text", "") + bazi_context
        prompt = PromptRegistry.render("follow_up", context=full_context, query=query)

        return await llm.acall(prompt)

    # ---- 内部辅助 ----

    @staticmethod
    def _build_bazi_context(session: UnifiedSession) -> str:
        """从 session 中提取四柱数据构建 LLM 上下文"""
        if not session.bazi_cache or not session.bazi_cache.bazi_data:
            return ""

        bazi_data = session.bazi_cache.bazi_data
        analysis_result = session.bazi_cache.analysis_result or {}

        bazi_info = ""
        if isinstance(bazi_data, dict):
            four_pillars = bazi_data.get("four_pillars", {})
            if four_pillars:
                bazi_info = "\n【四柱八字】\n"
                pillar_names = {"year": "年柱", "month": "月柱", "day": "日柱", "hour": "时柱"}
                for pname in ["year", "month", "day", "hour"]:
                    pillar = four_pillars.get(pname, {})
                    if isinstance(pillar, dict):
                        tg_raw = pillar.get("tiangan", "?")
                        dz_raw = pillar.get("dizhi", "?")
                        tg = tg_raw.get("value", tg_raw) if isinstance(tg_raw, dict) else str(tg_raw)
                        dz = dz_raw.get("value", dz_raw) if isinstance(dz_raw, dict) else str(dz_raw)
                    else:
                        tg, dz = "?", "?"
                    bazi_info += f"{pillar_names[pname]}: {tg}{dz}  "

        report_text = ""
        if isinstance(analysis_result, dict):
            report_text = analysis_result.get("llm_analysis", "") or analysis_result.get("report_text", "")

        result = f"\n\n--- 用户八字分析结果 ---\n{bazi_info}"
        if report_text:
            result += f"\n\n--- AI 分析报告 ---\n{report_text[:5000]}"
        return result

    @staticmethod
    def _build_context_compat(session, query, retrieval_results, context_skill, max_tokens):
        """兼容旧 ContextSkill 接口 — 将 UnifiedSession 转为旧 SessionData"""
        try:
            from src.storage.models import SessionData, Message, MessageRole, ConversationMetadata
            old_messages = [
                Message(role=MessageRole(m.role if isinstance(m.role, str) else m.role.value), content=m.content)
                for m in session.messages
            ]
            meta = session.metadata
            old_session = SessionData(
                conversation_id=meta.conversation_id,
                user_id=meta.user_id,
                messages=old_messages,
                metadata=ConversationMetadata(
                    conversation_id=meta.conversation_id,
                    user_id=meta.user_id,
                    message_count=meta.message_count,
                    token_count=meta.token_count,
                    context_strategy=meta.context_strategy,
                    retrieval_mode=meta.retrieval_mode,
                ),
            )
            return context_skill.build_context(
                session_data=old_session,
                user_query=query,
                retrieval_results=retrieval_results,
                max_tokens=max_tokens,
            )
        except Exception:
            return {"context_text": ""}
