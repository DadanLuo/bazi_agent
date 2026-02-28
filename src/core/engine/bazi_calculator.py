"""
四柱八字核心计算引擎
"""
import math
from datetime import datetime
from typing import List, Dict, Any
from src.core.models.bazi_models import (
    BirthInfo, FourPillars, Pillar, Tiangan, Dizhi,
    WuxingScore, DayunPillar, BaziResult
)
from .wuxing_calculator import WuxingCalculator

# --- 常量定义 ---
TIANGAN_LIST = [Tiangan.JIA, Tiangan.YI, Tiangan.BING, Tiangan.DING, Tiangan.WU,
                Tiangan.JI, Tiangan.GENG, Tiangan.XIN, Tiangan.REN, Tiangan.GUI]
DIZHI_LIST = [Dizhi.ZI, Dizhi.CHOU, Dizhi.YIN, Dizhi.MAO, Dizhi.CHEN, Dizhi.SI,
              Dizhi.WU, Dizhi.WEI, Dizhi.SHEN, Dizhi.YOU, Dizhi.XU, Dizhi.HAI]

# 年干支基准：1984 年为甲子年
BASE_YEAR = 1984
BASE_TIANGAN_IDX = 0  # 甲
BASE_DIZHI_IDX = 0  # 子


class BaziCalculator:
    """八字计算主类"""

    def __init__(self):
        self.wuxing_calculator = WuxingCalculator()

    def calculate_year_pillar(self, year: int) -> Pillar:
        """计算年柱"""
        tg_idx = (year - BASE_YEAR) % 10
        dz_idx = (year - BASE_YEAR) % 12
        return Pillar(
            tiangan=TIANGAN_LIST[tg_idx],
            dizhi=DIZHI_LIST[dz_idx]
        )

    def calculate_month_pillar(self, year: int, month: int, day: int) -> Pillar:
        """
        计算月柱
        简化逻辑：暂按农历月份或节气粗略计算
        """
        year_pillar = self.calculate_year_pillar(year)
        year_tg_idx = TIANGAN_LIST.index(year_pillar.tiangan)

        # 五虎遁年起月法
        start_map = {0: 2, 5: 2, 1: 4, 6: 4, 2: 6, 7: 6, 3: 8, 8: 8, 4: 0, 9: 0}
        start_tg_idx = start_map.get(year_tg_idx, 2)

        dz_idx = (month - 1 + 2) % 12
        tg_idx = (start_tg_idx + month - 1) % 10

        return Pillar(tiangan=TIANGAN_LIST[tg_idx], dizhi=DIZHI_LIST[dz_idx])

    def calculate_day_pillar(self, year: int, month: int, day: int) -> Pillar:
        """
        计算日柱
        使用基准日推算法
        """
        base_date = datetime(1900, 1, 1)
        target_date = datetime(year, month, day)
        delta_days = (target_date - base_date).days

        base_tg = 0
        base_dz = 10

        tg_idx = (base_tg + delta_days) % 10
        dz_idx = (base_dz + delta_days) % 12

        return Pillar(tiangan=TIANGAN_LIST[tg_idx], dizhi=DIZHI_LIST[dz_idx])

    def calculate_hour_pillar(self, day: int, hour: int, day_pillar: Pillar) -> Pillar:
        """
        计算时柱
        五鼠遁日起时法
        """
        day_tg_idx = TIANGAN_LIST.index(day_pillar.tiangan)

        start_map = {0: 0, 5: 0, 1: 2, 6: 2, 2: 4, 7: 4, 3: 6, 8: 6, 4: 8, 9: 8}
        start_tg_idx = start_map.get(day_tg_idx, 0)

        dz_idx = ((hour + 1) // 2) % 12
        tg_idx = (start_tg_idx + dz_idx) % 10

        return Pillar(tiangan=TIANGAN_LIST[tg_idx], dizhi=DIZHI_LIST[dz_idx])

    def calculate_wuxing_score(self, pillars: FourPillars) -> WuxingScore:
        """
        统计五行分数（使用新的规则计算器）
        """
        return self.wuxing_calculator.calculate_total_score(pillars)

    def calculate_dayun(self, birth_info: BirthInfo, pillars: FourPillars) -> List[DayunPillar]:
        """
        计算大运
        阳男阴女顺排，阴男阳女逆排
        """
        dayun_list = []
        start_age = 3

        current_pillar = pillars.month
        for i in range(8):
            tg_idx = (TIANGAN_LIST.index(current_pillar.tiangan) + i + 1) % 10
            dz_idx = (DIZHI_LIST.index(current_pillar.dizhi) + i + 1) % 12

            dp = DayunPillar(
                start_age=start_age + i * 10,
                pillar=Pillar(tiangan=TIANGAN_LIST[tg_idx], dizhi=DIZHI_LIST[dz_idx])
            )
            dayun_list.append(dp)

        return dayun_list

    def calculate(self, birth_info: BirthInfo) -> BaziResult:
        """
        完整排盘流程
        """
        year_pillar = self.calculate_year_pillar(birth_info.year)
        month_pillar = self.calculate_month_pillar(birth_info.year, birth_info.month, birth_info.day)
        day_pillar = self.calculate_day_pillar(birth_info.year, birth_info.month, birth_info.day)
        hour_pillar = self.calculate_hour_pillar(birth_info.day, birth_info.hour, day_pillar)

        four_pillars = FourPillars(
            year=year_pillar,
            month=month_pillar,
            day=day_pillar,
            hour=hour_pillar
        )

        wuxing_score = self.calculate_wuxing_score(four_pillars)
        dayun = self.calculate_dayun(birth_info, four_pillars)

        return BaziResult(
            birth_info=birth_info,
            four_pillars=four_pillars,
            wuxing_score=wuxing_score,
            dayun=dayun
        )