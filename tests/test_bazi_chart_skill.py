from src.core.engine.bazi_chart_skill import BaziChartSkill
from src.core.models.bazi_chart_models import BaziChartRequest


def test_chart_skill_uses_exact_solar_term_boundaries():
    skill = BaziChartSkill()
    result = skill.chart(
        BaziChartRequest(
            year=2002,
            month=10,
            day=12,
            hour=21,
            minute=31,
            gender="男",
            timezone="Asia/Shanghai",
        )
    )

    assert result.four_pillars.year.ganzhi == "壬午"
    assert result.four_pillars.month.ganzhi == "庚戌"
    assert result.four_pillars.day.ganzhi == "癸丑"
    assert result.four_pillars.hour.ganzhi == "癸亥"


def test_chart_skill_supports_datetime_input_and_fixed_offset():
    skill = BaziChartSkill()
    result = skill.chart(
        BaziChartRequest(
            birth_datetime="2002-10-12T21:31:00",
            gender="male",
            timezone="+08:00",
            analysis_depth="basic",
        )
    )

    assert result.request["gender"] == "男"
    assert result.request["analysis_depth"] == "基础"
    assert result.timing.timezone == "UTC+08:00"
    assert result.four_pillars.month.ganzhi == "庚戌"


def test_chart_skill_records_leap_month_metadata_and_location():
    skill = BaziChartSkill()
    result = skill.chart(
        BaziChartRequest(
            year=2020,
            month=5,
            day=23,
            hour=12,
            minute=0,
            gender="女",
            timezone="Asia/Shanghai",
            location="北京",
            analysis_depth="专业",
        )
    )

    assert result.timing.lunar_date.is_leap_month is True
    assert result.timing.location is not None
    assert result.timing.location.longitude == 116.4
    assert result.timing.solar_time_correction_minutes is not None
    assert len(result.liunian) == 10


def test_chart_skill_includes_dayun_and_current_liunian():
    skill = BaziChartSkill()
    result = skill.chart(
        BaziChartRequest(
            year=1990,
            month=5,
            day=15,
            hour=10,
            minute=0,
            gender="男",
            timezone="Asia/Shanghai",
        )
    )

    assert result.dayun.direction in {"顺排", "逆排"}
    assert len(result.dayun.periods) >= 8
    assert result.dayun.periods[0].ganzhi
    assert result.liunian[0].ganzhi
    assert result.wuxing.favorable_elements
