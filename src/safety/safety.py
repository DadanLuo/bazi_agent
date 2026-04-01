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
    - FATALISM: 宿命论（过度绝对化）
    - RELIGION: 迷信宗教（鬼魂、阴间、轮回等）
    - VIOLENCE: 暴力相关
    - POLITICS: 政治敏感

==============================================================================
"""

import re
import logging
from typing import Dict, Any, List, Optional, Literal
from dataclasses import dataclass, field
from enum import Enum

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
        "敏感": 10, "禁词": 10, "审查": 10,
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
        matched_keywords = []
        max_severity = 0
        category = None
        
        # 检查各类敏感词
        checks = [
            (self.config.PSYCHOLOGY_KEYWORDS, SafetyCategory.PSYCHOLOGY),
            (self.config.ILLEGAL_KEYWORDS, SafetyCategory.ILLEGAL),
            (self.config.GAMBLING_KEYWORDS, SafetyCategory.GAMBLING),
            (self.config.FATALISM_KEYWORDS, SafetyCategory.FATALISM),
            (self.config.RELIGION_KEYWORDS, SafetyCategory.RELIGION),
            (self.config.VIOLENCE_KEYWORDS, SafetyCategory.VIOLENCE),
            (self.config.POLITICS_KEYWORDS, SafetyCategory.POLITICS),
        ]
        
        for keywords_dict, cat in checks:
            for keyword, severity in keywords_dict.items():
                if keyword in text:
                    matched_keywords.append(keyword)
                    if severity > max_severity:
                        max_severity = severity
                        category = cat
        
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
        # 输出检查相对宽松，主要检查明显违规内容
        return self.check_input(text)
    
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
