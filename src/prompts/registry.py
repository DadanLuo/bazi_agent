# src/prompts/registry.py
"""
Prompt 模板注册表 — 集中管理所有 LLM prompt，替代内联 f-string
"""
from typing import Dict, Optional


# ========== 领域约束（唯一定义）==========

BAZI_CONSTRAINTS = (
    "【重要约束】如果上下文中包含【四柱八字】，该数据是经过精确万年历算法排出的确定结果，"
    "你必须严格使用这些四柱数据进行分析，绝对禁止自行重新推导或修改四柱排盘。"
    "如果你的推算结果与上述四柱不一致，以上述四柱为准。"
)

TAROT_CONSTRAINTS = (
    "【重要约束】你是一位专业的塔罗牌占卜师，需要根据塔罗牌的牌面画面和传统解读为用户提供准确的占卜服务。\n"
    "规则：\n"
    "1. 必须基于已抽出的塔罗牌进行解读，不能凭空编造或更换牌面\n"
    "2. 解读时要结合用户的具体问题、牌的位置含义和正逆位\n"
    "3. 保持专业但温和的语调，避免过于绝对的预测\n"
    "4. 如果涉及心理健康问题，要提供积极正面的建议\n"
    "5. 严格遵守中国法律法规，不涉及迷信和违法内容\n"
    "6. 大阿卡纳（22张）代表人生重大课题，小阿卡纳（56张）代表日常事件\n"
    "7. 正位/逆位含义不同，必须区分解读"
)


class PromptTemplate:
    """带变量注入和约束拼接的 prompt 模板"""

    def __init__(self, name: str, template: str, constraints: Optional[str] = None):
        self.name = name
        self.template = template
        self.constraints = constraints or ""

    def render(self, **kwargs) -> str:
        text = self.template.format(**kwargs)
        if self.constraints:
            text += f"\n\n{self.constraints}"
        return text


class PromptRegistry:
    """中央 prompt 注册表"""
    _templates: Dict[str, PromptTemplate] = {}

    @classmethod
    def register(cls, name: str, template: str, constraints: Optional[str] = None):
        cls._templates[name] = PromptTemplate(name, template, constraints)

    @classmethod
    def get(cls, name: str) -> PromptTemplate:
        if name not in cls._templates:
            raise KeyError(f"Prompt template '{name}' not registered")
        return cls._templates[name]

    @classmethod
    def render(cls, name: str, **kwargs) -> str:
        return cls.get(name).render(**kwargs)


# ========== 预注册模板 ==========

PromptRegistry.register(
    "follow_up",
    "基于以下对话上下文和检索知识，回答用户的追问：\n\n"
    "上下文：\n{context}\n\n"
    "用户追问：{query}\n\n"
    "请结合之前的八字分析结果和对话内容，提供连贯、专业的回答。",
    constraints=BAZI_CONSTRAINTS,
)

PromptRegistry.register(
    "topic_switch",
    "用户切换了话题。基于以下精简上下文回答新问题：\n\n"
    "上下文：\n{context}\n\n"
    "新问题：{query}\n\n"
    "请自然地回应新话题，提供专业的回答。",
    constraints=BAZI_CONSTRAINTS,
)

PromptRegistry.register(
    "clarification",
    "用户在请求澄清。基于最近的对话回答：\n\n"
    "最近对话：\n{context}\n\n"
    "澄清问题：{query}\n\n"
    "请针对用户的疑问，给出清晰、具体的解释。",
    constraints=BAZI_CONSTRAINTS,
)

PromptRegistry.register(
    "general_query",
    "基于以下上下文，回答用户问题：\n\n"
    "上下文：\n{context}\n\n"
    "用户问题：{query}\n\n"
    "请提供专业、准确的回答。",
    constraints=BAZI_CONSTRAINTS,
)


# ========== 塔罗牌模板 ==========

PromptRegistry.register(
    "tarot_card_interpret",
    "请对以下塔罗牌进行解读：\n\n"
    "牌名：{card_name}（{orientation}）\n"
    "牌阵位置：{position_name} — {position_description}\n"
    "关键词：{keywords}\n"
    "牌面描述：{card_description}\n\n"
    "用户问题类型：{question_type}\n"
    "用户具体问题：{specific_question}\n\n"
    "请结合牌的正逆位含义、在牌阵中的位置意义以及用户的问题，给出专业、具体的解读。"
    "解读应简洁有力，2-3句话即可，不要泛泛而谈。",
    constraints=TAROT_CONSTRAINTS,
)

PromptRegistry.register(
    "tarot_synthesis",
    "请对以下塔罗牌占卜结果进行综合解读：\n\n"
    "牌阵：{spread_name}（{spread_description}）\n"
    "用户问题类型：{question_type}\n"
    "用户具体问题：{specific_question}\n\n"
    "各牌位解读：\n{cards_detail}\n\n"
    "补充知识：\n{knowledge_context}\n\n"
    "请综合所有牌的含义，结合牌阵结构和用户问题，给出完整的占卜报告。\n"
    "报告应包含：1）整体趋势 2）核心建议 3）需要注意的方面。\n"
    "语气温和专业，给予积极正面的引导。",
    constraints=TAROT_CONSTRAINTS,
)

PromptRegistry.register(
    "tarot_follow_up",
    "基于以下塔罗牌占卜结果和对话上下文，回答用户的追问：\n\n"
    "占卜上下文：\n{tarot_context}\n\n"
    "用户追问：{query}\n\n"
    "请结合之前的塔罗牌占卜结果，提供连贯、专业的回答。",
    constraints=TAROT_CONSTRAINTS,
)

PromptRegistry.register(
    "tarot_general",
    "基于以下上下文，回答用户关于塔罗牌的问题：\n\n"
    "上下文：\n{context}\n\n"
    "用户问题：{query}\n\n"
    "请以塔罗牌占卜师的身份，提供专业、准确的回答。",
    constraints=TAROT_CONSTRAINTS,
)
