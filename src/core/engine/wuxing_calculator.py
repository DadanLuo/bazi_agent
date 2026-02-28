"""
五行分数计算器
基于 JSON 规则文件进行准确的五行统计
"""
import logging
from typing import Dict, List, Optional
from src.core.models.bazi_models import (
    FourPillars, WuxingScore, Pillar, Tiangan, Dizhi
)
from .rules import rule_loader

logger = logging.getLogger(__name__)


class WuxingCalculator:
    """
    五行分数计算器

    计算逻辑：
    1. 天干五行：直接计入，每干 100 分
    2. 地支五行：按藏干权重分配，每支 100 分
    3. 可选：考虑月令旺衰、得地得势等因素
    """

    # 五行顺序
    WUXING_ORDER = ["木", "火", "土", "金", "水"]

    def __init__(self):
        self.rule_loader = rule_loader
        self.tiangan_wuxing = self.rule_loader.get_tiangan_wuxing()
        self.dizhi_wuxing = self.rule_loader.get_dizhi_wuxing()

    def calculate_tiangan_score(self, pillars: FourPillars) -> Dict[str, int]:
        """
        计算天干五行分数
        每个天干计 100 分
        """
        score = {wx: 0 for wx in self.WUXING_ORDER}

        # 年干
        year_tg = pillars.year.tiangan.value
        year_wx = self.tiangan_wuxing.get(year_tg, "土")
        score[year_wx] += 100

        # 月干
        month_tg = pillars.month.tiangan.value
        month_wx = self.tiangan_wuxing.get(month_tg, "土")
        score[month_wx] += 100

        # 日干（日主，权重可加倍）
        day_tg = pillars.day.tiangan.value
        day_wx = self.tiangan_wuxing.get(day_tg, "土")
        score[day_wx] += 100  # 日主也可计 150 分，看流派

        # 时干
        hour_tg = pillars.hour.tiangan.value
        hour_wx = self.tiangan_wuxing.get(hour_tg, "土")
        score[hour_wx] += 100

        logger.debug(f"天干五行分数：{score}")
        return score

    def calculate_dizhi_score(self, pillars: FourPillars) -> Dict[str, int]:
        """
        计算地支五行分数
        根据地支藏干及权重分配
        """
        score = {wx: 0 for wx in self.WUXING_ORDER}

        # 年支
        year_dz = pillars.year.dizhi.value
        year_canggan = self.rule_loader.get_canggan(year_dz)
        for cangan in year_canggan:
            tg = cangan['tiangan']
            weight = cangan['weight']
            wx = self.tiangan_wuxing.get(tg, "土")
            score[wx] += weight

        # 月支（月令，权重可加倍）
        month_dz = pillars.month.dizhi.value
        month_canggan = self.rule_loader.get_canggan(month_dz)
        for cangan in month_canggan:
            tg = cangan['tiangan']
            weight = cangan['weight']
            wx = self.tiangan_wuxing.get(tg, "土")
            score[wx] += weight * 1.2  # 月令加权 20%

        # 日支
        day_dz = pillars.day.dizhi.value
        day_canggan = self.rule_loader.get_canggan(day_dz)
        for cangan in day_canggan:
            tg = cangan['tiangan']
            weight = cangan['weight']
            wx = self.tiangan_wuxing.get(tg, "土")
            score[wx] += weight

        # 时支
        hour_dz = pillars.hour.dizhi.value
        hour_canggan = self.rule_loader.get_canggan(hour_dz)
        for cangan in hour_canggan:
            tg = cangan['tiangan']
            weight = cangan['weight']
            wx = self.tiangan_wuxing.get(tg, "土")
            score[wx] += weight

        # 转换为整数
        score = {k: int(v) for k, v in score.items()}
        logger.debug(f"地支五行分数：{score}")
        return score

    def calculate_total_score(self, pillars: FourPillars) -> WuxingScore:
        """
        计算总五行分数
        """
        tiangan_score = self.calculate_tiangan_score(pillars)
        dizhi_score = self.calculate_dizhi_score(pillars)

        # 合并分数
        total_score = {
            "木": tiangan_score["木"] + dizhi_score["木"],
            "火": tiangan_score["火"] + dizhi_score["火"],
            "土": tiangan_score["土"] + dizhi_score["土"],
            "金": tiangan_score["金"] + dizhi_score["金"],
            "水": tiangan_score["水"] + dizhi_score["水"],
        }

        logger.info(f"五行总分：{total_score}")

        return WuxingScore(
            mu=total_score["木"],
            huo=total_score["火"],
            tu=total_score["土"],
            jin=total_score["金"],
            shui=total_score["水"]
        )

    def analyze_wuxing_balance(self, score: WuxingScore) -> Dict:
        """
        分析五行平衡状态
        """
        total = score.total()
        if total == 0:
            return {"status": "unknown", "description": "无法计算"}

        # 计算各五行占比
        percentages = {
            "木": round(score.mu / total * 100, 2),
            "火": round(score.huo / total * 100, 2),
            "土": round(score.tu / total * 100, 2),
            "金": round(score.jin / total * 100, 2),
            "水": round(score.shui / total * 100, 2),
        }

        # 平均值（理想状态每个五行 20%）
        avg = 20.0

        # 判断强弱
        strong = []
        weak = []
        balanced = []

        for wx, pct in percentages.items():
            if pct > avg + 5:  # 超过 25% 算强
                strong.append(wx)
            elif pct < avg - 5:  # 低于 15% 算弱
                weak.append(wx)
            else:
                balanced.append(wx)

        # 生成分析结论
        if len(strong) == 0 and len(weak) == 0:
            status = "balanced"
            description = "五行基本平衡"
        elif len(strong) > len(weak):
            status = "strong"
            description = f"五行偏强，{','.join(strong)}较旺"
        elif len(weak) > len(strong):
            status = "weak"
            description = f"五行偏弱，{','.join(weak)}不足"
        else:
            status = "mixed"
            description = f"{','.join(strong)}偏旺，{','.join(weak)}偏弱"

        return {
            "status": status,
            "description": description,
            "percentages": percentages,
            "strong": strong,
            "weak": weak,
            "balanced": balanced,
            "total_score": total
        }

    def get_day_master_strength(self, pillars: FourPillars) -> Dict:
        """
        判断日主强弱
        考虑：得令、得地、得势
        """
        day_tg = pillars.day.tiangan.value
        day_dz = pillars.day.dizhi.value
        month_dz = pillars.month.dizhi.value

        day_wx = self.tiangan_wuxing.get(day_tg, "土")

        # 1. 得令（月令是否生扶日主）
        month_canggan = self.rule_loader.get_canggan(month_dz)
        ling_score = 0
        for cangan in month_canggan:
            tg = cangan['tiangan']
            tg_wx = self.tiangan_wuxing.get(tg, "土")
            weight = cangan['weight']
            # 同五行或生我者为得令
            if tg_wx == day_wx:
                ling_score += weight
            elif self._is_sheng(tg_wx, day_wx):
                ling_score += weight * 0.8

        de_ling = ling_score >= 50

        # 2. 得地（日支是否生扶日主）
        day_canggan = self.rule_loader.get_canggan(day_dz)
        di_score = 0
        for cangan in day_canggan:
            tg = cangan['tiangan']
            tg_wx = self.tiangan_wuxing.get(tg, "土")
            weight = cangan['weight']
            if tg_wx == day_wx:
                di_score += weight
            elif self._is_sheng(tg_wx, day_wx):
                di_score += weight * 0.8

        de_di = di_score >= 50

        # 3. 得势（其他干支是否生扶）
        shi_score = 0
        all_pillars = [
            pillars.year.tiangan.value, pillars.year.dizhi.value,
            pillars.month.tiangan.value,
            pillars.hour.tiangan.value, pillars.hour.dizhi.value
        ]
        for gz in all_pillars:
            gz_wx = self.tiangan_wuxing.get(gz, "土")
            if gz_wx == day_wx:
                shi_score += 20
            elif self._is_sheng(gz_wx, day_wx):
                shi_score += 15

        de_shi = shi_score >= 50

        # 综合判断
        strength_level = sum([de_ling, de_di, de_shi])
        if strength_level >= 3:
            strength = "strong"
            description = "日主强旺（得令、得地、得势）"
        elif strength_level >= 2:
            strength = "medium"
            description = "日主中和偏强"
        elif strength_level >= 1:
            strength = "weak"
            description = "日主偏弱"
        else:
            strength = "very_weak"
            description = "日主极弱"

        return {
            "day_master": day_tg,
            "day_master_wx": day_wx,
            "de_ling": de_ling,
            "de_di": de_di,
            "de_shi": de_shi,
            "strength": strength,
            "description": description
        }

    def _is_sheng(self, from_wx: str, to_wx: str) -> bool:
        """判断五行 A 是否生五行 B"""
        sheng_map = {
            "木": "火",
            "火": "土",
            "土": "金",
            "金": "水",
            "水": "木"
        }
        return sheng_map.get(from_wx) == to_wx

    def _is_ke(self, from_wx: str, to_wx: str) -> bool:
        """判断五行 A 是否克五行 B"""
        ke_map = {
            "木": "土",
            "土": "水",
            "水": "火",
            "火": "金",
            "金": "木"
        }
        return ke_map.get(from_wx) == to_wx