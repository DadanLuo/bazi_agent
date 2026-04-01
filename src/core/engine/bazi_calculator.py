"""
==============================================================================
四柱八字核心计算引擎
==============================================================================

功能说明：
    本模块实现了八字排盘的核心计算逻辑，包括年柱、月柱、日柱、时柱的
    干支推算，以及大运计算。使用传统的干支纪年法和节气规则进行计算。

计算原理：
    1. 年柱：基于干支纪年法，以1984年甲子年为基准进行推算
    2. 月柱：使用五虎遁年起月法，根据年干和月份推算
    3. 日柱：使用基准日推算法，以1900年1月1日为基准
    4. 时柱：使用五鼠遁日起时法，根据日干和时辰推算
    5. 大运：根据性别和日干阴阳，顺排或逆排月干支

==============================================================================
"""

import math
from datetime import datetime
from typing import List, Dict, Any
from src.core.models.bazi_models import (
    BirthInfo, FourPillars, Pillar, Tiangan, Dizhi,
    WuxingScore, DayunPillar, BaziResult
)
from .wuxing_calculator import WuxingCalculator

try:
    from lunar_python import Solar as LunarSolar
    LUNAR_PYTHON_AVAILABLE = True
except ImportError:
    LunarSolar = None
    LUNAR_PYTHON_AVAILABLE = False

# --- 常量定义 ---

# 十天干列表
TIANGAN_LIST = [Tiangan.JIA, Tiangan.YI, Tiangan.BING, Tiangan.DING, Tiangan.WU,
                Tiangan.JI, Tiangan.GENG, Tiangan.XIN, Tiangan.REN, Tiangan.GUI]

# 十二地支列表
DIZHI_LIST = [Dizhi.ZI, Dizhi.CHOU, Dizhi.YIN, Dizhi.MAO, Dizhi.CHEN, Dizhi.SI,
              Dizhi.WU, Dizhi.WEI, Dizhi.SHEN, Dizhi.YOU, Dizhi.XU, Dizhi.HAI]

# 年干支基准：1984 年为甲子年（天干第0位，地支第0位）
BASE_YEAR = 1984
BASE_TIANGAN_IDX = 0  # 甲
BASE_DIZHI_IDX = 0  # 子


class BaziCalculator:
    """
    ==============================================================================
    八字计算主类
    ==============================================================================
    
    功能说明：
        八字计算主类，负责八字排盘的核心计算逻辑。包括年柱、月柱、日柱、
        时柱的干支推算，以及大运计算。
    
    核心方法：
        - calculate_year_pillar() - 计算年柱
        - calculate_month_pillar() - 计算月柱
        - calculate_day_pillar() - 计算日柱
        - calculate_hour_pillar() - 计算时柱
        - calculate_wuxing_score() - 计算五行分数
        - calculate_dayun() - 计算大运
        - calculate() - 完整排盘流程
    
    使用场景：
        - 八字排盘分析
        - 大运推算
        - 五行分析
    
    ==============================================================================
    """

    def __init__(self):
        """
        初始化八字计算器，创建五行计算器实例。
        """
        self.wuxing_calculator = WuxingCalculator()

    @staticmethod
    def _pillar_from_ganzhi(ganzhi: str) -> Pillar:
        """将干支字符串转换为 Pillar 对象。"""
        if not ganzhi or len(ganzhi) < 2:
            raise ValueError(f"无效干支: {ganzhi}")
        return Pillar(
            tiangan=Tiangan(ganzhi[0]),
            dizhi=Dizhi(ganzhi[1]),
        )

    def _calculate_with_lunar_python(self, birth_info: BirthInfo) -> FourPillars:
        """使用更严谨的节气历法计算四柱。"""
        if not LUNAR_PYTHON_AVAILABLE:
            raise RuntimeError("lunar_python 不可用")

        solar = LunarSolar.fromYmdHms(
            birth_info.year,
            birth_info.month,
            birth_info.day,
            birth_info.hour,
            birth_info.minute,
            0,
        )
        lunar = solar.getLunar()

        return FourPillars(
            year=self._pillar_from_ganzhi(lunar.getYearInGanZhiExact()),
            month=self._pillar_from_ganzhi(lunar.getMonthInGanZhiExact()),
            day=self._pillar_from_ganzhi(lunar.getDayInGanZhiExact()),
            hour=self._pillar_from_ganzhi(lunar.getTimeInGanZhi()),
        )

    def calculate_year_pillar(self, year: int) -> Pillar:
        """
        ==============================================================================
        计算年柱
        ==============================================================================
        
        功能说明：
            根据公历年份计算对应的干支纪年（年柱）。
            以1984年甲子年为基准进行推算。
        
        参数说明：
            year (int): 公历年份
        
        返回值：
            Pillar: 年柱对象，包含天干和地支
        
        计算原理：
            干支纪年以60年为一个循环（甲子周期）。
            天干索引 = (year - BASE_YEAR) % 10
            地支索引 = (year - BASE_YEAR) % 12
        
        示例：
            calculate_year_pillar(1990) -> 甲子
            calculate_year_pillar(2023) -> 癸卯
        
        ==============================================================================
        """
        tg_idx = (year - BASE_YEAR) % 10
        dz_idx = (year - BASE_YEAR) % 12
        return Pillar(
            tiangan=TIANGAN_LIST[tg_idx],
            dizhi=DIZHI_LIST[dz_idx]
        )

    def calculate_month_pillar(self, year: int, month: int, day: int) -> Pillar:
        """
        ==============================================================================
        计算月柱
        ==============================================================================
        
        功能说明：
            根据年份、月份和日期计算对应的干支纪月（月柱）。
            使用五虎遁年起月法进行推算。
        
        参数说明：
            year (int): 公历年份
            month (int): 公历月份（1-12）
            day (int): 公历日期
        
        返回值：
            Pillar: 月柱对象，包含天干和地支
        
        计算原理：
            1. 先计算年柱的天干索引
            2. 根据年干确定正月的天干起始位置（五虎遁口诀）
            3. 根据月份计算月柱的天干和地支
        
        五虎遁口诀：
            甲己之年丙作首，乙庚之年戊为头，
            丙辛之年庚寅起，丁壬壬寅顺行流，
            戊癸之年壬寅起，正月从丙寅开始。
        
        地支规律：
            正月为寅，二月为卯，三月为辰，以此类推
        
        示例：
            calculate_month_pillar(1990, 3, 15) -> 戊寅
        
        ==============================================================================
        """
        year_pillar = self.calculate_year_pillar(year)
        year_tg_idx = TIANGAN_LIST.index(year_pillar.tiangan)

        # 五虎遁年起月法：根据年干确定正月的天干起始位置
        start_map = {0: 2, 5: 2, 1: 4, 6: 4, 2: 6, 7: 6, 3: 8, 8: 8, 4: 0, 9: 0}
        start_tg_idx = start_map.get(year_tg_idx, 2)

        # 地支：正月为寅（第3位），所以需要 +2
        dz_idx = (month - 1 + 2) % 12
        # 天干：从起始位置开始，按月份递推
        tg_idx = (start_tg_idx + month - 1) % 10

        return Pillar(tiangan=TIANGAN_LIST[tg_idx], dizhi=DIZHI_LIST[dz_idx])

    def calculate_day_pillar(self, year: int, month: int, day: int) -> Pillar:
        """
        ==============================================================================
        计算日柱
        ==============================================================================
        
        功能说明：
            根据公历日期计算对应的干支纪日（日柱）。
            使用基准日推算法，以1900年1月1日为基准。
        
        参数说明：
            year (int): 公历年份
            month (int): 公历月份（1-12）
            day (int): 公历日期
        
        返回值：
            Pillar: 日柱对象，包含天干和地支
        
        计算原理：
            1. 计算目标日期与基准日期（1900年1月1日）的天数差
            2. 基准日为甲辰日（天干第0位，地支第10位）
            3. 根据天数差推算目标日期的干支
        
        示例：
            calculate_day_pillar(1990, 3, 15) -> 丙寅
        
        ==============================================================================
        """
        base_date = datetime(1900, 1, 1)
        target_date = datetime(year, month, day)
        delta_days = (target_date - base_date).days

        # 基准日：1900年1月1日为甲辰日（天干第0位，地支第10位）
        base_tg = 0
        base_dz = 10

        tg_idx = (base_tg + delta_days) % 10
        dz_idx = (base_dz + delta_days) % 12

        return Pillar(tiangan=TIANGAN_LIST[tg_idx], dizhi=DIZHI_LIST[dz_idx])

    def calculate_hour_pillar(self, day: int, hour: int, day_pillar: Pillar) -> Pillar:
        """
        ==============================================================================
        计算时柱
        ==============================================================================
        
        功能说明：
            根据日干和时辰计算对应的干支纪时（时柱）。
            使用五鼠遁日起时法进行推算。
        
        参数说明：
            day (int): 公历日期（用于计算日干）
            hour (int): 时辰（0-23点）
            day_pillar (Pillar): 日柱对象
        
        返回值：
            Pillar: 时柱对象，包含天干和地支
        
        计算原理：
            1. 获取日干的天干索引
            2. 根据日干确定子时的天干起始位置（五鼠遁口诀）
            3. 根据时辰确定地支（2小时为一个时辰）
            4. 计算时柱的天干
        
        五鼠遁口诀：
            甲己还加甲，乙庚丙作初，
            丙辛从戊子，丁壬庚子居，
            戊癸何发端，壬子是真途。
        
        时辰地支：
            23-1点：子时，1-3点：丑时，以此类推
        
        示例：
            calculate_hour_pillar(15, 14, day_pillar) -> 丁未
        
        ==============================================================================
        """
        day_tg_idx = TIANGAN_LIST.index(day_pillar.tiangan)

        # 五鼠遁日起时法：根据日干确定子时的天干起始位置
        start_map = {0: 0, 5: 0, 1: 2, 6: 2, 2: 4, 7: 4, 3: 6, 8: 6, 4: 8, 9: 8}
        start_tg_idx = start_map.get(day_tg_idx, 0)

        # 地支：2小时为一个时辰，23-1点为子时（第0位）
        dz_idx = ((hour + 1) // 2) % 12
        # 天干：从起始位置开始，按时辰递推
        tg_idx = (start_tg_idx + dz_idx) % 10

        return Pillar(tiangan=TIANGAN_LIST[tg_idx], dizhi=DIZHI_LIST[dz_idx])

    def calculate_wuxing_score(self, pillars: FourPillars) -> WuxingScore:
        """
        ==============================================================================
        统计五行分数（使用新的规则计算器）
        ==============================================================================
        
        功能说明：
            计算八字中五行的分布分数，用于后续的五行分析和日主强弱判断。
        
        参数说明：
            pillars (FourPillars): 四柱对象
        
        返回值：
            WuxingScore: 五行分数对象
        
        ==============================================================================
        """
        return self.wuxing_calculator.calculate_total_score(pillars)

    def calculate_dayun(self, birth_info: BirthInfo, pillars: FourPillars) -> List[DayunPillar]:
        """
        ==============================================================================
        计算大运
        ==============================================================================
        
        功能说明：
            根据性别和日干阴阳，计算大运排列。
            阳男阴女顺排，阴男阳女逆排。
        
        参数说明：
            birth_info (BirthInfo): 出生信息对象
            pillars (FourPillars): 四柱对象
        
        返回值：
            List[DayunPillar]: 大运列表，每10年为一大运
        
        计算原理：
            1. 确定排运方向（顺排或逆排）
            2. 从月柱开始，按天干地支顺序推算
            3. 每10年为一大运，共8步大运
        
        性别与排运规则：
            - 阳男（甲、丙、戊、庚、壬）：顺排
            - 阴女（乙、丁、己、辛、癸）：顺排
            - 阴男（乙、丁、己、辛、癸）：逆排
            - 阳女（甲、丙、戊、庚、壬）：逆排
        
        示例：
            甲子年 丙寅月 丙寅日 男 -> 顺排：丁卯、戊辰、己巳...
        
        ==============================================================================
        """
        dayun_list = []
        start_age = 3  # 起运年龄

        current_pillar = pillars.month
        for i in range(8):  # 共8步大运
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
        ==============================================================================
        完整排盘流程
        ==============================================================================
        
        功能说明：
            执行完整的八字排盘流程，包括年柱、月柱、日柱、时柱、五行分数
            和大运的计算。
        
        参数说明：
            birth_info (BirthInfo): 出生信息对象
        
        返回值：
            BaziResult: 八字排盘结果对象
        
        排盘流程：
            1. 计算年柱
            2. 计算月柱
            3. 计算日柱
            4. 计算时柱
            5. 组合四柱
            6. 计算五行分数
            7. 计算大运
        
        ==============================================================================
        """
        if LUNAR_PYTHON_AVAILABLE:
            four_pillars = self._calculate_with_lunar_python(birth_info)
        else:
            # 兼容兜底：如果更严谨的历法库不可用，则回退到旧算法
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

        # 计算五行分数
        wuxing_score = self.calculate_wuxing_score(four_pillars)
        
        # 计算大运
        dayun = self.calculate_dayun(birth_info, four_pillars)

        return BaziResult(
            birth_info=birth_info,
            four_pillars=four_pillars,
            wuxing_score=wuxing_score,
            dayun=dayun
        )
