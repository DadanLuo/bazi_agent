from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

AnalysisDepth = Literal["基础", "详细", "专业"]
GenderValue = Literal["男", "女"]


class Coordinates(BaseModel):
    latitude: float = Field(..., ge=-90, le=90, description="纬度")
    longitude: float = Field(..., ge=-180, le=180, description="经度")


class BaziChartRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    birth_datetime: datetime | None = Field(
        default=None,
        description="出生时间，支持 ISO 8601 字符串或 datetime 对象",
    )
    year: int | None = Field(default=None, ge=1900, le=2100, description="出生年份")
    month: int | None = Field(default=None, ge=1, le=12, description="出生月份")
    day: int | None = Field(default=None, ge=1, le=31, description="出生日期")
    hour: int | None = Field(default=None, ge=0, le=23, description="出生小时")
    minute: int = Field(default=0, ge=0, le=59, description="出生分钟")
    timezone: str = Field(
        default="Asia/Shanghai",
        description="IANA 时区 ID 或 UTC 偏移量，例如 Asia/Shanghai、+08:00",
    )
    gender: str = Field(..., description="性别，支持 男/女 或 male/female")
    location: str | Coordinates | None = Field(
        default=None,
        description="出生地，支持城市名字符串或经纬度对象",
    )
    daylight_saving: bool | None = Field(
        default=None,
        description="是否显式指定夏令时。固定 UTC 偏移输入时会用于修正偏移量。",
    )
    analysis_depth: AnalysisDepth | str = Field(
        default="详细",
        description="输出深度：基础/详细/专业",
    )
    flow_years: int | None = Field(
        default=None,
        ge=1,
        le=20,
        description="流年输出年数，默认随分析深度决定",
    )

    @model_validator(mode="after")
    def validate_birth_source(self) -> "BaziChartRequest":
        split_fields = [self.year, self.month, self.day, self.hour]
        has_split = any(value is not None for value in split_fields)
        has_full_split = all(value is not None for value in split_fields)

        if self.birth_datetime is None and not has_full_split:
            raise ValueError("必须提供 birth_datetime，或提供完整的 year/month/day/hour 字段。")

        if self.birth_datetime is not None and has_split:
            raise ValueError(
                "birth_datetime 与 year/month/day/hour 不能同时提供，请选择一种输入方式。"
            )

        return self

    @property
    def normalized_gender(self) -> GenderValue:
        mapping = {
            "男": "男",
            "male": "男",
            "m": "男",
            "女": "女",
            "female": "女",
            "f": "女",
        }
        normalized = mapping.get(self.gender.strip().lower(), mapping.get(self.gender.strip()))
        if normalized not in ("男", "女"):
            raise ValueError("gender 只支持 男/女 或 male/female。")
        return normalized

    @property
    def normalized_depth(self) -> AnalysisDepth:
        mapping = {
            "basic": "基础",
            "基础": "基础",
            "detailed": "详细",
            "detail": "详细",
            "详细": "详细",
            "professional": "专业",
            "pro": "专业",
            "专业": "专业",
        }
        normalized = mapping.get(str(self.analysis_depth).strip().lower(), self.analysis_depth)
        if normalized not in ("基础", "详细", "专业"):
            raise ValueError(
                "analysis_depth 只支持 基础/详细/专业 或 basic/detailed/professional。"
            )
        return normalized  # type: ignore[return-value]

    @property
    def resolved_flow_years(self) -> int:
        if self.flow_years is not None:
            return self.flow_years
        defaults = {"基础": 3, "详细": 5, "专业": 10}
        return defaults[self.normalized_depth]


class HiddenStemInfo(BaseModel):
    stem: str
    element: str
    ten_god: str


class PillarDetail(BaseModel):
    ganzhi: str
    tiangan: str
    dizhi: str
    stem_element: str
    branch_element: str
    nayin: str
    stem_ten_god: str
    branch_ten_gods: list[str]
    hidden_stems: list[HiddenStemInfo]
    changsheng: str
    xun: str
    xunkong: str


class FourPillarsDetail(BaseModel):
    year: PillarDetail
    month: PillarDetail
    day: PillarDetail
    hour: PillarDetail


class LunarDateInfo(BaseModel):
    year: str
    month: str
    day: str
    numeric_month: int
    numeric_day: int
    is_leap_month: bool
    zodiac: str
    season: str


class SolarTermInfo(BaseModel):
    name: str
    moment: datetime


class TimingInfo(BaseModel):
    input_datetime: datetime
    local_datetime: datetime
    utc_datetime: datetime
    timezone: str
    utc_offset_minutes: int
    daylight_saving_active: bool
    daylight_saving_requested: bool | None
    solar_time_correction_minutes: float | None = None
    apparent_solar_datetime: datetime | None = None
    lunar_date: LunarDateInfo
    previous_solar_term: SolarTermInfo | None = None
    next_solar_term: SolarTermInfo | None = None
    location: Coordinates | None = None


class WuxingElementStat(BaseModel):
    element: str
    score: int
    percentage: float
    trend: Literal["旺", "平", "弱"]


class DayMasterStrength(BaseModel):
    stem: str
    element: str
    support_score: int
    opposing_score: int
    ratio: float
    de_ling: bool
    de_di: bool
    de_shi: bool
    strength: Literal["极强", "偏强", "中和", "偏弱", "极弱"]
    summary: str


class WuxingAnalysis(BaseModel):
    elements: list[WuxingElementStat]
    balance: dict[str, Any]
    day_master: DayMasterStrength
    favorable_elements: list[str]
    unfavorable_elements: list[str]
    seasonal_adjustment: list[str]
    summary: str


class GejuAnalysis(BaseModel):
    pattern: str
    category: Literal["正格", "变格", "特殊格局", "常规格局"]
    strength: str
    summary: str
    basis: list[str]


class DayunEntry(BaseModel):
    index: int
    ganzhi: str
    start_year: int
    end_year: int
    start_age: int
    end_age: int
    xun: str
    xunkong: str


class DayunSummary(BaseModel):
    direction: Literal["顺排", "逆排"]
    start_solar: datetime
    start_offset: dict[str, int]
    periods: list[DayunEntry]


class LiunianPrediction(BaseModel):
    year: int
    ganzhi: str
    active_dayun: str | None
    ten_god: str
    fortune_level: str
    fortune_score: int
    summary: str
    advice: list[str]


class ChartMetadata(BaseModel):
    engine_version: str
    algorithm: str
    response_time_ms: float
    warnings: list[str]
    degraded: bool


class BaziChartResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    request: dict[str, Any]
    timing: TimingInfo
    four_pillars: FourPillarsDetail
    geju: GejuAnalysis
    dayun: DayunSummary
    liunian: list[LiunianPrediction]
    wuxing: WuxingAnalysis
    metadata: ChartMetadata
