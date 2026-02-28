"""
四柱八字数据模型定义
基于 Pydantic V2 规范重构
"""
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict, model_validator
from typing_extensions import Literal

# --- 枚举定义 ---

class Tiangan(str, Enum):
    """十天干"""
    JIA = "甲"
    YI = "乙"
    BING = "丙"
    DING = "丁"
    WU = "戊"
    JI = "己"
    GENG = "庚"
    XIN = "辛"
    REN = "壬"
    GUI = "癸"

class Dizhi(str, Enum):
    """十二地支"""
    ZI = "子"
    CHOU = "丑"
    YIN = "寅"
    MAO = "卯"
    CHEN = "辰"
    SI = "巳"
    WU = "午"
    WEI = "未"
    SHEN = "申"
    YOU = "酉"
    XU = "戌"
    HAI = "亥"

class Wuxing(str, Enum):
    """五行"""
    MU = "木"
    HUO = "火"
    TU = "土"
    JIN = "金"
    SHUI = "水"

# --- 基础模型 ---

class Pillar(BaseModel):
    """单柱模型（如年柱、月柱等）"""
    tiangan: Tiangan = Field(..., description="天干")
    dizhi: Dizhi = Field(..., description="地支")

    @property
    def wuxing(self) -> Dict[str, str]:
        """返回天干地支对应的五行（简化版，实际需查表）"""
        # 这里仅作示例，实际逻辑应在 calculator 或工具函数中
        return {"tiangan_wx": "木", "dizhi_wx": "木"}

    def __str__(self):
        return f"{self.tiangan.value}{self.dizhi.value}"

class FourPillars(BaseModel):
    """四柱模型"""
    year: Pillar = Field(..., description="年柱")
    month: Pillar = Field(..., description="月柱")
    day: Pillar = Field(..., description="日柱")
    hour: Pillar = Field(..., description="时柱")

class WuxingScore(BaseModel):
    """五行分数统计"""
    mu: int = Field(0, description="木")
    huo: int = Field(0, description="火")
    tu: int = Field(0, description="土")
    jin: int = Field(0, description="金")
    shui: int = Field(0, description="水")

    def total(self) -> int:
        return self.mu + self.huo + self.tu + self.jin + self.shui

class DayunPillar(BaseModel):
    """大运单柱"""
    start_age: int = Field(..., description="起运年龄")
    pillar: Pillar = Field(..., description="大运干支")

class BirthInfo(BaseModel):
    """用户出生信息输入"""
    year: int = Field(..., ge=1900, le=2100, description="出生年份")
    month: int = Field(..., ge=1, le=12, description="出生月份")
    day: int = Field(..., ge=1, le=31, description="出生日期")
    hour: int = Field(..., ge=0, le=23, description="出生时辰（0-23）")
    # 严格限制为 '男' 或 '女'，避免编码问题
    gender: Literal["男", "女"] = Field(..., description="性别")
    timezone: str = Field("Asia/Shanghai", description="时区")
    latitude: Optional[float] = Field(None, description="纬度（用于真太阳时）")
    longitude: Optional[float] = Field(None, description="经度（用于真太阳时）")

class BaziResult(BaseModel):
    """排盘最终结果"""
    # 使用 Pydantic V2 的 ConfigDict 替代旧的 class Config
    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.strftime("%Y-%m-%d %H:%M:%S") if v else None,
        },
        extra="ignore"  # 忽略多余字段
    )

    birth_info: BirthInfo = Field(..., description="原始出生信息")
    four_pillars: FourPillars = Field(..., description="四柱八字")
    wuxing_score: WuxingScore = Field(default_factory=WuxingScore, description="五行分数")
    dayun: List[DayunPillar] = Field(default_factory=list, description="大运列表")
    calculate_time: datetime = Field(default_factory=datetime.now, description="计算时间")

    def to_dict(self) -> Dict[str, Any]:
        """兼容序列化的方法"""
        return self.model_dump()