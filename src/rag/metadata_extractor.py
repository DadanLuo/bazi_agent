"""
Metadata 提取器
用于从八字命理文本中提取结构化元数据，替代 BM25 检索
"""
from typing import Dict, List, Optional
import re


# 固定实体词典
TIANGAN = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
DIZHI = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
WUXING = ["金", "木", "水", "火", "土"]
SHENSHA = [
    "七杀", "正官", "偏财", "正财", "食神", "伤官", 
    "比肩", "劫财", "正印", "偏印"
]
GEJU = [
    "正官格", "偏官格", "正财格", "偏财格",
    "正印格", "偏印格", "食神格", "伤官格",
    "建禄格", "羊刃格", "从格", "化气格"
]
YONGSHEN_TYPES = ["用神", "喜神", "忌神", "仇神", "闲神"]
LIUNIAN = ["流年", "大运", "小运", "岁运", "太岁"]
CHANGSHENG = ["长生", "沐浴", "冠带", "临官", "帝旺", "衰", "病", "死", "墓", "绝", "胎", "养"]

# 话题关键词 - 扩展版本
TOPIC_KEYWORDS = {
    "格局": ["格局", "成格", "破格", "正官格", "财格", "印格", "食神格", "七杀格", "从格", "化气格", "建禄格", "羊刃格"],
    "用神": ["用神", "喜神", "忌神", "仇神", "闲神", "调候", "扶抑", "通关", "平衡", "制化"],
    "五行": ["五行", "生克", "制化", "旺衰", "强弱", "相生", "相克", "相冲", "相合", "刑冲合害"],
    "神煞": ["神煞", "贵人", "桃花", "驿马", "华盖", "文昌", "天乙贵人", "太极贵人", "国印贵人", "魁罡", "将星", "红鸾", "天喜", "孤辰", "寡宿"],
    "流年": ["流年", "大运", "小运", "岁运", "太岁", "行运", "运程", "岁君", "流月", "流日"],
    "十神": ["十神", "正官", "七杀", "正财", "偏财", "食神", "伤官", "比肩", "劫财", "正印", "偏印", "枭神", "偏官"],
    "长生": ["长生", "沐浴", "冠带", "临官", "帝旺", "衰", "病", "死", "墓", "绝", "胎", "养", "十二长生", "长生十二神"],
    "命局": ["命局", "八字", "四柱", "命造", "原局", "本命", "日主", "日元", "日干", "命主"],
    "分析": ["分析", "判断", "推断", "预测", "解读", "解析", "论断", "评断"],
    "规则": ["规则", "原则", "定律", "法则", "规律", "定理", "公式", "方法", "步骤"],
    "案例": ["案例", "实例", "例子", "示例", "举例", "说明", "论证", "验证"]
}

# 章节关键词模式
CHAPTER_PATTERNS = [
    r'第[一二三四五六七八九十百千]+章',
    r'[一二三四五六七八九十百千]+、',
    r'\d+\.\d+\.\d+',
    r'\d+\.\d+',
    r'\d+',
    r'#+'
]

# 关键字提取增强规则
KEYWORD_EXTRACTION_RULES = {
    "重要性权重": {
        "必须": 3.0, "重要": 2.5, "关键": 2.5, "核心": 2.0, "主要": 2.0,
        "基本": 1.5, "根本": 1.5, "原则": 2.0, "规律": 2.0, "本质": 2.0,
        "决定": 2.0, "影响": 1.5, "作用": 1.5, "条件": 1.5, "要求": 1.5
    },
    "否定词": ["不", "无", "非", "未", "否", "莫", "勿", "毋", "弗", "匪"],
    "程度副词": ["很", "非常", "极其", "特别", "相当", "比较", "稍微", "略微"]
}


class MetadataExtractor:
    """Metadata 提取器"""

    def __init__(self):
        self.tiangan_set = set(TIANGAN)
        self.dizhi_set = set(DIZHI)
        self.wuxing_set = set(WUXING)
        self.shensha_set = set(SHENSHA)
        self.geju_set = set(GEJU)
        self.yongshen_types_set = set(YONGSHEN_TYPES)
        self.liunian_set = set(LIUNIAN)
        self.changsheng_set = set(CHANGSHENG)

    def extract(self, text: str, source: str = "", chapter: str = "", chapter_name: str = "", section_path: str = "") -> Dict:
        """
        从文本中提取 metadata
        
        Args:
            text: 输入文本
            source: 来源书籍
            chapter: 章节路径
            chapter_name: 章节名称
            section_path: 节路径（多级章节）
            
        Returns:
            包含提取的 metadata 的字典
        """
        wuxing = self._extract_entities(text, self.wuxing_set)
        tiangan = self._extract_entities(text, self.tiangan_set)
        dizhi = self._extract_entities(text, self.dizhi_set)
        shensha = self._extract_entities(text, self.shensha_set)
        geju = self._extract_entities(text, self.geju_set)
        yongshen = self._extract_entities(text, self.yongshen_types_set)
        liunian = self._extract_entities(text, self.liunian_set)
        changsheng = self._extract_entities(text, self.changsheng_set)
        topic = self._extract_topic(
            text,
            wuxing=wuxing,
            shensha=shensha,
            geju=geju,
            yongshen=yongshen,
            liunian=liunian,
            changsheng=changsheng,
        )
        sub_topic = self._extract_sub_topic(
            text,
            topic=topic,
            geju=geju,
            shensha=shensha,
        )
        keywords = self._build_keywords(
            topic=topic,
            sub_topic=sub_topic,
            wuxing=wuxing,
            tiangan=tiangan,
            dizhi=dizhi,
            shensha=shensha,
            geju=geju,
            yongshen=yongshen,
            liunian=liunian,
            changsheng=changsheng,
        )

        metadata = {
            # ===== 基础信息 =====
            "source": source,
            "chapter": chapter,
            "chapter_name": chapter_name,
            "section_path": section_path,
            "filename": "",
            
            # ===== 关键词（替代 BM25）=====
            "keywords": keywords,
            
            # ===== 实体标签 =====
            "wuxing": wuxing,
            "tiangan": tiangan,
            "dizhi": dizhi,
            "shensha": shensha,
            "geju": geju,
            "yongshen": yongshen,
            "liunian": liunian,
            "changsheng": changsheng,
            
            # ===== 主题分类 =====
            "topic": topic,
            "sub_topic": sub_topic,
            
            # ===== 文本属性 =====
            "chunk_type": self._classify_chunk_type(text),
            "importance": self._estimate_importance(text),
        }
        
        return metadata

    def _extract_entities(self, text: str, entity_set: set) -> List[str]:
        """提取指定类型的实体"""
        found = []
        for entity in entity_set:
            if entity in text:
                found.append(entity)
        return list(set(found))  # 去重

    def _extract_topic(
        self,
        text: str,
        *,
        wuxing: List[str],
        shensha: List[str],
        geju: List[str],
        yongshen: List[str],
        liunian: List[str],
        changsheng: List[str],
    ) -> str:
        """提取主话题"""
        if geju or any(keyword in text for keyword in ["格局", "成格", "破格"]):
            return "格局"
        if yongshen or any(keyword in text for keyword in ["调候", "扶抑", "通关"]):
            return "用神"
        if liunian or any(keyword in text for keyword in ["行运", "流月", "流日"]):
            return "流年"
        if changsheng or any(keyword in text for keyword in ["十二长生", "长生十二神"]):
            return "长生"
        if shensha or any(keyword in text for keyword in ["十神", "枭神", "偏官"]):
            return "十神"
        if wuxing or any(keyword in text for keyword in ["生克", "旺衰", "强弱"]):
            return "五行"

        for topic, keywords in TOPIC_KEYWORDS.items():
            for kw in keywords:
                if kw in text:
                    return topic
        return "general"

    def _extract_sub_topic(
        self,
        text: str,
        topic: str = "general",
        *,
        geju: Optional[List[str]] = None,
        shensha: Optional[List[str]] = None,
    ) -> str:
        """提取子话题"""
        geju = geju or []
        shensha = shensha or []

        if topic == "格局" and geju:
            return geju[0]

        if topic == "十神" and shensha:
            return shensha[0]

        # 优先匹配更具体的子话题
        for topic_name, keywords in TOPIC_KEYWORDS.items():
            for kw in keywords:
                if kw in text:
                    return kw
        return "general"

    def _build_keywords(self, **fields: List[str] | str) -> List[str]:
        """基于已提取字段构建关键词，避免再次全量扫描原文。"""
        keywords = []

        topic = fields.get("topic")
        sub_topic = fields.get("sub_topic")
        if isinstance(topic, str) and topic != "general":
            keywords.append(topic)
        if isinstance(sub_topic, str) and sub_topic != "general":
            keywords.append(sub_topic)

        for field_name in (
            "wuxing",
            "tiangan",
            "dizhi",
            "shensha",
            "geju",
            "yongshen",
            "liunian",
            "changsheng",
        ):
            values = fields.get(field_name, [])
            if isinstance(values, list):
                keywords.extend(values)

        return list(dict.fromkeys(keywords))

    def _classify_chunk_type(self, text: str) -> str:
        """分类文本类型"""
        if any(keyword in text for keyword in ["理论", "原理", "概念", "定义"]):
            return "theory"
        elif any(keyword in text for keyword in ["规则", "方法", "步骤", "条件"]):
            return "rule"
        elif any(keyword in text for keyword in ["案例", "实例", "例子", "分析"]):
            return "case"
        elif any(keyword in text for keyword in ["示例", "举例", "说明"]):
            return "example"
        else:
            return "general"

    def _estimate_importance(self, text: str) -> float:
        """估算重要程度"""
        importance_score = 0.5  # 默认值
        
        # 增加重要性的关键词
        important_keywords = [
            "必须", "重要", "关键", "核心", "主要", "基本", "根本",
            "原则", "规律", "本质", "决定", "影响", "作用"
        ]
        
        # 减少重要性的关键词
        modifier_keywords = [
            "可能", "或许", "也许", "一般", "通常", "往往", "有时"
        ]
        
        for keyword in important_keywords:
            if keyword in text:
                importance_score += 0.1
                
        for keyword in modifier_keywords:
            if keyword in text:
                importance_score -= 0.05
                
        # 确保在 0.0-1.0 范围内
        return max(0.0, min(1.0, importance_score))
    
# 全局实例
metadata_extractor = MetadataExtractor()


def extract_metadata(text: str, source: str = "", chapter: str = "", chapter_name: str = "", section_path: str = "") -> Dict:
    """便捷函数：提取 metadata"""
    return metadata_extractor.extract(text, source, chapter, chapter_name, section_path)
