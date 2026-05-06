# src/safety/safety.py
"""
==============================================================================
安全模块核心实现
==============================================================================

功能说明：
    本模块实现了命理咨询系统的核心安全功能，包括输入层的敏感词过滤、
    意图检测，输出层的内容审核，以及兜底机制的安全回复模板。

安全机制：
    1. 输入层：敏感词过滤、意图检测
    2. 输出层：内容审核
    3. 兜底机制：预设安全回复模板

安全类别：
    - PSYCHOLOGY: 心理健康（自杀、自残、心理疾病等）
    - ILLEGAL: 违法内容（犯罪、贩毒、诈骗等）
    - GAMBLING: 赌博相关
    - SEXUAL: 色情低俗
    - FINANCIAL: 金融投资/荐股
    - FATALISM: 宿命论（过度绝对化）
    - RELIGION: 迷信宗教（鬼魂、阴间、轮回等）
    - VIOLENCE: 暴力相关
    - POLITICS: 政治敏感

==============================================================================
"""

import re
import logging
from typing import Dict, Any, List, Optional, Literal, Pattern
from dataclasses import dataclass, field
from enum import Enum

from src.safety.scene_strategy import SceneType, scene_strategy

logger = logging.getLogger(__name__)


class SafetyLevel(Enum):
    """
    ==============================================================================
    安全等级
    ==============================================================================
    
    等级说明：
        - SAFE: 安全，无需处理
        - WARNING: 警告，需人工审核
        - BLOCK: 阻断，直接拒绝
    
    ==============================================================================
    """
    SAFE = "safe"           # 安全
    WARNING = "warning"     # 警告（需人工审核）
    BLOCK = "block"         # 阻断（直接拒绝）


class SafetyCategory(Enum):
    """
    ==============================================================================
    安全类别
    ==============================================================================
    
    类别说明：
        - PSYCHOLOGY: 心理健康
        - ILLEGAL: 违法内容
        - GAMBLING: 赌博
        - SEXUAL: 色情低俗
        - FINANCIAL: 金融投资/荐股
        - FATALISM: 宿命论
        - RELIGION: 迷信宗教
        - VIOLENCE: 暴力
        - POLITICS: 政治敏感
        - OTHER: 其他
    
    ==============================================================================
    """
    PSYCHOLOGY = "psychology"       # 心理健康
    ILLEGAL = "illegal"             # 违法内容
    GAMBLING = "gambling"           # 赌博
    SEXUAL = "sexual"               # 色情低俗
    FINANCIAL = "financial"         # 金融投资/荐股
    FATALISM = "fatalism"           # 宿命论
    RELIGION = "religion"           # 迷信宗教
    VIOLENCE = "violence"           # 暴力
    POLITICS = "politics"           # 政治敏感
    OTHER = "other"                 # 其他


@dataclass
class SafetyResult:
    """
    ==============================================================================
    安全检查结果
    ==============================================================================
    
    属性说明：
        - level: 安全等级（SAFE/WARNING/BLOCK）
        - category: 安全类别（可选）
        - matched_keywords: 匹配的敏感词列表
        - message: 检查消息
        - blocked: 是否被阻断
    
    ==============================================================================
    """
    level: SafetyLevel
    category: Optional[SafetyCategory] = None
    matched_keywords: List[str] = field(default_factory=list)
    message: str = ""
    blocked: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """
        将安全检查结果转换为字典格式
        
        Returns:
            Dict[str, Any]: 安全检查结果字典
        """
        return {
            "level": self.level.value,
            "category": self.category.value if self.category else None,
            "matched_keywords": self.matched_keywords,
            "message": self.message,
            "blocked": self.blocked,
        }


@dataclass
class SafetyInput:
    """
    ==============================================================================
    输入安全检查数据
    ==============================================================================
    
    属性说明：
        - text: 输入文本
        - input_type: 输入类型（user_query/llm_output/system_prompt）
        - user_id: 用户ID（可选）
        - conversation_id: 会话ID（可选）
    
    ==============================================================================
    """
    text: str
    input_type: Literal["user_query", "llm_output", "system_prompt"] = "user_query"
    user_id: Optional[str] = None
    conversation_id: Optional[str] = None


@dataclass
class SafetyOutput:
    """
    ==============================================================================
    输出安全检查数据
    ==============================================================================
    
    属性说明：
        - text: 输出文本
        - original_text: 原始输出文本
        - safety_result: 安全检查结果
    
    ==============================================================================
    """
    text: str
    original_text: str
    safety_result: SafetyResult


class SafetyConfig:
    """
    ==============================================================================
    安全配置
    ==============================================================================
    
    功能说明：
        安全配置类，定义了各类敏感词库、意图检测模式和安全回复模板。
    
    敏感词库：
        - PSYCHOLOGY_KEYWORDS: 心理健康相关
        - ILLEGAL_KEYWORDS: 违法相关
        - GAMBLING_KEYWORDS: 赌博相关
        - SEXUAL_KEYWORDS: 色情低俗相关
        - FINANCIAL_KEYWORDS: 金融投资/荐股相关
        - FATALISM_KEYWORDS: 宿命论相关
        - RELIGION_KEYWORDS: 迷信相关
        - VIOLENCE_KEYWORDS: 暴力相关
        - POLITICS_KEYWORDS: 政治相关
    
    意图检测：
        - INTENT_PATTERNS: 意图检测正则表达式模式
    
    安全回复：
        - BLOCK_RESPONSES: 阻断回复模板
        - WARNING_RESPONSES: 警告回复模板
        - SAFE_RESPONSES: 安全回复模板
    
    ==============================================================================
    """
    
    # 敏感词库 - 心理健康相关
    # 权重：10（高危）、9（高）、8（中）
    PSYCHOLOGY_KEYWORDS = {
        # 自杀相关
        "自杀": 10, "自尽": 10, "结束生命": 10, "了结生命": 10,
        "不想活了": 10, "想死": 10, "死掉": 10, "自残": 10,
        "割腕": 10, "跳楼": 10, "跳桥": 10, "服药": 10,
        # 心理疾病
        "抑郁症": 8, "抑郁症": 8, "焦虑症": 8, "强迫症": 8,
        "双相情感障碍": 8, "精神分裂": 8, "人格障碍": 8,
        "创伤后应激": 8, "PTSD": 8,
        # 危险表述
        "活不下去": 9, "太痛苦了": 9, "活着没意思": 9,
        "不如死了算了": 10, "想结束一切": 10,
    }
    
    # 敏感词库 - 违法相关
    ILLEGAL_KEYWORDS = {
        "违法": 10, "犯罪": 10, "贩毒": 10, "走私": 10,
        "贪污": 10, "受贿": 10, "行贿": 10, "洗钱": 10,
        "诈骗": 10, "敲诈": 10, "绑架": 10, "拐卖": 10,
        "恐怖分子": 10, "暴恐": 10, "分裂国家": 10,
    }
    
    # 敏感词库 - 赌博相关
    GAMBLING_KEYWORDS = {
        "赌博": 10, "赌钱": 10, "赌球": 10, "赌马": 10,
        "六合彩": 10, "赌桌": 10, "筹码": 10, "梭哈": 10,
        "百家乐": 10, "轮盘赌": 10, "老虎机": 10,
        "赢钱": 8, "输钱": 8, "赢了": 8, "输了": 8,
    }

    # 敏感词库 - 色情低俗相关
    SEXUAL_KEYWORDS = {
        "色情": 10, "黄色": 10, "淫秽": 10, "成人影片": 10,
        "AV片": 10, "av": 9, "做爱": 10, "上床": 10,
        "约炮": 10, "一夜情": 10, "嫖娼": 10, "招嫖": 10,
        "性交易": 10, "情色": 9, "裸聊": 10, "成人视频": 10,
    }

    # 敏感词库 - 金融投资/荐股相关
    FINANCIAL_KEYWORDS = {
        "荐股": 10, "带单": 10, "喊单": 10, "股票代码": 10,
        "涨停": 9, "跌停": 9, "抄底": 9, "满仓": 9,
        "加仓": 9, "减仓": 9, "做多": 8, "做空": 8,
        "买哪只股票": 10, "什么时候买入": 10, "什么时候卖出": 10,
        "短线": 8, "K线": 8, "个股": 8, "炒股": 9,
    }
    
    # 敏感词库 - 宿命论相关（过度绝对化）
    FATALISM_KEYWORDS = {
        "注定": 6, "命里注定": 6, "无法改变": 6, "逃不掉": 6,
        "命中注定": 6, "注定要": 6, "注定会": 6, "注定不能": 6,
        "注定失败": 6, "注定成功": 6, "宿命": 6,
    }
    
    # 敏感词库 - 迷信相关
    RELIGION_KEYWORDS = {
        "鬼魂": 7, "阴间": 7, "阳间": 7, "投胎": 7,
        "转世": 7, "轮回": 7, "阴灵": 7, "附体": 7,
        "驱鬼": 7, "画符": 7, "咒语": 7, "诅咒": 7,
    }
    
    # 敏感词库 - 暴力相关
    VIOLENCE_KEYWORDS = {
        "杀人": 9, "谋杀": 9, "伤害": 9, "殴打": 9,
        "砍死": 9, "炸死": 9, "烧死": 9, "勒死": 9,
        "暴力": 8, "血腥": 8, "残暴": 8, "虐杀": 8,
    }
    
    # 敏感词库 - 政治相关
    POLITICS_KEYWORDS = {
        "反共": 10, "反政府": 10, "颠覆": 10, "政变": 10,
        "抗议": 10, "游行": 10, "示威": 10, "罢工": 10,
        "敏感词": 10, "政治敏感": 10, "审查": 10, "禁词": 10,
    }

    # 需要结合语境判断的模糊关键词
    AMBIGUOUS_KEYWORD_PATTERNS = {
        SafetyCategory.SEXUAL: {
            "黄色": [
                r"黄(片|片子|网|色网站|色小说|色资源)",
                r"黄色(?:网站|小说|视频|资源|图片|漫画|内容|电影|片)",
            ],
            "av": [
                r"AV片",
                r"(?:^|[^a-z])av(?:[^a-z]|$)",
            ],
        },
        SafetyCategory.POLITICS: {
            "敏感词": [r"敏感词"],
            "政治敏感": [r"政治敏感"],
            "审查": [r"内容审查|政治审查|舆论审查|新闻审查|言论审查|审查制度"],
            "禁词": [r"禁词"],
        },
    }

    # 输出中若明确表达规避、拒绝、风险提示，则不应直接阻断
    MITIGATING_PATTERNS = [
        r"(不要|别|不能|不可|不该|避免|远离|警惕|拒绝|防止|谨慎|切勿|别把).{0,8}",
        r"(违法|非法|高风险|有风险|存在风险|不建议|不宜|无关).{0,8}",
        r"(不是|并非|不代表|不等于|不意味着).{0,8}",
    ]

    # 输出检查中，命理相关常见表述默认只告警不阻断
    OUTPUT_SEVERITY_CAPS = {
        SafetyCategory.FATALISM: 6,
        SafetyCategory.RELIGION: 6,
    }
    
    # 意图检测关键词
    # 使用正则表达式进行模式匹配
    INTENT_PATTERNS = {
        "自杀危机": [
            r"不想活了", r"想死", r"活不下去", r"了结生命",
            r"结束生命", r"不如死了算了", r"太痛苦了",
        ],
        "违法请求": [
            r"教我.*违法", r"教我.*犯罪", r"怎么.*诈骗",
            r"怎么.*贩毒", r"帮.*犯罪",
        ],
        "赌博请求": [
            r"教我.*赌博", r"怎么.*赢钱", r"赌博技巧",
            r"赌球.*技巧", r"六合彩.*预测",
        ],
        "宿命论请求": [
            r"注定.*无法.*改变", r"命里.*注定", r"逃不掉.*",
            r"宿命.*无法.*改变",
        ],
        "色情请求": [
            r"推荐.*(色情|黄色|av|成人视频)",
            r"怎么.*约炮",
            r"怎么.*嫖",
            r"(做爱|上床).*技巧",
        ],
        "荐股请求": [
            r"(推荐|告诉我|给我).*(股票|个股)",
            r"(什么时候|何时).*(买入|卖出)",
            r"(哪只|什么).*(股票|基金)",
            r"(股票代码|涨停|抄底|加仓|减仓|满仓)",
        ],
    }
    
    # 兜底回复模板
    # 针对不同安全类别提供不同的回复
    BLOCK_RESPONSES = {
        SafetyCategory.PSYCHOLOGY: (
            "我理解您可能正在经历一些困难。如果您感到心理上的痛苦或困扰，"
            "建议您寻求专业的心理咨询师或精神科医生的帮助。"
            "生命是宝贵的，请珍惜自己。"
        ),
        SafetyCategory.ILLEGAL: (
            "我不能提供任何违法或犯罪相关的建议。"
            "如果您遇到困难，建议通过合法途径寻求帮助。"
        ),
        SafetyCategory.GAMBLING: (
            "赌博是违法行为，不仅违反中国法律，而且会对个人和家庭造成严重伤害。"
            "如果您或身边的人有赌博问题，建议寻求专业帮助。"
        ),
        SafetyCategory.SEXUAL: (
            "我不能提供色情、低俗或性交易相关内容。"
            "如果您有其他健康、关系或情绪方面的问题，我可以提供合规范围内的帮助。"
        ),
        SafetyCategory.FINANCIAL: (
            "我不能提供荐股、带单或具体买卖时点等投资建议。"
            "如果您关心财务规划，我可以提供一般性的风险提示和理性建议。"
        ),
        SafetyCategory.FATALISM: (
            "命运掌握在自己手中，通过努力和正确的选择，"
            "每个人都可以改变自己的人生轨迹。"
            "我更愿意为您提供积极的人生建议和心理支持。"
        ),
        SafetyCategory.RELIGION: (
            "我主要提供基于传统文化的命理咨询服务，"
            "不涉及迷信或超自然内容。"
            "如果您有其他问题，欢迎继续提问。"
        ),
        SafetyCategory.VIOLENCE: (
            "我不能提供任何涉及暴力或伤害他人的建议。"
            "如果您感到愤怒或有暴力倾向，建议寻求专业心理帮助。"
        ),
        SafetyCategory.POLITICS: (
            "我主要提供命理和传统文化相关的咨询服务。"
            "如果您有其他非敏感话题的问题，欢迎继续提问。"
        ),
    }
    
    # 警告回复模板
    WARNING_RESPONSES = {
        SafetyCategory.PSYCHOLOGY: (
            "我注意到您可能正在经历一些困难。"
            "生命是宝贵的，请珍惜自己。"
            "如果您需要帮助，建议联系专业心理咨询机构。"
        ),
        SafetyCategory.FINANCIAL: (
            "涉及财务与投资问题时，我只能提供一般性风险提示，"
            "不会给出具体买卖、荐股或收益承诺。"
        ),
        SafetyCategory.FATALISM: (
            "命理学强调的是趋吉避凶，而不是宿命论。"
            "通过努力和正确的选择，每个人都可以改变自己的人生。"
        ),
    }
    
    # 安全输出模板
    SAFE_RESPONSES = {
        "default": "感谢您的提问，我会尽力为您提供帮助。",
        "psychology_referral": (
            "如果您感到心理上的困扰，建议您寻求专业帮助。"
            "以下是一些心理援助资源："
            "• 心理援助热线：400-161-9995（希望24热线）"
            "• 北京心理危机干预中心：010-82951332"
            "• 上海心理援助：021-12320-5"
        ),
    }


class SafetyChecker:
    """
    ==============================================================================
    安全检查器
    ==============================================================================
    
    功能说明：
        安全检查器，负责对输入和输出内容进行安全检查。
        包括敏感词匹配、意图检测和安全等级判断。
    
    核心方法：
        - check_input(): 检查输入内容的安全性
        - check_output(): 检查输出内容的安全性
        - get_safe_response(): 获取兜底安全回复
        - is_blocked(): 检查文本是否会被阻断
        - get_blocked_category(): 获取阻断的类别
    
    使用场景：
        - 用户输入检查
        - LLM 输出检查
        - 安全兜底回复
    
    ==============================================================================
    """
    
    def __init__(self, config: SafetyConfig = None):
        """
        ==============================================================================
        初始化安全检查器
        ==============================================================================
        
        功能说明：
            初始化安全检查器，加载安全配置和正则表达式模式。
        
        参数说明：
            config (SafetyConfig): 安全配置对象，默认使用 SafetyConfig
        
        ==============================================================================
        """
        self.config = config or SafetyConfig()
        self._init_patterns()
    
    def _init_patterns(self):
        """
        ==============================================================================
        初始化正则表达式模式
        ==============================================================================
        
        功能说明：
            将意图检测的关键词列表编译为正则表达式模式，提高匹配效率。
        
        ==============================================================================
        """
        self.intent_patterns = {}
        for intent, patterns in self.config.INTENT_PATTERNS.items():
            self.intent_patterns[intent] = re.compile(
                "|".join(f"({p})" for p in patterns),
                re.IGNORECASE
            )
        self.ambiguous_keyword_patterns: Dict[SafetyCategory, Dict[str, List[Pattern[str]]]] = {}
        for category, keyword_map in self.config.AMBIGUOUS_KEYWORD_PATTERNS.items():
            compiled_map: Dict[str, List[Pattern[str]]] = {}
            for keyword, patterns in keyword_map.items():
                compiled_map[keyword] = [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
            self.ambiguous_keyword_patterns[category] = compiled_map
        self.mitigating_patterns = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in self.config.MITIGATING_PATTERNS
        ]
    
    def check_input(self, text: str, user_id: str = None) -> SafetyResult:
        """
        ==============================================================================
        检查输入内容的安全性
        ==============================================================================
        
        功能说明：
            检查用户输入内容的安全性，包括敏感词匹配和意图检测。
        
        参数说明：
            text (str): 输入文本
            user_id (str): 用户ID（用于追踪，可选）
        
        返回值：
            SafetyResult: 安全检查结果
        
        检查流程：
            1. 检查各类敏感词
            2. 检查意图模式
            3. 确定安全等级
            4. 构建检查结果
        
        安全等级判断：
            - max_severity >= 9: BLOCK（阻断）
            - max_severity >= 6: WARNING（警告）
            - 其他: SAFE（安全）
        
        ==============================================================================
        """
        matched_keywords, max_severity, category = self._scan_keywords(text, mode="input")
        
        # 检查意图模式
        for intent, pattern in self.intent_patterns.items():
            if pattern.search(text):
                matched_keywords.append(f"意图: {intent}")
                if intent == "自杀危机":
                    max_severity = 10
                    category = SafetyCategory.PSYCHOLOGY
                elif intent == "违法请求":
                    max_severity = 10
                    category = SafetyCategory.ILLEGAL
                elif intent == "赌博请求":
                    max_severity = 10
                    category = SafetyCategory.GAMBLING
                elif intent == "色情请求":
                    max_severity = 10
                    category = SafetyCategory.SEXUAL
                elif intent == "荐股请求":
                    max_severity = 10
                    category = SafetyCategory.FINANCIAL
        
        # 确定安全等级
        if max_severity >= 9:
            level = SafetyLevel.BLOCK
        elif max_severity >= 6:
            level = SafetyLevel.WARNING
        else:
            level = SafetyLevel.SAFE
        
        # 构建结果
        result = SafetyResult(
            level=level,
            category=category,
            matched_keywords=matched_keywords,
            blocked=level == SafetyLevel.BLOCK,
        )
        
        # 添加消息
        if level == SafetyLevel.BLOCK:
            if category in self.config.BLOCK_RESPONSES:
                result.message = self.config.BLOCK_RESPONSES[category]
            else:
                result.message = "您的输入包含敏感内容，无法处理。"
        elif level == SafetyLevel.WARNING:
            if category in self.config.WARNING_RESPONSES:
                result.message = self.config.WARNING_RESPONSES[category]
            else:
                result.message = "您的输入可能存在风险，请注意。"
        
        logger.info(f"输入安全检查: level={level.value}, category={category}, keywords={matched_keywords}")
        
        return result
    
    def check_output(self, text: str) -> SafetyResult:
        """
        ==============================================================================
        检查输出内容的安全性
        ==============================================================================
        
        功能说明：
            检查 LLM 输出内容的安全性，主要检查明显违规内容。
            输出检查相对宽松，主要防止明显违规。
        
        参数说明：
            text (str): 输出文本
        
        返回值：
            SafetyResult: 安全检查结果
        
        ==============================================================================
        """
        matched_keywords, max_severity, category = self._scan_keywords(text, mode="output")

        if max_severity >= 9:
            level = SafetyLevel.BLOCK
        elif max_severity >= 6:
            level = SafetyLevel.WARNING
        else:
            level = SafetyLevel.SAFE

        result = SafetyResult(
            level=level,
            category=category,
            matched_keywords=matched_keywords,
            blocked=level == SafetyLevel.BLOCK,
        )

        if level == SafetyLevel.BLOCK:
            if category in self.config.BLOCK_RESPONSES:
                result.message = self.config.BLOCK_RESPONSES[category]
            else:
                result.message = "输出内容包含敏感信息，已被拦截。"
        elif level == SafetyLevel.WARNING:
            if category in self.config.WARNING_RESPONSES:
                result.message = self.config.WARNING_RESPONSES[category]
            else:
                result.message = "输出内容可能存在风险，请注意。"

        logger.info(f"输出安全检查: level={level.value}, category={category}, keywords={matched_keywords}")
        return result

    def check_scene_input(self, text: str, scene_type: SceneType) -> SafetyResult:
        """输入安全 + 场景化策略组合检查。"""
        return self._merge_scene_result(self.check_input(text), text, scene_type, mode="input")

    def check_scene_output(self, text: str, scene_type: SceneType) -> SafetyResult:
        """输出安全 + 场景化策略组合检查。"""
        return self._merge_scene_result(self.check_output(text), text, scene_type, mode="output")

    def _merge_scene_result(
        self,
        base_result: SafetyResult,
        text: str,
        scene_type: SceneType,
        mode: Literal["input", "output"],
    ) -> SafetyResult:
        """
        将通用规则检查与场景化安全策略合并。

        规则：
        - 任一方 block 即最终 block
        - 否则任一方 warning 即最终 warning
        - 消息优先使用更具体的一方
        """
        scene_result = scene_strategy.check_content(text, scene_type, mode=mode)
        matched_keywords = list(dict.fromkeys(base_result.matched_keywords + scene_result.get("matched_keywords", [])))

        if base_result.blocked or scene_result.get("blocked"):
            message = base_result.message or scene_result.get("message") or "您的请求包含敏感内容，无法处理。"
            category = base_result.category or SafetyCategory.OTHER
            if category == SafetyCategory.OTHER and scene_result.get("blocked"):
                category = self._guess_category_from_scene(scene_result.get("matched_keywords", []))
            return SafetyResult(
                level=SafetyLevel.BLOCK,
                category=category,
                matched_keywords=matched_keywords,
                message=message,
                blocked=True,
            )

        if base_result.level == SafetyLevel.WARNING or scene_result.get("warning"):
            message = base_result.message or scene_result.get("message") or "您的输入可能存在风险，请注意。"
            category = base_result.category or self._guess_category_from_scene(scene_result.get("matched_keywords", []))
            return SafetyResult(
                level=SafetyLevel.WARNING,
                category=category,
                matched_keywords=matched_keywords,
                message=message,
                blocked=False,
            )

        return SafetyResult(
            level=SafetyLevel.SAFE,
            category=base_result.category,
            matched_keywords=matched_keywords,
            message=base_result.message,
            blocked=False,
        )

    def _guess_category_from_scene(self, keywords: List[str]) -> SafetyCategory:
        text = " ".join(keywords)
        if any(keyword in text for keyword in ["股票", "炒股", "荐股", "涨停", "跌停", "买入", "卖出"]):
            return SafetyCategory.FINANCIAL
        if any(keyword in text for keyword in ["色情", "黄色", "av", "做爱", "嫖"]):
            return SafetyCategory.SEXUAL
        if any(keyword in text for keyword in ["鬼魂", "阴间", "投胎", "轮回", "附体", "诅咒"]):
            return SafetyCategory.RELIGION
        if any(keyword in text for keyword in ["注定", "宿命", "无法改变"]):
            return SafetyCategory.FATALISM
        return SafetyCategory.OTHER

    def _scan_keywords(
        self,
        text: str,
        mode: Literal["input", "output"],
    ) -> tuple[List[str], int, Optional[SafetyCategory]]:
        matched_keywords: List[str] = []
        max_severity = 0
        category: Optional[SafetyCategory] = None

        checks = [
            (self.config.PSYCHOLOGY_KEYWORDS, SafetyCategory.PSYCHOLOGY),
            (self.config.ILLEGAL_KEYWORDS, SafetyCategory.ILLEGAL),
            (self.config.GAMBLING_KEYWORDS, SafetyCategory.GAMBLING),
            (self.config.SEXUAL_KEYWORDS, SafetyCategory.SEXUAL),
            (self.config.FINANCIAL_KEYWORDS, SafetyCategory.FINANCIAL),
            (self.config.FATALISM_KEYWORDS, SafetyCategory.FATALISM),
            (self.config.RELIGION_KEYWORDS, SafetyCategory.RELIGION),
            (self.config.VIOLENCE_KEYWORDS, SafetyCategory.VIOLENCE),
            (self.config.POLITICS_KEYWORDS, SafetyCategory.POLITICS),
        ]

        for keywords_dict, current_category in checks:
            for keyword, severity in keywords_dict.items():
                if not self._keyword_matches(text, current_category, keyword):
                    continue
                adjusted_severity = self._adjust_severity(
                    text=text,
                    category=current_category,
                    keyword=keyword,
                    severity=severity,
                    mode=mode,
                )
                if adjusted_severity <= 0:
                    continue
                matched_keywords.append(keyword)
                if adjusted_severity > max_severity:
                    max_severity = adjusted_severity
                    category = current_category

        return matched_keywords, max_severity, category

    def _keyword_matches(
        self,
        text: str,
        category: SafetyCategory,
        keyword: str,
    ) -> bool:
        pattern_map = self.ambiguous_keyword_patterns.get(category, {})
        if keyword in pattern_map:
            return any(pattern.search(text) for pattern in pattern_map[keyword])
        return keyword in text

    def _adjust_severity(
        self,
        *,
        text: str,
        category: SafetyCategory,
        keyword: str,
        severity: int,
        mode: Literal["input", "output"],
    ) -> int:
        if mode == "output":
            capped = self.config.OUTPUT_SEVERITY_CAPS.get(category)
            if capped is not None:
                severity = min(severity, capped)
            has_global_mitigation = any(pattern.search(text) for pattern in self.mitigating_patterns)
            if self._has_mitigating_context(text, keyword):
                if category in {
                    SafetyCategory.FATALISM,
                    SafetyCategory.RELIGION,
                    SafetyCategory.FINANCIAL,
                }:
                    return 0
                severity = min(severity, 6)
            if has_global_mitigation and category == SafetyCategory.FINANCIAL:
                return 0
        return severity

    def _has_mitigating_context(self, text: str, keyword: str) -> bool:
        try:
            keyword_index = text.index(keyword)
        except ValueError:
            return False

        start = max(0, keyword_index - 12)
        end = min(len(text), keyword_index + len(keyword) + 12)
        context = text[start:end]
        return any(pattern.search(context) for pattern in self.mitigating_patterns)
    
    def get_safe_response(self, category: SafetyCategory, level: SafetyLevel) -> str:
        """
        ==============================================================================
        获取兜底安全回复
        ==============================================================================
        
        功能说明：
            根据安全类别和等级，返回预设的安全回复模板。
        
        参数说明：
            category (SafetyCategory): 安全类别
            level (SafetyLevel): 安全等级
        
        返回值：
            str: 安全回复文本
        
        ==============================================================================
        """
        if level == SafetyLevel.BLOCK:
            if category in self.config.BLOCK_RESPONSES:
                return self.config.BLOCK_RESPONSES[category]
            return "您的请求包含敏感内容，无法处理。"
        
        if level == SafetyLevel.WARNING:
            if category in self.config.WARNING_RESPONSES:
                return self.config.WARNING_RESPONSES[category]
            return "您的请求可能存在风险，请注意。"
        
        return self.config.SAFE_RESPONSES["default"]
    
    def is_blocked(self, text: str) -> bool:
        """
        ==============================================================================
        检查文本是否会被阻断
        ==============================================================================
        
        功能说明：
            快速检查文本是否会被阻断，返回布尔值。
        
        参数说明：
            text (str): 输入文本
        
        返回值：
            bool: 是否会被阻断
        
        ==============================================================================
        """
        result = self.check_input(text)
        return result.blocked
    
    def get_blocked_category(self, text: str) -> Optional[SafetyCategory]:
        """
        ==============================================================================
        获取阻断的类别
        ==============================================================================
        
        功能说明：
            获取文本被阻断的安全类别。
        
        参数说明：
            text (str): 输入文本
        
        返回值：
            Optional[SafetyCategory]: 阻断的类别，如果未被阻断则返回 None
        
        ==============================================================================
        """
        result = self.check_input(text)
        if result.blocked:
            return result.category
        return None
