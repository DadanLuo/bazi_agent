# src/safety/scene_strategy.py
"""
==============================================================================
场景化安全策略
==============================================================================

功能说明：
    本模块实现了场景化安全策略，根据不同业务场景采用不同的安全审核标准。
    通过白名单、黑名单和警告关键词的组合，实现灵活的安全控制。

场景类型：
    - BAZI: 八字分析
    - TAROT: 塔罗占卜
    - CHAT: 日常聊天
    - FOLLOW_UP: 追问场景

==============================================================================
"""

from dataclasses import dataclass
from typing import Dict, List, Set, Optional
from enum import Enum


class SceneType(Enum):
    """
    ==============================================================================
    场景类型
    ==============================================================================
    
    类型说明：
        - BAZI: 八字分析
        - TAROT: 塔罗占卜
        - CHAT: 日常聊天
        - FOLLOW_UP: 追问场景
    
    ==============================================================================
    """
    BAZI = "bazi"           # 八字分析
    TAROT = "tarot"         # 塔罗占卜
    CHAT = "chat"           # 日常聊天
    FOLLOW_UP = "follow_up" # 追问场景


@dataclass
class SceneSafetyConfig:
    """
    ==============================================================================
    场景安全配置
    ==============================================================================
    
    属性说明：
        - scene_type: 场景类型
        - allowed_keywords: 允许的关键词（白名单）
        - blocked_keywords: 禁止的关键词（黑名单）
        - warning_keywords: 警告关键词
        - strictness: 审核严格程度 (0-1, 1最严格)
        - require_human_review: 是否需要人工审核
        - fallback_template: 兜底回复模板
    
    ==============================================================================
    """
    scene_type: SceneType
    
    # 允许的关键词（白名单）
    allowed_keywords: Set[str]
    
    # 禁止的关键词（黑名单）
    blocked_keywords: Set[str]
    
    # 警告关键词
    warning_keywords: Set[str]
    
    # 审核严格程度 (0-1, 1最严格)
    strictness: float
    
    # 是否需要人工审核
    require_human_review: bool
    
    # 兜底回复模板
    fallback_template: str


class SceneSafetyStrategy:
    """
    ==============================================================================
    场景化安全策略
    ==============================================================================
    
    功能说明：
        场景化安全策略，根据不同业务场景采用不同的安全审核标准。
        通过白名单、黑名单和警告关键词的组合，实现灵活的安全控制。
    
    核心方法：
        - get_config(): 获取场景配置
        - check_content(): 根据场景检查内容
        - get_strictness(): 获取场景严格程度
        - should_require_human_review(): 是否需要人工审核
    
    使用场景：
        - 八字分析场景的安全控制
        - 塔罗占卜场景的安全控制
        - 日常聊天场景的安全控制
        - 追问场景的安全控制
    
    ==============================================================================
    """
    
    def __init__(self):
        """
        ==============================================================================
        初始化场景化安全策略
        ==============================================================================
        
        功能说明：
            初始化场景化安全策略，加载各场景的配置。
        
        ==============================================================================
        """
        self.configs: Dict[SceneType, SceneSafetyConfig] = {}
        self._init_configs()
    
    def _init_configs(self):
        """
        ==============================================================================
        初始化各场景配置
        ==============================================================================
        
        功能说明：
            初始化各业务场景的安全配置，包括白名单、黑名单和警告关键词。
        
        ==============================================================================
        """
        
        # 八字分析场景
        self.configs[SceneType.BAZI] = SceneSafetyConfig(
            scene_type=SceneType.BAZI,
            allowed_keywords={
                # 允许的命理术语
                "命理", "八字", "五行", "格局", "用神", "流年",
                "大运", "十神", "神煞", "天干", "地支",
                "财星", "官星", "印星", "食神", "伤官",
                "比肩", "劫财", "正财", "偏财", "正官", "七杀",
                "正印", "偏印", "食神", "伤官", "劫财", "比肩",
                "命局", "命盘", "排盘", "测算", "分析", "预测",
                "趋吉避凶", "化解", "开运", "风水", "择吉",
            },
            blocked_keywords={
                # 禁止的内容
                "自杀", "自尽", "结束生命", "了结生命", "不想活了",
                "想死", "死掉", "自残", "割腕", "跳楼", "跳桥",
                "杀人", "谋杀", "伤害", "殴打", "砍死", "炸死",
                "赌博", "赌钱", "赌球", "赌马", "六合彩", "梭哈",
                "违法", "犯罪", "贩毒", "走私", "贪污", "受贿",
                "诈骗", "敲诈", "绑架", "拐卖", "恐怖分子", "暴恐",
            },
            warning_keywords={
                # 需要警告的内容
                "注定", "宿命", "无法改变", "命中注定", "逃不掉",
                "命里注定", "注定要", "注定会", "注定不能", "注定失败",
                "注定成功", "宿命", "轮回", "阴间", "阳间",
            },
            strictness=0.5,  # 中等严格度
            require_human_review=False,
            fallback_template=(
                "命理学旨在提供人生参考，而非决定命运。"
                "每个人都可以通过努力改变自己的人生轨迹。"
                "如果您有其他问题，欢迎继续提问。"
            ),
        )
        
        # 塔罗占卜场景
        self.configs[SceneType.TAROT] = SceneSafetyConfig(
            scene_type=SceneType.TAROT,
            allowed_keywords={
                # 允许的塔罗术语
                "塔罗", "牌阵", "大阿卡纳", "小阿卡纳",
                "正位", "逆位", "圣杯", "权杖", "星币", "宝剑",
                "愚者", "魔术师", "女祭司", "皇后", "皇帝", "教皇",
                "恋人", "战车", "力量", "隐者", "命运之轮", "正义",
                "倒吊人", "死神", "节制", "恶魔", "高塔", "星星",
                "月亮", "太阳", "审判", "世界", "权杖一", "权杖二",
                "圣杯一", "圣杯二", "星币一", "星币二", "宝剑一", "宝剑二",
            },
            blocked_keywords={
                # 禁止的内容
                "自杀", "自尽", "结束生命", "了结生命", "不想活了",
                "想死", "死掉", "自残", "割腕", "跳楼", "跳桥",
                "杀人", "谋杀", "伤害", "殴打", "砍死", "炸死",
                "赌博", "赌钱", "赌球", "赌马", "六合彩", "梭哈",
                "违法", "犯罪", "贩毒", "走私", "贪污", "受贿",
                "诅咒", "附体", "驱鬼", "画符", "咒语", "阴灵",
            },
            warning_keywords={
                # 需要警告的内容
                "鬼魂", "阴间", "投胎", "轮回", "阳间", "阴间",
                "灵魂", "灵异", "超自然", "神秘力量", "神秘能量",
            },
            strictness=0.6,  # 稍高严格度
            require_human_review=False,
            fallback_template=(
                "塔罗牌是一种心理投射工具，用于自我探索和反思。"
                "请以积极的心态面对生活中的挑战。"
                "如果您有其他问题，欢迎继续提问。"
            ),
        )
        
        # 日常聊天场景
        self.configs[SceneType.CHAT] = SceneSafetyConfig(
            scene_type=SceneType.CHAT,
            allowed_keywords=set(),  # 无特殊允许
            blocked_keywords={
                # 严格禁止
                "自杀", "自尽", "结束生命", "了结生命", "不想活了",
                "想死", "死掉", "自残", "割腕", "跳楼", "跳桥",
                "杀人", "谋杀", "伤害", "殴打", "砍死", "炸死",
                "赌博", "赌钱", "赌球", "赌马", "六合彩", "梭哈",
                "违法", "犯罪", "贩毒", "走私", "贪污", "受贿",
                "诈骗", "敲诈", "绑架", "拐卖", "恐怖分子", "暴恐",
                "分裂国家", "反政府", "反共", "政变", "抗议",
                "鬼魂", "阴间", "阳间", "投胎", "轮回", "诅咒",
            },
            warning_keywords=set(),
            strictness=0.9,  # 高严格度
            require_human_review=True,
            fallback_template="您的请求包含敏感内容，无法处理。",
        )
        
        # 追问场景
        self.configs[SceneType.FOLLOW_UP] = SceneSafetyConfig(
            scene_type=SceneType.FOLLOW_UP,
            allowed_keywords={
                # 允许的追问关键词
                "解释", "说明", "为什么", "怎么", "详细", "具体",
                "再", "继续", "然后", "接下来", "那么", "所以",
            },
            blocked_keywords={
                # 禁止的内容
                "自杀", "自尽", "结束生命", "了结生命", "不想活了",
                "想死", "死掉", "自残", "割腕", "跳楼", "跳桥",
                "杀人", "谋杀", "伤害", "殴打", "砍死", "炸死",
                "赌博", "赌钱", "赌球", "赌马", "六合彩", "梭哈",
                "违法", "犯罪", "贩毒", "走私", "贪污", "受贿",
            },
            warning_keywords={
                # 需要警告的内容
                "注定", "宿命", "无法改变", "命中注定", "逃不掉",
            },
            strictness=0.7,  # 中高严格度
            require_human_review=False,
            fallback_template="您的追问包含敏感内容，无法处理。",
        )
    
    def get_config(self, scene_type: SceneType) -> SceneSafetyConfig:
        """
        ==============================================================================
        获取场景配置
        ==============================================================================
        
        参数说明：
            scene_type (SceneType): 场景类型
        
        返回值：
            SceneSafetyConfig: 场景配置对象
        
        ==============================================================================
        """
        return self.configs.get(scene_type, self.configs[SceneType.CHAT])
    
    def check_content(
        self,
        content: str,
        scene_type: SceneType,
    ) -> Dict:
        """
        ==============================================================================
        根据场景检查内容
        ==============================================================================
        
        功能说明：
            根据场景配置检查内容的安全性。
        
        参数说明：
            content (str): 待检查内容
            scene_type (SceneType): 场景类型
        
        返回值：
            Dict: 检查结果，包含：
                - scene (str): 场景类型
                - blocked (bool): 是否被阻断
                - warning (bool): 是否有警告
                - matched_keywords (List[str]): 匹配的关键词
                - message (str): 检查消息
                - require_human_review (bool): 是否需要人工审核
        
        检查流程：
            1. 检查禁止关键词（黑名单）
            2. 检查警告关键词
            3. 检查允许关键词（白名单，可抵消警告）
            4. 设置检查消息
        
        ==============================================================================
        """
        config = self.get_config(scene_type)
        
        result = {
            "scene": scene_type.value,
            "blocked": False,
            "warning": False,
            "matched_keywords": [],
            "message": "",
            "require_human_review": config.require_human_review,
        }
        
        # 检查禁止关键词
        for keyword in config.blocked_keywords:
            if keyword in content:
                result["blocked"] = True
                result["matched_keywords"].append(keyword)
        
        # 检查警告关键词
        for keyword in config.warning_keywords:
            if keyword in content:
                result["warning"] = True
                result["matched_keywords"].append(keyword)
        
        # 检查允许关键词（可以抵消部分警告）
        for keyword in config.allowed_keywords:
            if keyword in content:
                # 允许的关键词可以降低警告级别
                if result["warning"] and len(result["matched_keywords"]) == 1:
                    result["warning"] = False
        
        # 设置消息
        if result["blocked"]:
            result["message"] = config.fallback_template
        elif result["warning"]:
            result["message"] = "请注意：内容可能存在风险"
        
        return result
    
    def get_strictness(self, scene_type: SceneType) -> float:
        """
        ==============================================================================
        获取场景严格程度
        ==============================================================================
        
        参数说明：
            scene_type (SceneType): 场景类型
        
        返回值：
            float: 严格程度 (0-1, 1最严格)
        
        ==============================================================================
        """
        config = self.get_config(scene_type)
        return config.strictness
    
    def should_require_human_review(self, scene_type: SceneType) -> bool:
        """
        ==============================================================================
        是否需要人工审核
        ==============================================================================
        
        参数说明：
            scene_type (SceneType): 场景类型
        
        返回值：
            bool: 是否需要人工审核
        
        ==============================================================================
        """
        config = self.get_config(scene_type)
        return config.require_human_review


# 全局场景策略实例
scene_strategy = SceneSafetyStrategy()
