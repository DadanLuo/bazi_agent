# src/core/city_coords.py
"""城市名称 → 经纬度映射（与前端 static/index.html 下拉框一致）"""
from typing import Optional, Tuple

CITY_COORDS = {
    "北京": (116.4, 39.9),
    "上海": (121.5, 31.2),
    "广州": (113.3, 23.1),
    "深圳": (114.1, 22.5),
    "成都": (104.1, 30.7),
    "重庆": (106.6, 29.6),
    "杭州": (120.2, 30.3),
    "南京": (118.8, 32.1),
    "武汉": (114.3, 30.6),
    "济南": (117.0, 36.7),
    "长沙": (113.0, 28.2),
    "西安": (108.9, 34.3),
    "哈尔滨": (126.6, 45.8),
    "沈阳": (123.4, 41.8),
    "乌鲁木齐": (87.6, 43.8),
    "拉萨": (91.1, 29.7),
}


def resolve_city_coords(birth_place: str) -> Optional[Tuple[float, float]]:
    """
    将城市名解析为 (longitude, latitude)。
    支持模糊匹配："成都市"、"四川成都" 均可命中 "成都"。
    未匹配返回 None。
    """
    if not birth_place:
        return None
    # 精确匹配
    if birth_place in CITY_COORDS:
        return CITY_COORDS[birth_place]
    # 去掉常见后缀后匹配
    cleaned = birth_place.rstrip("市省区县")
    if cleaned in CITY_COORDS:
        return CITY_COORDS[cleaned]
    # 子串匹配（"四川成都" 包含 "成都"）
    for city, coords in CITY_COORDS.items():
        if city in birth_place:
            return coords
    return None
