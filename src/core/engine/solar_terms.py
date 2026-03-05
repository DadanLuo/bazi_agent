"""
高精度节气计算与真太阳时校正模块 (修复版)
依赖：ephem
"""
import ephem
import math
import logging
from datetime import datetime, timedelta
from typing import Dict, Tuple

logger = logging.getLogger(__name__)


class SolarTermsCalculator:
    """
    基于天文算法的节气与真太阳时计算器
    """

    # 二十四节气对应的太阳黄经
    TERMS_ANGLES = {
        "小寒": 285, "大寒": 300, "立春": 315, "雨水": 330,
        "惊蛰": 345, "春分": 0, "清明": 15, "谷雨": 30,
        "立夏": 45, "小满": 60, "芒种": 75, "夏至": 90,
        "小暑": 105, "大暑": 120, "立秋": 135, "处暑": 150,
        "白露": 165, "秋分": 180, "寒露": 195, "霜降": 210,
        "立冬": 225, "小雪": 240, "大雪": 255, "冬至": 270
    }

    # 反向映射：角度到名称
    ANGLE_TO_TERM = {v: k for k, v in TERMS_ANGLES.items()}

    def __init__(self):
        self.observer = ephem.Observer()
        self.observer.pressure = 0  # 忽略大气折射影响，提高天文精度

    def _get_sun_longitude(self, dt: datetime) -> float:
        """计算指定时间的太阳视黄经"""
        # 转换为 UTC
        dt_utc = dt - timedelta(hours=8)
        self.observer.date = ephem.Date(dt_utc)

        sun = ephem.Sun(self.observer)
        # 计算太阳黄经
        # ephem.Ecliptic 将赤道坐标转换为黄道坐标
        ecl = ephem.Ecliptic(sun)
        return math.degrees(ecl.lon)

    def _find_crossing_time(self, year: int, target_angle: int) -> datetime:
        """
        使用二分法精确查找太阳到达特定黄经的时间
        """
        target_rad = math.radians(target_angle)

        # 1. 粗略估算日期
        # 小寒(285度)通常在1月5-6日
        # 春分(0度)在3月20-21日
        # 每个月约移动30度
        if target_angle >= 285:  # 1月
            guess_month = 1
            guess_day = 5 + (target_angle - 285) // 15
        else:
            # 简单映射：0度(3月), 30度(4月)...
            # 平均每月移动约30度
            guess_month = 3 + target_angle // 30
            guess_day = 20

        start_dt = datetime(year, guess_month, 1)
        end_dt = datetime(year, guess_month + 1, 1) if guess_month < 12 else datetime(year + 1, 1, 1)

        # 2. 二分查找
        # ephem 的 newton 方法更适合，但这里使用简单迭代
        current_dt = start_dt + (end_dt - start_dt) / 2

        for _ in range(50):  # 最多迭代50次，精度足够
            lon = self._get_sun_longitude(current_dt)

            # 归一化角度差
            diff = (math.radians(lon) - target_rad + math.pi) % (2 * math.pi) - math.pi

            if abs(diff) < 0.0001:  # 精度约 0.005 度
                return current_dt

            # 时间修正：太阳平均每天移动约0.9856度 (360/365.25)
            # diff 单位是弧度，转换为度
            days_adjust = math.degrees(diff) / 0.9856
            current_dt += timedelta(days=days_adjust)

        # logger.warning(f"节气计算收敛超时: {year}年 {target_angle}度")
        return current_dt

    def get_solar_term_datetime(self, year: int, term_name: str) -> datetime:
        """获取指定节气的精确时间"""
        target_angle = self.TERMS_ANGLES.get(term_name)
        if target_angle is None:
            raise ValueError(f"未知节气: {term_name}")

        return self._find_crossing_time(year, target_angle)

    def get_solar_terms_in_year(self, year: int) -> Dict[str, datetime]:
        """
        获取一年中所有节气时间
        """
        terms = {}
        # 注意：小寒大寒属于上一年的气，但这里为了方便排盘，
        # 我们计算当前年份包含的节气，立春是年界
        for name in self.TERMS_ANGLES.keys():
            try:
                dt = self.get_solar_term_datetime(year, name)
                # 特殊处理：如果是小寒或大寒，且时间在立春之前，它属于本年年初
                # 如果是冬至，也归入当年
                # 通常为了排盘，我们需要当年立春，和下一年的立春来判断年柱
                if name in ["小寒", "大寒"]:
                    # 这里计算的是 year 年 1月的那个小寒/大寒
                    pass
                terms[name] = dt
            except Exception as e:
                logger.error(f"计算节气 {name} 失败: {e}")
                # 使用默认估算
                terms[name] = datetime(year, 1, 6)  # fallback

        return terms

    def adjust_true_solar_time(self, dt: datetime, longitude: float, latitude: float = 39.9) -> Tuple[datetime, float]:
        """
        真太阳时校正
        """
        # 1. 经度修正 (东经120度为基准)
        lon_offset = (longitude - 120.0) * 4.0  # 分钟

        # 2. 均时差
        day_of_year = dt.timetuple().tm_yday
        B = 360.0 / 365.0 * (day_of_year - 81)
        B_rad = math.radians(B)
        # 简化的均时差公式 (分钟)
        eot = 9.87 * math.sin(2 * B_rad) - 7.53 * math.cos(B_rad) - 1.5 * math.sin(B_rad)

        total_offset = lon_offset + eot
        adjusted_dt = dt + timedelta(minutes=total_offset)

        return adjusted_dt, total_offset

    def get_month_pillar_dizhi(self, adjusted_dt: datetime, year_terms: Dict[str, datetime]) -> str:
        """根据节气判定月支"""
        # 获取立春时间
        lichun = year_terms.get("立春")
        if not lichun:
            return "寅"  # Fallback

        # 立春前为丑月
        if adjusted_dt < lichun:
            return "丑"

        # 节气序列
        sequence = [
            ("立春", "寅"), ("惊蛰", "卯"), ("清明", "辰"),
            ("立夏", "巳"), ("芒种", "午"), ("小暑", "未"),
            ("立秋", "申"), ("白露", "酉"), ("寒露", "戌"),
            ("立冬", "亥"), ("大雪", "子"), ("小寒", "丑")
        ]

        current_dizhi = "丑"
        for term_name, dizhi in sequence:
            term_dt = year_terms.get(term_name)
            if not term_dt:
                continue
            if adjusted_dt >= term_dt:
                current_dizhi = dizhi
            else:
                # 因为节气是按时间顺序排列的，一旦当前时间小于节气时间，
                # 说明还没到这个节气，返回上一个确定的节气地支
                break

        return current_dizhi
