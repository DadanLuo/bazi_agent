# src/agents/tarot_tools.py
"""塔罗牌 Agent Tools — 供 ReAct Agent Loop 调用的工具集"""
import hashlib
import json
import logging
import random
from datetime import datetime
from typing import Dict, Any, List, Optional

from src.core.tarot_data import (
    FULL_DECK, SPREADS, QUESTION_SPREAD_MAP, Orientation,
)

logger = logging.getLogger(__name__)


# ========== Tool Schema（OpenAI function calling 格式）==========

TAROT_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "select_spread",
            "description": "根据用户的问题类型和需求，选择合适的塔罗牌阵。可选牌阵：single(单张,1张), three_card(三张,过去/现在/未来), five_card(五张,现状/挑战/建议/环境/结果), celtic_cross(凯尔特十字,10张,最全面)。你应该根据问题的复杂度和深度自主判断使用哪个牌阵。",
            "parameters": {
                "type": "object",
                "properties": {
                    "spread_id": {
                        "type": "string",
                        "enum": ["single", "three_card", "five_card", "celtic_cross"],
                        "description": "牌阵ID。简单问题用single，一般问题用three_card，需要深入分析用five_card，重大决策用celtic_cross"
                    },
                    "reason": {
                        "type": "string",
                        "description": "选择该牌阵的理由，简要说明"
                    }
                },
                "required": ["spread_id", "reason"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "draw_cards",
            "description": "根据已选择的牌阵，从78张塔罗牌中随机抽牌。每张牌会随机决定正位或逆位。必须先调用select_spread选择牌阵后才能抽牌。",
            "parameters": {
                "type": "object",
                "properties": {
                    "spread_id": {
                        "type": "string",
                        "description": "已选择的牌阵ID"
                    }
                },
                "required": ["spread_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "interpret_single_card",
            "description": "对单张已抽出的塔罗牌进行深度解读。结合牌的含义、正逆位、在牌阵中的位置以及用户的问题进行分析。可以对任意一张已抽出的牌调用此工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "card_index": {
                        "type": "integer",
                        "description": "要解读的牌在抽牌结果中的索引（从0开始）"
                    },
                    "focus": {
                        "type": "string",
                        "description": "解读的侧重点，如'爱情方面的含义'、'与其他牌的关联'等。可选。"
                    }
                },
                "required": ["card_index"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "retrieve_knowledge",
            "description": "从塔罗牌知识库中检索相关知识，用于补充解读。当需要更专业的牌义解释、牌阵组合含义、或特定领域的塔罗知识时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "检索查询，如'愚者正位在爱情中的含义'、'三张牌阵过去现在未来的关联解读方法'"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "synthesize_reading",
            "description": "综合所有已抽出的牌和解读，生成完整的占卜报告。应在完成所有单牌解读后调用。会将所有牌的含义串联起来，给出整体分析和建议。",
            "parameters": {
                "type": "object",
                "properties": {
                    "question_type": {
                        "type": "string",
                        "description": "用户的问题类型：爱情、事业、财运、健康、学业、人际关系、综合"
                    },
                    "specific_question": {
                        "type": "string",
                        "description": "用户的具体问题"
                    }
                },
                "required": ["question_type"]
            }
        }
    },
]


# ========== Tool 执行器 ==========

class TarotToolExecutor:
    """塔罗牌工具执行器 — 维护单次占卜的状态"""

    def __init__(self, conversation_id: str = ""):
        self.conversation_id = conversation_id
        self.spread_info: Optional[Dict] = None
        self.drawn_cards: List[Dict] = []
        self.card_interpretations: List[Dict] = []
        self.synthesis: str = ""
        self.knowledge_context: str = ""

    def execute(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """执行工具，返回结果文本"""
        handler = {
            "select_spread": self._select_spread,
            "draw_cards": self._draw_cards,
            "interpret_single_card": self._interpret_single_card,
            "retrieve_knowledge": self._retrieve_knowledge,
            "synthesize_reading": self._synthesize_reading,
        }.get(tool_name)

        if not handler:
            return f"未知工具: {tool_name}"

        try:
            return handler(arguments)
        except Exception as e:
            logger.error(f"工具 {tool_name} 执行失败: {e}", exc_info=True)
            return f"工具执行失败: {str(e)}"

    def _select_spread(self, args: Dict) -> str:
        spread_id = args.get("spread_id", "three_card")
        if spread_id not in SPREADS:
            return f"无效的牌阵ID: {spread_id}，可选: {list(SPREADS.keys())}"

        spread = SPREADS[spread_id]
        self.spread_info = {
            "id": spread.id,
            "name_cn": spread.name_cn,
            "card_count": spread.card_count,
            "positions": [
                {"index": p.index, "name": p.name, "description": p.description}
                for p in spread.positions
            ],
            "description": spread.description,
        }

        positions_desc = "、".join([f"{p.name}({p.description})" for p in spread.positions])
        return (
            f"已选择【{spread.name_cn}】牌阵，共{spread.card_count}张牌。\n"
            f"牌位：{positions_desc}\n"
            f"说明：{spread.description}\n"
            f"请调用 draw_cards 进行抽牌。"
        )

    def _draw_cards(self, args: Dict) -> str:
        spread_id = args.get("spread_id", "")
        if not self.spread_info:
            if spread_id and spread_id in SPREADS:
                self._select_spread({"spread_id": spread_id})
            else:
                return "请先调用 select_spread 选择牌阵"

        card_count = self.spread_info["card_count"]
        positions = self.spread_info["positions"]

        # 生成随机种子
        seed_str = f"{self.conversation_id}:{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        seed = int(hashlib.md5(seed_str.encode()).hexdigest()[:8], 16)
        rng = random.Random(seed)

        # 抽牌
        deck_indices = list(range(len(FULL_DECK)))
        rng.shuffle(deck_indices)
        selected = deck_indices[:card_count]

        self.drawn_cards = []
        result_lines = [f"🔮 {self.spread_info['name_cn']}抽牌结果：\n"]

        for i, card_idx in enumerate(selected):
            card = FULL_DECK[card_idx]
            orientation = Orientation.UPRIGHT if rng.random() > 0.35 else Orientation.REVERSED
            pos = positions[i] if i < len(positions) else {"name": f"位置{i+1}", "index": i, "description": ""}

            card_data = {
                "card_id": card.id,
                "card_name_cn": card.name_cn,
                "card_name_en": card.name_en,
                "suit": card.suit.value,
                "number": card.number,
                "orientation": orientation.value,
                "position_name": pos["name"],
                "position_index": pos.get("index", i),
                "position_description": pos.get("description", ""),
                "upright_keywords": card.upright_keywords,
                "reversed_keywords": card.reversed_keywords,
                "description": card.description,
            }
            self.drawn_cards.append(card_data)

            orient_cn = "正位" if orientation == Orientation.UPRIGHT else "逆位"
            keywords = card.upright_keywords if orientation == Orientation.UPRIGHT else card.reversed_keywords
            result_lines.append(
                f"📌 [{pos['name']}] {card.name_cn}（{orient_cn}）\n"
                f"   关键词：{'、'.join(keywords)}\n"
                f"   牌面：{card.description}\n"
                f"   位置含义：{pos.get('description', '')}\n"
            )

        result_lines.append("抽牌完成。你可以逐张调用 interpret_single_card 进行解读，也可以直接调用 synthesize_reading 进行综合解读。")
        return "\n".join(result_lines)

    def _interpret_single_card(self, args: Dict) -> str:
        card_index = args.get("card_index", 0)
        if not self.drawn_cards:
            return "还没有抽牌，请先调用 draw_cards"
        if card_index < 0 or card_index >= len(self.drawn_cards):
            return f"无效的牌索引: {card_index}，当前共{len(self.drawn_cards)}张牌（索引0-{len(self.drawn_cards)-1}）"

        card = self.drawn_cards[card_index]
        orient_cn = "正位" if card["orientation"] == "upright" else "逆位"
        keywords = card["upright_keywords"] if card["orientation"] == "upright" else card["reversed_keywords"]
        focus = args.get("focus", "")

        # 返回牌的详细信息供 LLM 自行解读
        info = (
            f"【{card['position_name']}】{card['card_name_cn']}（{orient_cn}）\n"
            f"英文名：{card['card_name_en']}\n"
            f"花色：{card['suit']}\n"
            f"关键词：{'、'.join(keywords)}\n"
            f"牌面描述：{card['description']}\n"
            f"位置含义：{card['position_description']}\n"
        )
        if focus:
            info += f"解读侧重：{focus}\n"

        info += "\n请基于以上信息给出这张牌在当前位置的解读。"
        return info

    def _retrieve_knowledge(self, args: Dict) -> str:
        """RAG 知识检索 — 占位实现，后续接入知识图谱"""
        query = args.get("query", "")
        logger.info(f"知识检索（占位）: {query}")
        # 后续替换为实际的知识图谱/向量检索
        self.knowledge_context += f"\n[检索: {query}] — 知识库暂未接入，请基于自身塔罗牌知识进行解读。"
        return "知识库暂未接入，请基于你的塔罗牌专业知识进行解读。后续版本将接入知识图谱提供更丰富的参考资料。"

    def _synthesize_reading(self, args: Dict) -> str:
        if not self.drawn_cards:
            return "还没有抽牌，请先完成抽牌流程"

        question_type = args.get("question_type", "综合")
        specific_question = args.get("specific_question", "")

        # 组装所有牌的信息
        cards_summary = []
        for card in self.drawn_cards:
            orient_cn = "正位" if card["orientation"] == "upright" else "逆位"
            keywords = card["upright_keywords"] if card["orientation"] == "upright" else card["reversed_keywords"]
            cards_summary.append(
                f"[{card['position_name']}] {card['card_name_cn']}（{orient_cn}）— 关键词：{'、'.join(keywords)}"
            )

        info = (
            f"请综合以下所有牌的含义，生成完整的占卜报告：\n\n"
            f"牌阵：{self.spread_info['name_cn']}\n"
            f"问题类型：{question_type}\n"
        )
        if specific_question:
            info += f"具体问题：{specific_question}\n"

        info += f"\n所有牌：\n" + "\n".join(cards_summary)
        info += "\n\n请给出：1）整体趋势 2）核心建议 3）需要注意的方面"

        return info

    def get_result(self) -> Dict[str, Any]:
        """获取最终结果，用于持久化到 session"""
        return {
            "spread_info": self.spread_info,
            "drawn_cards": self.drawn_cards,
            "card_interpretations": self.card_interpretations,
            "synthesis": self.synthesis,
            "knowledge_context": self.knowledge_context,
        }
