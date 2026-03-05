"""
四柱八字核心计算引擎 (高精度版)
修复：
1. 月柱计算 - 基于天文节气
2. 时柱计算 - 早晚子时严格区分
3. 真太阳时 - 基于经纬度校正
4. 大运计算 - 基于节气天数和阴阳顺逆
"""
import math
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple
from src.core.models.bazi_models import (
    BirthInfo, FourPillars, Pillar, Tiangan, Dizhi,
    WuxingScore, DayunPillar, BaziResult
)
from .wuxing_calculator import WuxingCalculator
from .solar_terms import SolarTermsCalculator
from .dayun import DayunEngine

# --- 常量定义 ---
TIANGAN_LIST = [Tiangan.JIA, Tiangan.YI, Tiangan.BING, Tiangan.DING, Tiangan.WU,
                Tiangan.JI, Tiangan.GENG, Tiangan.XIN, Tiangan.REN, Tiangan.GUI]
DIZHI_LIST = [Dizhi.ZI, Dizhi.CHOU, Dizhi.YIN, Dizhi.MAO, Dizhi.CHEN, Dizhi.SI,
              Dizhi.WU, Dizhi.WEI, Dizhi.SHEN, Dizhi.YOU, Dizhi.XU, Dizhi.HAI]

BASE_YEAR = 1984
BASE_TIANGAN_IDX = 0
BASE_DIZHI_IDX = 0


class BaziCalculator:
    def __init__(self):
        self.wuxing_calculator = WuxingCalculator()
        self.solar_calculator = SolarTermsCalculator()
        self.dayun_engine = DayunEngine()

    def _get_adjusted_time(self, birth_info: BirthInfo) -> Tuple[datetime, Dict]:
        """
        执行真太阳时校正并获取所需节气数据
        """
        # 1. 构建初始时间对象
        input_dt = datetime(
            birth_info.year, birth_info.month, birth_info.day,
            birth_info.hour, birth_info.minute, 0
        )

        # 2. 真太阳时校正
        # 如果没有提供经纬度，使用北京时间（东经120度）
        lon = birth_info.longitude if birth_info.longitude is not None else 120.0
        lat = birth_info.latitude if birth_info.latitude is not None else 30.0

        adjusted_dt, offset = self.solar_calculator.adjust_true_solar_time(
            input_dt, lon, lat
        )

        # 3. 获取节气表
        # 注意：需要获取当前年和上一年的节气表，以处理年初出生的情况
        terms_current_year = self.solar_calculator.get_solar_terms_in_year(birth_info.year)
        terms_prev_year = self.solar_calculator.get_solar_terms_in_year(birth_info.year - 1)

        # 合并节气表，确保能取到上一年的立春或今年的小寒
        all_terms = {**terms_prev_year, **terms_current_year}

        return adjusted_dt, all_terms

    def calculate_year_pillar(self, year: int, adjusted_dt: datetime, year_terms: Dict) -> Pillar:
        """
        计算年柱
        严格以立春为界
        """
        # 获取当年的立春时间
        lichun_key = "立春"
        lichun_dt = year_terms.get(lichun_key)

        if not lichun_dt:
            # 兜底逻辑
            actual_year = year
        else:
            # 如果出生时间在立春之前，年份减一
            if adjusted_dt < lichun_dt:
                actual_year = year - 1
            else:
                actual_year = year

        tg_idx = (actual_year - BASE_YEAR) % 10
        dz_idx = (actual_year - BASE_YEAR) % 12

        return Pillar(
            tiangan=TIANGAN_LIST[tg_idx],
            dizhi=DIZHI_LIST[dz_idx]
        )

    def calculate_month_pillar(self, adjusted_dt: datetime, year_terms: Dict, year_pillar: Pillar) -> Pillar:
        """
        计算月柱
        基于真太阳时和精确节气判定
        """
        # 1. 确定月支
        month_dizhi_val = self.solar_calculator.get_month_pillar_dizhi(adjusted_dt, year_terms)
        month_dz_idx = DIZHI_LIST.index(Dizhi(month_dizhi_val))

        # 2. 确定月干（五虎遁）
        year_tg_idx = TIANGAN_LIST.index(year_pillar.tiangan)

        # 五虎遁年起月法
        start_map = {
            0: 2, 5: 2,  # 甲己 -> 丙寅起
            1: 4, 6: 4,  # 乙庚 -> 戊寅起
            2: 6, 7: 6,  # 丙辛 -> 庚寅起
            3: 8, 8: 8,  # 丁壬 -> 壬寅起
            4: 0, 9: 0  # 戊癸 -> 甲寅起
        }
        start_tg_idx = start_map.get(year_tg_idx, 2)

        # 寅月对应的索引是 2 (DIZHI_LIST[2] == 寅)
        # 天干索引 = (起始天干 + (地支索引 - 寅索引)) % 10
        tg_idx = (start_tg_idx + (month_dz_idx - 2)) % 10

        return Pillar(tiangan=TIANGAN_LIST[tg_idx], dizhi=DIZHI_LIST[month_dz_idx])

    def calculate_day_pillar(self, adjusted_dt: datetime) -> Pillar:
        """
        计算日柱
        处理早晚子时：

        规则：
        - 早子时（00:00-01:00）：属于新的一天，日柱为新一天
        - 晚子时（23:00-24:00）：属于当天的最后时段，日柱为当天（还是第二天？）

        【重要决策】
        根据正统八字历法，"子时换日"：
        23:00 即为新的一天开始。
        即：23:00-24:00 是新一天的【早子时】（部分流派称晚子时，但日柱算新一天）。
        为了避免歧义，本项目采用标准天文日与八字历法结合：
        即：过了 23:00 (Local Apparent Time)，日柱干支即变为下一柱。
        """

        calc_date = adjusted_dt

        # 判断是否进入子时 (23:00-01:00)
        # 如果是 23:00 以后，算作下一天的早子时
        if adjusted_dt.hour >= 23:
            # 推进一天（或算作下一天的干支）
            # 这里我们取下一天的干支
            calc_date = adjusted_dt + timedelta(hours=1)  # 强制加一小时变成第二天00点计算

        # 基准日计算法
        base_date = datetime(1900, 1, 1)  # 甲戌日
        target_date = datetime(calc_date.year, calc_date.month, calc_date.day)
        delta_days = (target_date - base_date).days

        base_tg = 0  # 甲
        base_dz = 10  # 戌

        tg_idx = (base_tg + delta_days) % 10
        dz_idx = (base_dz + delta_days) % 12

        return Pillar(tiangan=TIANGAN_LIST[tg_idx], dizhi=DIZHI_LIST[dz_idx])

    def calculate_hour_pillar(self, hour: int, minute: int, day_pillar: Pillar) -> Pillar:
        """
        计算时柱
        处理早晚子时的天干区分

        规则：
        - 23:00-00:00 (晚子时/夜子时): 天干用当天的日柱推算？还是下一天的？
          正统：23:00已经换日，所以日柱是新的一天，时柱是子时（早子时）。
          但部分流派认为 23:00-00:00 是"晚子时"，天干用当天的。
          这里采用最主流的"子时换日"标准，即：
          凡是 23:00-01:00，均为子时，且日柱已换。
          但为了兼容极少数情况，我们还是区分 hour == 23 和 hour == 0 的地支计算。

        【最终逻辑】
        - hour: 23 -> 地支子，天干跟随新一天的日柱
        - hour: 0  -> 地支子，天干跟随新一天的日柱
        - hour: 1  -> 地支丑...

        注意：输入参数 `day_pillar` 应该是经过 calculate_day_pillar 处理过的（已修正晚子时换日问题）
        """
        day_tg_idx = TIANGAN_LIST.index(day_pillar.tiangan)

        # 五鼠遁日起时法
        start_map = {
            0: 0, 5: 0,  # 甲己 -> 甲子起
            1: 2, 6: 2,  # 乙庚 -> 丙子起
            2: 4, 7: 4,  # 丙辛 -> 戊子起
            3: 6, 8: 6,  # 丁壬 -> 庚子起
            4: 8, 9: 8  # 戊癸 -> 壬子起
        }
        start_tg_idx = start_map.get(day_tg_idx, 0)

        # 计算地支索引
        dz_idx = 0

        if hour == 23:
            # 晚子时，地支为子(0)
            dz_idx = 0
        elif hour == 0 or hour == 1:
            # 早子时(0-1点)，地支为子(0)
            # 注意：如果 hour=0，代表 00:00-01:00
            dz_idx = 0
        else:
            # 丑(1-3), 寅(3-5)...
            # 通用公式：(hour + 1) // 2
            # hour=1 -> 1; hour=3 -> 2
            dz_idx = (hour + 1) // 2 % 12

        # 计算天干
        tg_idx = (start_tg_idx + dz_idx) % 10

        return Pillar(tiangan=TIANGAN_LIST[tg_idx], dizhi=DIZHI_LIST[dz_idx])

    def calculate_wuxing_score(self, pillars: FourPillars) -> WuxingScore:
        """
        统计五行分数（使用新的规则计算器）
        """
        return self.wuxing_calculator.calculate_total_score(pillars)

    def calculate_dayun(self, birth_info: BirthInfo, pillars: FourPillars,
                        adjusted_dt: datetime, year_terms: Dict) -> List[DayunPillar]:
        """
        计算大运（返回基础干支列表）
        详细分析在 DayunEngine 中进行
        """
        # 计算起运年龄和方向
        qiyun_age, direction = self.dayun_engine.calculate_qiyun_age(
            adjusted_dt, birth_info.gender, pillars.year, year_terms
        )

        is_shun = direction == "顺行"

        # 生成大运序列
        dayun_sequence = self.dayun_engine.generate_dayun_sequence(
            pillars.month, is_shun, steps=8
        )

        # 构建返回对象
        dayun_list = []
        for i, pillar in enumerate(dayun_sequence):
            dayun_list.append(DayunPillar(
                start_age=qiyun_age + i * 10,
                pillar=pillar
            ))

        return dayun_list

    def calculate(self, birth_info: BirthInfo) -> BaziResult:
        """
        完整排盘流程
        """
        # 1. 时间校正与节气获取
        adjusted_dt, year_terms = self._get_adjusted_time(birth_info)

        # 2. 计算年柱 (依赖立春)
        year_pillar = self.calculate_year_pillar(birth_info.year, adjusted_dt, year_terms)

        # 3. 计算日柱 (依赖早晚子时，此步骤必须在时柱之前)
        # 注意：calculate_day_pillar 内部已经处理了 23:00 换日逻辑
        day_pillar = self.calculate_day_pillar(adjusted_dt)

        # 4. 计算月柱 (依赖节气)
        month_pillar = self.calculate_month_pillar(adjusted_dt, year_terms, year_pillar)

        # 5. 计算时柱 (依赖日柱)
        hour_pillar = self.calculate_hour_pillar(adjusted_dt.hour, adjusted_dt.minute, day_pillar)

        four_pillars = FourPillars(
            year=year_pillar,
            month=month_pillar,
            day=day_pillar,
            hour=hour_pillar
        )

        wuxing_score = self.calculate_wuxing_score(four_pillars)

        # 6. 计算大运（传入额外参数）
        dayun = self.calculate_dayun(birth_info, four_pillars, adjusted_dt, year_terms)

        return BaziResult(
            birth_info=birth_info,
            four_pillars=four_pillars,
            wuxing_score=wuxing_score,
            dayun=dayun
        )
