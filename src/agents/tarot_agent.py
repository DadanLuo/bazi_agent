# src/agents/tarot_agent.py
"""塔罗牌占卜 Agent — LangGraph 驱动的自主决策"""
import logging
from typing import Dict, Any, List

from src.agents.base import BaseAgent, SlotSchema
from src.core.contracts import UnifiedSession
from src.prompts.registry import PromptRegistry, TAROT_CONSTRAINTS

logger = logging.getLogger(__name__)


class TarotAgent(BaseAgent):
    """塔罗牌占卜 Agent"""

    @property
    def agent_id(self) -> str:
        return "tarot"

    @property
    def display_name(self) -> str:
        return "塔罗牌占卜"

    @property
    def slot_schema(self) -> SlotSchema:
        return SlotSchema({
            "question_type": {
                "required": True,
                "pattern": r"(爱情|事业|财运|综合|健康|学业|人际关系|其他)",
                "keywords": ["爱情", "事业", "财运", "综合", "健康", "学业", "人际关系", "其他"],
            },
            "spread_type": {
                "required": False,
                "pattern": r"(单张|三张|凯尔特十字|五张)",
                "keywords": ["单张", "三张", "凯尔特十字", "五张", "牌阵"],
            },
            "specific_question": {
                "required": False,
                "pattern": r".*",
                "keywords": ["问题", "想问", "关于", "想知道"],
            },
        })

    @property
    def intent_keywords(self) -> Dict[str, List[str]]:
        return {
            "NEW_ANALYSIS": [
                "塔罗", "占卜", "牌", "算牌", "抽牌", "塔罗牌", "塔罗占卜",
                "问塔罗", "塔罗预测", "塔罗解读", "帮我抽牌", "抽一张牌",
                "塔罗牌阵", "塔罗牌面",
            ],
            "FOLLOW_UP": [
                "这张牌", "解释一下", "什么意思", "代表什么",
                "为什么", "怎么理解", "详细说说",
                "牌面上", "这个符号", "那个图案",
            ],
            "TOPIC_SWITCH": [
                "换一个", "换个话题", "说说", "聊聊", "谈谈", "讲讲",
                "重新抽", "再抽一次", "换牌阵",
            ],
            "CLARIFICATION": [
                "什么意思", "为什么", "怎么", "如何", "哪个", "什么",
                "解释", "说明", "不清楚", "不明白",
            ],
            "GENERAL_QUERY": [
                "你好", "在吗", "谢谢", "感谢", "再见", "拜拜",
            ],
        }

    def get_domain_constraints(self) -> str:
        return TAROT_CONSTRAINTS

    async def handle_analysis(
        self,
        session: UnifiedSession,
        slots: Dict[str, Any],
        mode: str = "full",
    ) -> Dict[str, Any]:
        """执行塔罗牌占卜 — ReAct Agent 模式"""
        from src.graph.tarot_graph import tarot_app

        # 检查必要槽位
        missing = self.slot_schema.get_missing(slots)
        if missing:
            return {"response": "请告诉我您想占卜的方向（如：爱情、事业、财运、综合等）", "output": None}

        question_type = slots.get("question_type", "综合")
        spread_type = slots.get("spread_type", "")
        specific_question = slots.get("specific_question", "")

        # 构建初始 user message，让 LLM 理解任务
        user_msg = f"用户想进行塔罗牌占卜。\n问题类型：{question_type}\n"
        if specific_question:
            user_msg += f"具体问题：{specific_question}\n"
        if spread_type:
            user_msg += f"用户指定牌阵：{spread_type}\n"
        else:
            user_msg += "用户未指定牌阵，请你根据问题自主选择合适的牌阵。\n"
        user_msg += "\n请开始占卜流程。"

        graph_input = {
            "user_input": {
                "question_type": question_type,
                "spread_type": spread_type,
                "specific_question": specific_question,
            },
            "user_query": specific_question or f"{question_type}占卜",
            "messages": [{"role": "user", "content": user_msg}],
            "conversation_id": session.metadata.conversation_id,
            "user_id": session.metadata.user_id,
            "iteration": 0,
            "pending_tool_calls": [],
            "executor_state": {},
            "status": "initialized",
        }

        try:
            result = await tarot_app.ainvoke(graph_input)

            response = result.get("llm_response", "")
            if not response:
                response = "塔罗牌占卜完成，您可以继续追问了解更多。"

            return {
                "response": response,
                "output": result.get("tarot_result"),
                "drawn_cards": result.get("drawn_cards"),
                "graph_result": result,
            }
        except Exception as e:
            logger.error(f"塔罗牌占卜失败: {e}", exc_info=True)
            return {"response": f"占卜过程中出现错误: {str(e)}", "output": None}

    async def handle_followup(
        self,
        session: UnifiedSession,
        query: str,
    ) -> str:
        """处理塔罗牌追问"""
        from src.dependencies import llm

        tarot_context = self._build_tarot_context(session)

        if not tarot_context:
            return "目前还没有占卜记录，请先进行一次塔罗牌占卜吧。"

        prompt = PromptRegistry.render("tarot_follow_up", tarot_context=tarot_context, query=query)
        return await llm.acall(prompt)

    @staticmethod
    def _build_tarot_context(session: UnifiedSession) -> str:
        """从 session 中提取塔罗占卜结果构建上下文"""
        if not session.tarot_cache:
            return ""

        cache = session.tarot_cache
        parts = []

        # 牌阵信息
        spread_info = cache.spread_info
        if spread_info:
            parts.append(f"牌阵：{spread_info.get('name_cn', '未知')}")

        # 抽牌结果
        if cache.drawn_cards:
            parts.append("\n【抽牌结果】")
            for card in cache.drawn_cards:
                orientation_cn = "正位" if card.get("orientation") == "upright" else "逆位"
                parts.append(f"- {card.get('position_name', '')}: {card.get('card_name_cn', '')}（{orientation_cn}）")

        # 综合解读
        if cache.synthesis:
            parts.append(f"\n【综合解读】\n{cache.synthesis[:3000]}")

        return "\n".join(parts)
