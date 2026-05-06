from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from lunar_python import Solar

from src.core.city_coords import resolve_city_coords
from src.core.engine.geju import GejuEngine
from src.core.engine.liunian import LiunianEngine
from src.core.engine.rules import rule_loader
from src.core.engine.wuxing_calculator import WuxingCalculator
from src.core.engine.yongshen import YongshenEngine
from src.core.exceptions import ValidationError
from src.core.models.bazi_chart_models import (
    BaziChartRequest,
    BaziChartResponse,
    ChartMetadata,
    Coordinates,
    DayMasterStrength,
    DayunEntry,
    DayunSummary,
    FourPillarsDetail,
    GejuAnalysis,
    HiddenStemInfo,
    LiunianPrediction,
    LunarDateInfo,
    PillarDetail,
    SolarTermInfo,
    TimingInfo,
    WuxingAnalysis,
    WuxingElementStat,
)
from src.core.models.bazi_models import BirthInfo, DayunPillar, FourPillars, Pillar, Tiangan, Dizhi

OFFSET_PATTERN = re.compile(
    r"^(?:UTC|GMT)?(?P<sign>[+-])(?P<hour>\d{1,2})(?::?(?P<minute>\d{2}))?$", re.I
)
SUPPORTIVE_DISHI = {"长生", "沐浴", "冠带", "临官", "帝旺", "衰"}
YANG_STEMS = {"甲", "丙", "戊", "庚", "壬"}


@dataclass
class NormalizedContext:
    request: BaziChartRequest
    input_datetime: datetime
    local_datetime: datetime
    utc_datetime: datetime
    timezone_name: str
    utc_offset_minutes: int
    daylight_saving_active: bool
    location: Coordinates | None
    warnings: list[str]
    solar_time_correction_minutes: float | None
    apparent_solar_datetime: datetime | None


class BaziChartSkill:
    ENGINE_VERSION = "2.0.0"

    def __init__(self) -> None:
        self.wuxing_calculator = WuxingCalculator()
        self.geju_engine = GejuEngine()
        self.yongshen_engine = YongshenEngine()
        self.liunian_engine = LiunianEngine()
        self.tiangan_wuxing = rule_loader.get_tiangan_wuxing()
        self.dizhi_wuxing = rule_loader.get_dizhi_wuxing()

    def chart(self, request: BaziChartRequest) -> BaziChartResponse:
        started = time.perf_counter()
        context = self._normalize_request(request)
        solar = Solar.fromYmdHms(
            context.local_datetime.year,
            context.local_datetime.month,
            context.local_datetime.day,
            context.local_datetime.hour,
            context.local_datetime.minute,
            context.local_datetime.second,
        )
        lunar = solar.getLunar()
        eight_char = lunar.getEightChar()
        pillars = self._build_four_pillars(eight_char)

        pillar_details = FourPillarsDetail(
            year=self._build_pillar_detail("Year", eight_char),
            month=self._build_pillar_detail("Month", eight_char),
            day=self._build_pillar_detail("Day", eight_char),
            hour=self._build_pillar_detail("Time", eight_char),
        )

        wuxing_score = self.wuxing_calculator.calculate_total_score(pillars)
        balance = self.wuxing_calculator.analyze_wuxing_balance(wuxing_score)
        day_master = self._analyze_day_master(pillars, eight_char)
        geju_raw = self.geju_engine.determine_geju(
            pillars,
            {
                "strength": self._legacy_strength(day_master.strength),
                "score": int(day_master.ratio * 100),
                "description": day_master.summary,
            },
        )
        yongshen_raw = self.yongshen_engine.determine_yongshen(
            pillars,
            {"strength": self._legacy_strength(day_master.strength)},
            geju_raw,
        )
        geju = self._build_geju_analysis(geju_raw, day_master, yongshen_raw)
        wuxing = self._build_wuxing_analysis(wuxing_score, balance, day_master, yongshen_raw)
        dayun = self._build_dayun_summary(eight_char, context.request.normalized_gender)
        liunian = self._build_liunian_predictions(
            pillars=pillars,
            yongshen=yongshen_raw,
            dayun=dayun,
            timezone_name=context.timezone_name,
            years=context.request.resolved_flow_years,
        )
        timing = self._build_timing_info(context, lunar)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)

        return BaziChartResponse(
            request=self._build_request_echo(context.request),
            timing=timing,
            four_pillars=pillar_details,
            geju=geju,
            dayun=dayun,
            liunian=liunian,
            wuxing=wuxing,
            metadata=ChartMetadata(
                engine_version=self.ENGINE_VERSION,
                algorithm="ZoneInfo + lunar-python(EightChar/Yun) + local rules",
                response_time_ms=elapsed_ms,
                warnings=context.warnings,
                degraded=False,
            ),
        )

    def chart_from_dict(self, payload: dict[str, Any]) -> BaziChartResponse:
        return self.chart(BaziChartRequest(**payload))

    def chart_from_birth_info(
        self, birth_info: BirthInfo, analysis_depth: str = "详细"
    ) -> BaziChartResponse:
        payload: dict[str, Any] = {
            "year": birth_info.year,
            "month": birth_info.month,
            "day": birth_info.day,
            "hour": birth_info.hour,
            "minute": birth_info.minute,
            "timezone": birth_info.timezone,
            "gender": birth_info.gender,
            "analysis_depth": analysis_depth,
        }
        if birth_info.latitude is not None and birth_info.longitude is not None:
            payload["location"] = {
                "latitude": birth_info.latitude,
                "longitude": birth_info.longitude,
            }
        return self.chart_from_dict(payload)

    def to_legacy_result(
        self, birth_info: BirthInfo
    ) -> tuple[BaziChartResponse, list[DayunPillar]]:
        chart = self.chart_from_birth_info(birth_info)
        periods = [
            DayunPillar(
                start_age=entry.start_age,
                pillar=Pillar(
                    tiangan=Tiangan(entry.ganzhi[0]),
                    dizhi=Dizhi(entry.ganzhi[1]),
                ),
            )
            for entry in chart.dayun.periods
        ]
        return chart, periods

    def _normalize_request(self, request: BaziChartRequest) -> NormalizedContext:
        warnings: list[str] = []
        tzinfo, timezone_name, fixed_offset = self._parse_timezone(
            request.timezone, request.daylight_saving
        )

        if request.birth_datetime is not None:
            input_datetime = request.birth_datetime
            if input_datetime.tzinfo is None:
                local_datetime = input_datetime.replace(tzinfo=tzinfo)
            else:
                local_datetime = input_datetime.astimezone(tzinfo)
        else:
            try:
                input_datetime = datetime(
                    request.year or 1900,
                    request.month or 1,
                    request.day or 1,
                    request.hour or 0,
                    request.minute,
                )
            except ValueError as exc:
                raise ValidationError(f"出生时间无效：{exc}") from exc
            local_datetime = input_datetime.replace(tzinfo=tzinfo)

        actual_dst = bool(local_datetime.dst() and local_datetime.dst().total_seconds())
        if (
            fixed_offset is None
            and request.daylight_saving is not None
            and request.daylight_saving != actual_dst
        ):
            warnings.append(
                "daylight_saving 与该时区的历史规则不一致，系统已优先使用时区数据库中的实际结果。"
            )

        utc_datetime = local_datetime.astimezone(timezone.utc)
        utc_offset_minutes = int(local_datetime.utcoffset().total_seconds() // 60)
        location = self._resolve_location(request.location)
        solar_correction = None
        apparent_solar = None
        if location is not None:
            solar_correction = round(
                self._calculate_solar_time_correction_minutes(local_datetime, location.longitude),
                3,
            )
            apparent_solar = local_datetime + timedelta(minutes=solar_correction)

        return NormalizedContext(
            request=request,
            input_datetime=input_datetime,
            local_datetime=local_datetime,
            utc_datetime=utc_datetime,
            timezone_name=timezone_name,
            utc_offset_minutes=utc_offset_minutes,
            daylight_saving_active=actual_dst,
            location=location,
            warnings=warnings,
            solar_time_correction_minutes=solar_correction,
            apparent_solar_datetime=apparent_solar,
        )

    def _parse_timezone(
        self,
        value: str,
        daylight_saving: bool | None,
    ) -> tuple[timezone | ZoneInfo, str, timedelta | None]:
        if not value:
            raise ValidationError("timezone 不能为空。")

        try:
            zone = ZoneInfo(value)
            return zone, value, None
        except ZoneInfoNotFoundError:
            pass

        matched = OFFSET_PATTERN.match(value.strip())
        if not matched:
            raise ValidationError(
                "timezone 必须是合法 IANA 时区 ID，或 UTC 偏移量，例如 Asia/Shanghai、+08:00。"
            )

        sign = 1 if matched.group("sign") == "+" else -1
        hours = int(matched.group("hour"))
        minutes = int(matched.group("minute") or 0)
        offset = timedelta(hours=hours, minutes=minutes) * sign
        if daylight_saving:
            offset += timedelta(hours=1)
        name = f"UTC{matched.group('sign')}{hours:02d}:{minutes:02d}"
        return timezone(offset, name=name), name, offset

    def _resolve_location(self, value: str | Coordinates | None) -> Coordinates | None:
        if value is None:
            return None
        if isinstance(value, Coordinates):
            return value
        if isinstance(value, dict):
            return Coordinates(**value)

        coords = resolve_city_coords(value)
        if coords is None:
            raise ValidationError(
                f"无法解析城市“{value}”，请改用 {{latitude, longitude}} 坐标对象。"
            )
        longitude, latitude = coords
        return Coordinates(latitude=latitude, longitude=longitude)

    def _calculate_solar_time_correction_minutes(
        self, local_datetime: datetime, longitude: float
    ) -> float:
        standard_meridian = local_datetime.utcoffset().total_seconds() / 3600 * 15
        day_of_year = local_datetime.timetuple().tm_yday
        b = 2 * math.pi * (day_of_year - 81) / 364
        equation_of_time = 9.87 * math.sin(2 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)
        longitude_correction = 4 * (longitude - standard_meridian)
        return longitude_correction + equation_of_time

    def _build_four_pillars(self, eight_char) -> FourPillars:
        return FourPillars(
            year=self._pillar_from_ganzhi(eight_char.getYear()),
            month=self._pillar_from_ganzhi(eight_char.getMonth()),
            day=self._pillar_from_ganzhi(eight_char.getDay()),
            hour=self._pillar_from_ganzhi(eight_char.getTime()),
        )

    def _pillar_from_ganzhi(self, ganzhi: str) -> Pillar:
        return Pillar(
            tiangan=Tiangan(ganzhi[0]),
            dizhi=Dizhi(ganzhi[1]),
        )

    def _build_pillar_detail(self, prefix: str, eight_char) -> PillarDetail:
        ganzhi = getattr(eight_char, f"get{prefix}")()
        tiangan = getattr(eight_char, f"get{prefix}Gan")()
        dizhi = getattr(eight_char, f"get{prefix}Zhi")()
        hidden_stems = getattr(eight_char, f"get{prefix}HideGan")()
        branch_ten_gods = list(getattr(eight_char, f"get{prefix}ShiShenZhi")())

        hidden_items = [
            HiddenStemInfo(
                stem=stem,
                element=self.tiangan_wuxing.get(stem, "土"),
                ten_god=branch_ten_gods[index] if index < len(branch_ten_gods) else "未知",
            )
            for index, stem in enumerate(hidden_stems)
        ]

        return PillarDetail(
            ganzhi=ganzhi,
            tiangan=tiangan,
            dizhi=dizhi,
            stem_element=self.tiangan_wuxing.get(tiangan, "土"),
            branch_element=self.dizhi_wuxing.get(dizhi, "土"),
            nayin=getattr(eight_char, f"get{prefix}NaYin")(),
            stem_ten_god=getattr(eight_char, f"get{prefix}ShiShenGan")(),
            branch_ten_gods=branch_ten_gods,
            hidden_stems=hidden_items,
            changsheng=getattr(eight_char, f"get{prefix}DiShi")(),
            xun=getattr(eight_char, f"get{prefix}Xun")(),
            xunkong=getattr(eight_char, f"get{prefix}XunKong")(),
        )

    def _analyze_day_master(self, pillars: FourPillars, eight_char) -> DayMasterStrength:
        day_stem = pillars.day.tiangan.value
        day_element = self.tiangan_wuxing.get(day_stem, "土")
        supporting_elements = {
            day_element,
            self._element_that_generates(day_element),
        }
        opposing_elements = {
            self._element_generated_by(day_element),
            self._element_that_controls(day_element),
            self._element_controlled_by(day_element),
        }

        support_score = 0.0
        opposing_score = 0.0
        visible_weights = {"year": 1.0, "month": 1.6, "day": 1.2, "hour": 1.0}
        hidden_weights = {"year": 0.7, "month": 1.3, "day": 1.0, "hour": 0.7}

        for position, pillar in [
            ("year", pillars.year),
            ("month", pillars.month),
            ("day", pillars.day),
            ("hour", pillars.hour),
        ]:
            stem_element = self.tiangan_wuxing.get(pillar.tiangan.value, "土")
            stem_score = 40 * visible_weights[position]
            if stem_element in supporting_elements:
                support_score += stem_score
            elif stem_element in opposing_elements:
                opposing_score += stem_score

            for hidden in rule_loader.get_canggan(pillar.dizhi.value):
                hidden_element = self.tiangan_wuxing.get(hidden["tiangan"], "土")
                branch_score = hidden["weight"] * hidden_weights[position]
                if hidden_element in supporting_elements:
                    support_score += branch_score
                elif hidden_element in opposing_elements:
                    opposing_score += branch_score

        month_hidden = rule_loader.get_canggan(pillars.month.dizhi.value)
        de_ling = any(
            self.tiangan_wuxing.get(item["tiangan"], "土") in supporting_elements
            and item["weight"] >= 25
            for item in month_hidden
        )
        day_hidden = rule_loader.get_canggan(pillars.day.dizhi.value)
        de_di = any(
            self.tiangan_wuxing.get(item["tiangan"], "土") in supporting_elements
            and item["weight"] >= 20
            for item in day_hidden
        )
        de_shi = (
            sum(
                1
                for pillar in (pillars.year, pillars.month, pillars.hour)
                if self.tiangan_wuxing.get(pillar.tiangan.value, "土") in supporting_elements
            )
            >= 2
            or eight_char.getMonthDiShi() in SUPPORTIVE_DISHI
        )

        total = max(support_score + opposing_score, 1)
        ratio = support_score / total
        if ratio >= 0.72:
            strength = "极强"
        elif ratio >= 0.58:
            strength = "偏强"
        elif ratio >= 0.42:
            strength = "中和"
        elif ratio >= 0.28:
            strength = "偏弱"
        else:
            strength = "极弱"

        summary_parts = []
        if de_ling:
            summary_parts.append("得令")
        if de_di:
            summary_parts.append("得地")
        if de_shi:
            summary_parts.append("得势")
        summary = "、".join(summary_parts) if summary_parts else "失令失地失势"
        summary = f"日主{strength}，{summary}，扶助分 {int(support_score)}，克泄耗分 {int(opposing_score)}。"

        return DayMasterStrength(
            stem=day_stem,
            element=day_element,
            support_score=int(support_score),
            opposing_score=int(opposing_score),
            ratio=round(ratio, 4),
            de_ling=de_ling,
            de_di=de_di,
            de_shi=de_shi,
            strength=strength,  # type: ignore[arg-type]
            summary=summary,
        )

    def _build_geju_analysis(
        self,
        geju_raw: dict[str, Any],
        day_master: DayMasterStrength,
        yongshen_raw: dict[str, Any],
    ) -> GejuAnalysis:
        pattern = geju_raw.get("geju_type", "常格")
        if "格" not in pattern or pattern == "常格":
            category = "常规格局"
        elif pattern in {
            "正官格",
            "七杀格",
            "正印格",
            "偏印格",
            "正财格",
            "偏财格",
            "食神格",
            "伤官格",
        }:
            category = "正格"
        elif pattern.startswith("从"):
            category = "变格"
        else:
            category = "特殊格局"

        basis = [day_master.summary]
        if geju_raw.get("month_shishen"):
            basis.append(f"月令本气十神：{geju_raw['month_shishen']}")
        if geju_raw.get("month_tg_shishen"):
            basis.append(f"月干十神：{geju_raw['month_tg_shishen']}")
        if yongshen_raw.get("reason"):
            basis.append(f"喜用神依据：{yongshen_raw['reason']}")

        summary = geju_raw.get("description") or f"命局以 {pattern} 入格。"
        return GejuAnalysis(
            pattern=pattern,
            category=category,  # type: ignore[arg-type]
            strength=geju_raw.get("strength", "中等"),
            summary=summary,
            basis=basis,
        )

    def _build_wuxing_analysis(
        self,
        wuxing_score,
        balance: dict[str, Any],
        day_master: DayMasterStrength,
        yongshen_raw: dict[str, Any],
    ) -> WuxingAnalysis:
        score_map = {
            "木": wuxing_score.mu,
            "火": wuxing_score.huo,
            "土": wuxing_score.tu,
            "金": wuxing_score.jin,
            "水": wuxing_score.shui,
        }
        total = max(wuxing_score.total(), 1)
        elements = [
            WuxingElementStat(
                element=element,
                score=score,
                percentage=round(score / total * 100, 2),
                trend=self._classify_wuxing_trend(balance, element),
            )
            for element, score in score_map.items()
        ]
        summary = (
            f"日主为{day_master.stem}{day_master.element}，整体{day_master.strength}。"
            f" 喜用神偏向 {','.join(yongshen_raw.get('yongshen', [])) or '暂无'}，"
            f" 忌神偏向 {','.join(yongshen_raw.get('jishen', [])) or '暂无'}。"
        )
        return WuxingAnalysis(
            elements=elements,
            balance=balance,
            day_master=day_master,
            favorable_elements=list(yongshen_raw.get("yongshen", [])),
            unfavorable_elements=list(yongshen_raw.get("jishen", [])),
            seasonal_adjustment=list(yongshen_raw.get("tiaohou", [])),
            summary=summary,
        )

    def _classify_wuxing_trend(self, balance: dict[str, Any], element: str) -> str:
        if element in balance.get("strong", []):
            return "旺"
        if element in balance.get("weak", []):
            return "弱"
        return "平"

    def _build_dayun_summary(self, eight_char, gender: str) -> DayunSummary:
        yun = eight_char.getYun(1 if gender == "男" else 0)
        start_solar = datetime.strptime(yun.getStartSolar().toYmdHms(), "%Y-%m-%d %H:%M:%S")
        periods = []
        for item in yun.getDaYun():
            ganzhi = item.getGanZhi()
            if not ganzhi:
                continue
            periods.append(
                DayunEntry(
                    index=item.getIndex(),
                    ganzhi=ganzhi,
                    start_year=item.getStartYear(),
                    end_year=item.getEndYear(),
                    start_age=item.getStartAge(),
                    end_age=item.getEndAge(),
                    xun=item.getXun(),
                    xunkong=item.getXunKong(),
                )
            )

        year_stem = eight_char.getYearGan()
        is_forward = (gender == "男" and year_stem in YANG_STEMS) or (
            gender == "女" and year_stem not in YANG_STEMS
        )
        return DayunSummary(
            direction="顺排" if is_forward else "逆排",
            start_solar=start_solar,
            start_offset={
                "years": yun.getStartYear(),
                "months": yun.getStartMonth(),
                "days": yun.getStartDay(),
                "hours": yun.getStartHour(),
            },
            periods=periods,
        )

    def _build_liunian_predictions(
        self,
        pillars: FourPillars,
        yongshen: dict[str, Any],
        dayun: DayunSummary,
        timezone_name: str,
        years: int,
    ) -> list[LiunianPrediction]:
        current_year = datetime.now(
            ZoneInfo(timezone_name) if "/" in timezone_name else timezone.utc
        ).year
        predictions = []
        for year in range(current_year, current_year + years):
            analyzed = self.liunian_engine.analyze_liunian(pillars, yongshen, year)
            active_dayun = next(
                (
                    period.ganzhi
                    for period in dayun.periods
                    if period.start_year <= year <= period.end_year
                ),
                None,
            )
            predictions.append(
                LiunianPrediction(
                    year=year,
                    ganzhi=analyzed["ganzhi"],
                    active_dayun=active_dayun,
                    ten_god=analyzed["shishen"],
                    fortune_level=analyzed["jixiong"]["level"],
                    fortune_score=analyzed["jixiong"]["score"],
                    summary=analyzed["analysis"],
                    advice=list(analyzed.get("advice", [])),
                )
            )
        return predictions

    def _build_timing_info(self, context: NormalizedContext, lunar) -> TimingInfo:
        previous_term, next_term = self._find_neighbor_solar_terms(
            lunar, context.local_datetime.replace(tzinfo=None)
        )
        numeric_month = lunar.getMonth()
        return TimingInfo(
            input_datetime=context.input_datetime,
            local_datetime=context.local_datetime,
            utc_datetime=context.utc_datetime,
            timezone=context.timezone_name,
            utc_offset_minutes=context.utc_offset_minutes,
            daylight_saving_active=context.daylight_saving_active,
            daylight_saving_requested=context.request.daylight_saving,
            solar_time_correction_minutes=context.solar_time_correction_minutes,
            apparent_solar_datetime=context.apparent_solar_datetime,
            lunar_date=LunarDateInfo(
                year=lunar.getYearInChinese(),
                month=lunar.getMonthInChinese(),
                day=lunar.getDayInChinese(),
                numeric_month=abs(numeric_month),
                numeric_day=lunar.getDay(),
                is_leap_month=numeric_month < 0,
                zodiac=lunar.getYearShengXiao(),
                season=lunar.getSeason(),
            ),
            previous_solar_term=previous_term,
            next_solar_term=next_term,
            location=context.location,
        )

    def _find_neighbor_solar_terms(
        self, lunar, local_naive: datetime
    ) -> tuple[SolarTermInfo | None, SolarTermInfo | None]:
        term_items: list[tuple[str, datetime]] = []
        for name, solar in lunar.getJieQiTable().items():
            if not self._looks_like_solar_term(name):
                continue
            term_dt = datetime.strptime(solar.toYmdHms(), "%Y-%m-%d %H:%M:%S")
            term_items.append((name, term_dt))

        term_items.sort(key=lambda item: item[1])
        previous = None
        next_item = None
        for name, term_dt in term_items:
            if term_dt <= local_naive:
                previous = SolarTermInfo(name=name, moment=term_dt)
            elif next_item is None:
                next_item = SolarTermInfo(name=name, moment=term_dt)
                break
        return previous, next_item

    def _looks_like_solar_term(self, name: str) -> bool:
        return bool(re.search(r"[\u4e00-\u9fff]", name))

    def _build_request_echo(self, request: BaziChartRequest) -> dict[str, Any]:
        payload = request.model_dump(exclude_none=True)
        payload["gender"] = request.normalized_gender
        payload["analysis_depth"] = request.normalized_depth
        payload["flow_years"] = request.resolved_flow_years
        return payload

    def _legacy_strength(self, value: str) -> str:
        mapping = {
            "极强": "very_strong",
            "偏强": "strong",
            "中和": "medium",
            "偏弱": "weak",
            "极弱": "very_weak",
        }
        return mapping.get(value, "medium")

    def _element_that_generates(self, element: str) -> str:
        return {"木": "水", "火": "木", "土": "火", "金": "土", "水": "金"}[element]

    def _element_generated_by(self, element: str) -> str:
        return {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}[element]

    def _element_that_controls(self, element: str) -> str:
        return {"木": "金", "火": "水", "土": "木", "金": "火", "水": "土"}[element]

    def _element_controlled_by(self, element: str) -> str:
        return {"木": "土", "火": "金", "土": "水", "金": "木", "水": "火"}[element]
