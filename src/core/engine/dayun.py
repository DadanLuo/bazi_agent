"""
大运计算引擎
基于《子平真诠》《滴天髓》规则
"""
import logging
from typing import Dict, List, Tuple, Optional
from datetime import datetime
from src.core.models.bazi_models import FourPillars, Pillar, Tiangan, Dizhi, DayunPillar
from .solar_terms import SolarTermsCalculator
from .wuxing_calculator import WuxingCalculator
from .yongshen import YongshenEngine
from .geju import GejuEngine

logger = logging.getLogger(__name__)


class DayunEngine:
    """
    大运计算引擎

    核心规则：
    1. 起运数：根据出生日到最近节气的天数计算（3天折1年）
    2. 顺逆：
       - 阳男阴女：顺行（从月柱向后推）
       - 阴男阳女：逆行（从月柱向前推）
    3. 每步大运管10年
    """

    # 天干地支列表
    TIANGAN_LIST = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
    DIZHI_LIST = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]

    # 阳干阳支
    YANG_TIANGAN = ["甲", "丙", "戊", "庚", "壬"]
    YANG_DIZHI = ["子", "寅", "辰", "午", "申", "戌"]

    def __init__(self):
        self.solar_calculator = SolarTermsCalculator()
        self.wuxing_calc = WuxingCalculator()
        self.yongshen_engine = YongshenEngine()
        self.geju_engine = GejuEngine()

    def calculate_qiyun_age(self, birth_dt: datetime, gender: str,
                            year_pillar: Pillar, year_terms: Dict) -> Tuple[int, str]:
        """
        计算起运年龄

        Args:
            birth_dt: 出生时间（真太阳时）
            gender: 性别 ("男" 或 "女")
            year_pillar: 年柱
            year_terms: 节气字典

        Returns:
            (起运年龄, 起运方向描述)
        """
        # 1. 判断年柱阴阳
        year_tg = year_pillar.tiangan.value
        is_yang_year = year_tg in self.YANG_TIANGAN

        # 2. 确定顺逆方向
        # 阳男阴女顺行，阴男阳女逆行
        is_shun = (is_yang_year and gender == "男") or (not is_yang_year and gender == "女")

        direction = "顺行" if is_shun else "逆行"

        # 3. 找到最近的节气
        # 出生时间前后的节气
        nearest_term_before = None
        nearest_term_after = None
        min_diff_before = float('inf')
        min_diff_after = float('inf')

        # 节气节点（只看"节"，不看"气"）
        jie_terms = ["立春", "惊蛰", "清明", "立夏", "芒种", "小暑",
                     "立秋", "白露", "寒露", "立冬", "大雪", "小寒"]

        for term_name in jie_terms:
            term_dt = year_terms.get(term_name)
            if not term_dt:
                continue

            diff = (birth_dt - term_dt).total_seconds()

            if diff > 0 and diff < min_diff_before:
                min_diff_before = diff
                nearest_term_before = (term_name, term_dt)
            elif diff < 0 and abs(diff) < min_diff_after:
                min_diff_after = abs(diff)
                nearest_term_after = (term_name, term_dt)

        # 4. 计算到最近节气的天数
        if is_shun:
            # 顺行：计算到下一个节气的天数
            if nearest_term_after:
                days_to_term = (nearest_term_after[1] - birth_dt).days
            else:
                # 容错
                days_to_term = 3
        else:
            # 逆行：计算到上一个节气的天数
            if nearest_term_before:
                days_to_term = (birth_dt - nearest_term_before[1]).days
            else:
                days_to_term = 3

        # 5. 计算起运年龄
        # 3天 = 1年，1天 = 4个月
        # 四舍五入
        qiyun_years = round(days_to_term / 3.0)

        # 最小起运年龄为1岁
        qiyun_years = max(1, qiyun_years)

        logger.info(f"起运计算：天数={days_to_term}, 起运年龄={qiyun_years}, 方向={direction}")

        return qiyun_years, direction

    def generate_dayun_sequence(self, month_pillar: Pillar, is_shun: bool,
                                steps: int = 8) -> List[Pillar]:
        """
        生成大运序列

        Args:
            month_pillar: 月柱
            is_shun: 是否顺行
            steps: 生成步数（默认8步，80年）

        Returns:
            大运干支列表
        """
        dayun_sequence = []

        current_tg_idx = self.TIANGAN_LIST.index(month_pillar.tiangan.value)
        current_dz_idx = self.DIZHI_LIST.index(month_pillar.dizhi.value)

        for i in range(1, steps + 1):
            if is_shun:
                tg_idx = (current_tg_idx + i) % 10
                dz_idx = (current_dz_idx + i) % 12
            else:
                tg_idx = (current_tg_idx - i) % 10
                dz_idx = (current_dz_idx - i) % 12

            dayun_pillar = Pillar(
                tiangan=Tiangan(self.TIANGAN_LIST[tg_idx]),
                dizhi=Dizhi(self.DIZHI_LIST[dz_idx])
            )
            dayun_sequence.append(dayun_pillar)

        return dayun_sequence

    def analyze_dayun(self, pillars: FourPillars, yongshen_result: Dict,
                      birth_dt: datetime, gender: str,
                      year_terms: Dict, current_age: int = None) -> Dict:
        """
        分析大运

        Args:
            pillars: 四柱
            yongshen_result: 喜用神结果
            birth_dt: 出生时间
            gender: 性别
            year_terms: 节气字典
            current_age: 当前年龄（用于定位当前大运）

        Returns:
            大运分析结果
        """
        logger.info("开始大运分析...")

        # 1. 计算起运年龄和方向
        qiyun_age, direction = self.calculate_qiyun_age(
            birth_dt, gender, pillars.year, year_terms
        )

        # 2. 生成大运序列
        is_shun = direction == "顺行"
        dayun_sequence = self.generate_dayun_sequence(pillars.month, is_shun, steps=8)

        # 3. 构建大运列表
        dayun_list = []
        for i, pillar in enumerate(dayun_sequence):
            start_age = qiyun_age + i * 10
            end_age = start_age + 10

            dayun_item = DayunPillar(
                start_age=start_age,
                pillar=pillar
            )

            # 分析该步大运
            analysis = self._analyze_single_dayun(
                pillar, pillars, yongshen_result, start_age, end_age
            )

            dayun_list.append({
                "pillar": dayun_item,
                "analysis": analysis,
                "age_range": f"{start_age}-{end_age}岁"
            })

        # 4. 定位当前大运
        current_dayun = None
        if current_age is not None:
            for dayun_item in dayun_list:
                start_age = dayun_item["pillar"].start_age
                end_age = start_age + 10
                if start_age <= current_age < end_age:
                    current_dayun = dayun_item
                    break

        # 5. 综合分析
        overall_analysis = self._generate_overall_analysis(
            dayun_list, yongshen_result, current_dayun
        )

        result = {
            "qiyun_age": qiyun_age,
            "direction": direction,
            "dayun_list": dayun_list,
            "current_dayun": current_dayun,
            "overall_analysis": overall_analysis
        }

        logger.info(f"大运分析完成：起运{qiyun_age}岁，{direction}")
        return result

    def _analyze_single_dayun(self, dayun_pillar: Pillar, pillars: FourPillars,
                              yongshen_result: Dict, start_age: int, end_age: int) -> Dict:
        """
        分析单步大运
        """
        yongshen = yongshen_result.get("yongshen", [])
        jishen = yongshen_result.get("jishen", [])

        # 获取大运天干地支五行
        tg_wx = self.wuxing_calc.rule_loader.get_tiangan_wuxing().get(
            dayun_pillar.tiangan.value, "土"
        )
        dz_wx = self.wuxing_calc.rule_loader.get_dizhi_wuxing().get(
            dayun_pillar.dizhi.value, "土"
        )

        # 判断喜忌
        tg_relation = "平"
        dz_relation = "平"

        if tg_wx in yongshen:
            tg_relation = "喜"
        elif tg_wx in jishen:
            tg_relation = "忌"

        if dz_wx in yongshen:
            dz_relation = "喜"
        elif dz_wx in jishen:
            dz_relation = "忌"

        # 计算吉凶分数（-100 到 100）
        score = 0
        if tg_relation == "喜":
            score += 40
        elif tg_relation == "忌":
            score -= 40

        if dz_relation == "喜":
            score += 60  # 地支力量更强
        elif dz_relation == "忌":
            score -= 60

        # 判断等级
        if score >= 60:
            level = "大吉"
            desc = "运势极佳，宜积极进取"
        elif score >= 30:
            level = "吉"
            desc = "运势较好，机遇较多"
        elif score >= 0:
            level = "平吉"
            desc = "运势平稳，稳中求进"
        elif score >= -30:
            level = "平凶"
            desc = "运势一般，谨慎行事"
        else:
            level = "凶"
            desc = "运势较差，宜守不宜进"

        # 生成建议
        advice = self._generate_dayun_advice(level, tg_wx, dz_wx, yongshen)

        return {
            "tiangan_wuxing": tg_wx,
            "dizhi_wuxing": dz_wx,
            "tg_relation": tg_relation,
            "dz_relation": dz_relation,
            "score": score,
            "level": level,
            "description": desc,
            "advice": advice
        }

    def _generate_dayun_advice(self, level: str, tg_wx: str, dz_wx: str,
                               yongshen: List[str]) -> List[str]:
        """生成大运建议"""
        advice = []

        # 根据吉凶等级
        if level in ["大吉", "吉"]:
            advice.append("宜积极进取，把握机遇")
            advice.append("适合投资、创业、重要决策")
        elif level == "平吉":
            advice.append("稳步发展，不宜冒进")
        else:
            advice.append("宜守不宜进，谨慎行事")
            advice.append("避免重大投资和风险决策")

        # 根据五行
        wuxing_advice = {
            "木": "利于教育、文化、创意行业",
            "火": "利于科技、网络、娱乐行业",
            "土": "利于房地产、建筑、农业",
            "金": "利于金融、法律、管理",
            "水": "利于贸易、物流、服务业"
        }

        if tg_wx in yongshen or dz_wx in yongshen:
            advice.append(wuxing_advice.get(tg_wx, ""))

        return [a for a in advice if a]  # 过滤空字符串

    def _generate_overall_analysis(self, dayun_list: List[Dict],
                                   yongshen_result: Dict,
                                   current_dayun: Dict) -> str:
        """生成大运总体分析文本"""
        yongshen = yongshen_result.get("yongshen", [])

        # 统计吉凶
        good_count = 0
        bad_count = 0

        for dayun_item in dayun_list:
            level = dayun_item["analysis"]["level"]
            if level in ["大吉", "吉"]:
                good_count += 1
            elif level in ["平凶", "凶"]:
                bad_count += 1

        # 生成分析文本
        text = f"大运共{len(dayun_list)}步，"

        if good_count > bad_count:
            text += f"吉运{good_count}步，凶运{bad_count}步，整体运势较好。"
        elif good_count < bad_count:
            text += f"吉运{good_count}步，凶运{bad_count}步，需注意把握时机。"
        else:
            text += "吉凶参半，起伏较大。"

        if current_dayun:
            text += f"当前正处于{current_dayun['age_range']}大运，"
            text += f"{current_dayun['analysis']['description']}。"

        return text
