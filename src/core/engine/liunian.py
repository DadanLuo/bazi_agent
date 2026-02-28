"""
流年运势分析引擎
基于《三命通会》《滴天髓》规则
"""
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from src.core.models.bazi_models import FourPillars, Pillar, Tiangan, Dizhi
from .rules import rule_loader
from .wuxing_calculator import WuxingCalculator
from .geju import GejuEngine

logger = logging.getLogger(__name__)


class LiunianEngine:
    """
    流年运势分析引擎

    分析内容：
    1. 流年干支计算
    2. 流年与四柱关系（冲合刑害）
    3. 流年十神判断
    4. 流年神煞判断
    5. 综合吉凶评估
    """

    # 天干地支顺序
    TIANGAN_LIST = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
    DIZHI_LIST = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]

    # 六冲
    LIUCHONG = {
        "子": "午", "午": "子",
        "丑": "未", "未": "丑",
        "寅": "申", "申": "寅",
        "卯": "酉", "酉": "卯",
        "辰": "戌", "戌": "辰",
        "巳": "亥", "亥": "巳"
    }

    # 六合
    LIUHE = {
        "子": "丑", "丑": "子",
        "寅": "亥", "亥": "寅",
        "卯": "戌", "戌": "卯",
        "辰": "酉", "酉": "辰",
        "巳": "申", "申": "巳",
        "午": "未", "未": "午"
    }

    # 十神映射（复用 GejuEngine）
    SHISHEN_MAP = GejuEngine.SHISHEN_MAP

    def __init__(self):
        self.rule_loader = rule_loader
        self.wuxing_calc = WuxingCalculator()
        self.tiangan_wuxing = self.rule_loader.get_tiangan_wuxing()
        self.dizhi_wuxing = self.rule_loader.get_dizhi_wuxing()

    def get_liunian_ganzhi(self, year: int) -> Tuple[str, str]:
        """
        获取流年干支
        1984 年为甲子年
        """
        base_year = 1984
        offset = year - base_year

        tg_idx = offset % 10
        dz_idx = offset % 12

        return self.TIANGAN_LIST[tg_idx], self.DIZHI_LIST[dz_idx]

    def get_liuchong_relation(self, dizhi1: str, dizhi2: str) -> bool:
        """判断是否相冲"""
        return self.LIUCHONG.get(dizhi1) == dizhi2

    def get_liuhe_relation(self, dizhi1: str, dizhi2: str) -> bool:
        """判断是否相合"""
        return self.LIUHE.get(dizhi1) == dizhi2

    def get_shishen(self, ri_qian: str, tiangan: str) -> str:
        """获取十神"""
        return self.SHISHEN_MAP.get(ri_qian, {}).get(tiangan, "未知")

    def analyze_liunian(self, pillars: FourPillars,
                        yongshen_result: Dict,
                        target_year: int = None) -> Dict:
        """分析流年运势"""
        if target_year is None:
            target_year = datetime.now().year

        logger.info(f"流年分析：目标年份={target_year}")

        # 1. 获取流年干支
        liunian_tg, liunian_dz = self.get_liunian_ganzhi(target_year)
        logger.info(f"流年干支：{liunian_tg}{liunian_dz}")

        # 2. 获取日主信息
        ri_qian = pillars.day.tiangan.value
        ri_dz = pillars.day.dizhi.value
        nian_dz = pillars.year.dizhi.value

        # 3. 流年十神
        liunian_shishen = self.get_shishen(ri_qian, liunian_tg)
        logger.info(f"流年十神：{liunian_shishen}")

        # 4. 流年与四柱关系
        chonghe_analysis = self._analyze_chonghe(pillars, liunian_tg, liunian_dz)

        # 5. 太岁关系
        taisui_analysis = self._analyze_taisui(nian_dz, liunian_dz)

        # 6. 神煞分析（修复：直接调用，不依赖 JSON）
        shensha_analysis = self._analyze_shensha(ri_qian, pillars, liunian_dz)

        # 7. 喜用神关系
        yongshen_relation = self._analyze_yongshen_relation(
            liunian_tg, liunian_dz, yongshen_result
        )

        # 8. 综合吉凶判断
        jixiong_score, jixiong_level, jixiong_desc = self._calculate_jixiong(
            chonghe_analysis, taisui_analysis, shensha_analysis,
            yongshen_relation, liunian_shishen
        )

        # 9. 生成建议
        advice = self._generate_advice(
            jixiong_level, liunian_shishen, chonghe_analysis, yongshen_relation
        )

        result = {
            "year": target_year,
            "ganzhi": f"{liunian_tg}{liunian_dz}",
            "tiangan": liunian_tg,
            "dizhi": liunian_dz,
            "shishen": liunian_shishen,
            "chonghe": chonghe_analysis,
            "taisui": taisui_analysis,
            "shensha": shensha_analysis,
            "yongshen_relation": yongshen_relation,
            "jixiong": {
                "score": jixiong_score,
                "level": jixiong_level,
                "description": jixiong_desc
            },
            "advice": advice,
            "analysis": self._generate_analysis_text(
                liunian_tg, liunian_dz, liunian_shishen,
                chonghe_analysis, yongshen_relation
            )
        }

        logger.info(f"流年吉凶：{jixiong_level} - {jixiong_desc}")
        return result

    def _analyze_chonghe(self, pillars: FourPillars,
                         liunian_tg: str, liunian_dz: str) -> Dict:
        """分析流年与四柱的冲合关系"""
        chonghe = {
            "chong": [],  # 冲
            "he": [],  # 合
            "xing": [],  # 刑
            "hai": []  # 害
        }

        four_dizhi = [
            ("年支", pillars.year.dizhi.value),
            ("月支", pillars.month.dizhi.value),
            ("日支", pillars.day.dizhi.value),
            ("时支", pillars.hour.dizhi.value)
        ]

        for position, dizhi in four_dizhi:
            # 检查冲
            if self.get_liuchong_relation(liunian_dz, dizhi):
                chonghe["chong"].append({
                    "position": position,
                    "dizhi": dizhi,
                    "description": f"流年冲{position}，主变动"
                })

            # 检查合
            if self.get_liuhe_relation(liunian_dz, dizhi):
                chonghe["he"].append({
                    "position": position,
                    "dizhi": dizhi,
                    "description": f"流年合{position}，主和合"
                })

        return chonghe

    def _analyze_taisui(self, nian_dz: str, liunian_dz: str) -> Dict:
        """分析太岁关系"""
        taisui = {"type": "平", "description": "无明显冲犯"}

        # 值太岁
        if nian_dz == liunian_dz:
            taisui = {
                "type": "值太岁",
                "description": "本命年，伏吟之象，多变动",
                "severity": "中"
            }
        # 冲太岁
        elif self.get_liuchong_relation(nian_dz, liunian_dz):
            taisui = {
                "type": "冲太岁",
                "description": "冲犯太岁，多波折，需谨慎",
                "severity": "重"
            }
        # 合太岁
        elif self.get_liuhe_relation(nian_dz, liunian_dz):
            taisui = {
                "type": "合太岁",
                "description": "合太岁，多机遇，贵人相助",
                "severity": "吉"
            }
        # 害太岁（简化：相冲的前一位）
        elif self.LIUCHONG.get(nian_dz) == liunian_dz:
            taisui = {
                "type": "害太岁",
                "description": "害太岁，防小人，注意人际",
                "severity": "轻"
            }

        return taisui

    def _analyze_shensha(self, ri_qian: str, pillars: FourPillars,
                         liunian_dz: str) -> Dict:
        """分析流年神煞"""
        shensha = {"jishen": [], "xiongsha": []}

        # 天乙贵人查法（直接硬编码，避免 JSON 解析问题）
        tianyi_map = {
            "甲": ["丑", "未"], "乙": ["子", "申"],
            "丙": ["亥", "酉"], "丁": ["亥", "酉"],
            "戊": ["丑", "未"], "己": ["子", "申"],
            "庚": ["丑", "未"], "辛": ["寅", "午"],
            "壬": ["卯", "巳"], "癸": ["卯", "巳"]
        }
        tianyi_dizhi = tianyi_map.get(ri_qian, [])
        if liunian_dz in tianyi_dizhi:
            shensha["jishen"].append({
                "name": "天乙贵人",
                "effect": "贵人相助，逢凶化吉"
            })

        # 文昌贵人查法
        wenchang_map = {
            "甲": "巳", "乙": "午", "丙": "申", "丁": "酉",
            "戊": "申", "己": "酉", "庚": "亥", "辛": "子",
            "壬": "寅", "癸": "卯"
        }
        wenchang_dizhi = wenchang_map.get(ri_qian, "")
        if liunian_dz == wenchang_dizhi:
            shensha["jishen"].append({
                "name": "文昌贵人",
                "effect": "学业进步，才华展现"
            })

        # 禄神查法
        lushen_map = {
            "甲": "寅", "乙": "卯", "丙": "巳", "丁": "午",
            "戊": "巳", "己": "午", "庚": "申", "辛": "酉",
            "壬": "亥", "癸": "子"
        }
        lushen_dizhi = lushen_map.get(ri_qian, "")
        if liunian_dz == lushen_dizhi:
            shensha["jishen"].append({
                "name": "禄神",
                "effect": "财运亨通，事业顺利"
            })

        # 羊刃查法
        yangren_map = {
            "甲": "卯", "乙": "辰", "丙": "午", "丁": "未",
            "戊": "午", "己": "未", "庚": "酉", "辛": "戌",
            "壬": "子", "癸": "丑"
        }
        yangren_dizhi = yangren_map.get(ri_qian, "")
        if liunian_dz == yangren_dizhi:
            shensha["xiongsha"].append({
                "name": "羊刃",
                "effect": "性格刚强，易惹是非"
            })

        # 桃花查法
        taohua_map = {
            "申子辰": "酉", "寅午戌": "卯",
            "巳酉丑": "午", "亥卯未": "子"
        }
        nian_dz = pillars.year.dizhi.value
        for key, value in taohua_map.items():
            if nian_dz in key and liunian_dz == value:
                shensha["xiongsha"].append({
                    "name": "桃花",
                    "effect": "异性缘佳，但防感情纠纷"
                })
                break

        return shensha
    def _analyze_yongshen_relation(self, liunian_tg: str, liunian_dz: str,
                                   yongshen_result: Dict) -> Dict:
        """分析流年与喜用神的关系"""
        yongshen = yongshen_result.get("yongshen", [])
        jishen = yongshen_result.get("jishen", [])

        liunian_tg_wx = self.tiangan_wuxing.get(liunian_tg, "土")
        liunian_dz_wx = self.rule_loader.get_dizhi_wuxing().get(liunian_dz, "土")

        relation = {
            "tg_relation": "平",
            "dz_relation": "平",
            "description": ""
        }

        # 天干关系
        if liunian_tg_wx in yongshen:
            relation["tg_relation"] = "喜"
            relation["description"] += f"流年天干为喜用神({liunian_tg_wx})，吉; "
        elif liunian_tg_wx in jishen:
            relation["tg_relation"] = "忌"
            relation["description"] += f"流年天干为忌神({liunian_tg_wx})，凶; "

        # 地支关系
        if liunian_dz_wx in yongshen:
            relation["dz_relation"] = "喜"
            relation["description"] += f"流年地支为喜用神({liunian_dz_wx})，吉; "
        elif liunian_dz_wx in jishen:
            relation["dz_relation"] = "忌"
            relation["description"] += f"流年地支为忌神({liunian_dz_wx})，凶; "

        return relation

    def _calculate_jixiong(self, chonghe: Dict, taisui: Dict,
                           shensha: Dict, yongshen_rel: Dict,
                           liunian_shishen: str) -> Tuple[int, str, str]:
        """综合计算吉凶分数（-100 到 100）"""
        score = 0

        # 冲合影响
        score -= len(chonghe.get("chong", [])) * 15  # 每个冲 -15
        score += len(chonghe.get("he", [])) * 10  # 每个合 +10

        # 太岁影响
        taisui_score = {"吉": 20, "平": 0, "轻": -10, "中": -20, "重": -30}
        score += taisui_score.get(taisui.get("severity", "平"), 0)

        # 神煞影响
        score += len(shensha.get("jishen", [])) * 10  # 每个吉神 +10
        score -= len(shensha.get("xiongsha", [])) * 10  # 每个凶煞 -10

        # 喜用神影响
        if yongshen_rel.get("tg_relation") == "喜":
            score += 20
        elif yongshen_rel.get("tg_relation") == "忌":
            score -= 20
        if yongshen_rel.get("dz_relation") == "喜":
            score += 20
        elif yongshen_rel.get("dz_relation") == "忌":
            score -= 20

        # 十神影响
        # 修正后的代码
        shishen_rules = self.rule_loader.get_liunian_rules().get("shishen_liunian", {}).get("rules", {})
        shishen_info = shishen_rules.get(liunian_shishen, {})
        if shishen_info.get("ji", True):
            score += 10
        else:
            score -= 10

        # 限制分数范围
        score = max(-100, min(100, score))

        # 判定吉凶等级
        if score >= 60:
            level = "大吉"
            desc = "流年运势极佳，诸事顺利"
        elif score >= 30:
            level = "吉"
            desc = "流年运势较好，多有机遇"
        elif score >= 0:
            level = "平吉"
            desc = "流年运势平稳，小有收获"
        elif score >= -30:
            level = "平凶"
            desc = "流年运势一般，需谨慎行事"
        elif score >= -60:
            level = "凶"
            desc = "流年运势较差，多有不顺"
        else:
            level = "大凶"
            desc = "流年运势极差，宜守不宜进"

        return score, level, desc

    def _generate_advice(self, jixiong_level: str, liunian_shishen: str,
                         chonghe: Dict, yongshen_rel: Dict) -> List[str]:
        """生成流年建议"""
        advice = []

        # 根据吉凶等级
        if jixiong_level in ["大吉", "吉"]:
            advice.append("宜积极进取，把握机遇")
            advice.append("适合投资、创业、跳槽等重大决策")
        elif jixiong_level in ["凶", "大凶"]:
            advice.append("宜守不宜进，谨慎行事")
            advice.append("避免重大投资和决策")
            advice.append("注意身体健康和人际关系")
        else:
            advice.append("稳步发展，不宜冒进")

        # 根据十神
        if liunian_shishen == "七杀":
            advice.append("压力较大，需防小人")
        elif liunian_shishen == "伤官":
            advice.append("易惹是非，需谨言慎行")
        elif liunian_shishen == "正财":
            advice.append("财运稳定，适合理财")
        elif liunian_shishen == "正官":
            advice.append("事业顺利，有贵人相助")

        # 根据冲合
        if chonghe.get("chong"):
            advice.append("流年有冲，主变动，注意调整心态")

        return advice

    def _generate_analysis_text(self, liunian_tg: str, liunian_dz: str,
                                liunian_shishen: str, chonghe: Dict,
                                yongshen_rel: Dict) -> str:
        """生成流年分析文本"""
        text = f"{liunian_tg}{liunian_dz}年，"

        # 十神描述
        shishen_desc = {
            "正官": "事业运佳，有升职机遇",
            "七杀": "压力与机遇并存",
            "正印": "学业进步，贵人扶持",
            "偏印": "思维独特，宜钻研",
            "正财": "财运稳定，收入增加",
            "偏财": "有偏财机遇",
            "食神": "才华展现，心情愉悦",
            "伤官": "创意丰富，但防口舌",
            "比肩": "朋友相助，合作顺利",
            "劫财": "财运波动，需防破财"
        }
        text += shishen_desc.get(liunian_shishen, "") + "。"

        # 冲合描述
        if chonghe.get("chong"):
            text += "流年有冲，主变动，"
        if chonghe.get("he"):
            text += "流年有合，主和合，"

        # 喜用神描述
        if yongshen_rel.get("tg_relation") == "喜" or yongshen_rel.get("dz_relation") == "喜":
            text += "喜用神到位，运势较佳。"
        elif yongshen_rel.get("tg_relation") == "忌" or yongshen_rel.get("dz_relation") == "忌":
            text += "忌神当道，需谨慎行事。"

        return text

    def analyze_multiple_years(self, pillars: FourPillars,
                               yongshen_result: Dict,
                               start_year: int,
                               end_year: int) -> List[Dict]:
        """分析多年流年运势"""
        results = []
        for year in range(start_year, end_year + 1):
            result = self.analyze_liunian(pillars, yongshen_result, year)
            results.append(result)
        return results