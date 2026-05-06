from src.core.engine.bazi_calculator import BaziCalculator
from src.core.models.bazi_models import BirthInfo


def _pillar_text(pillar) -> str:
    return f"{pillar.tiangan.value}{pillar.dizhi.value}"


def test_bazi_uses_solar_term_month_boundary():
    calculator = BaziCalculator()
    birth_info = BirthInfo(
        year=2002,
        month=10,
        day=12,
        hour=21,
        minute=31,
        gender="男",
        timezone="Asia/Shanghai",
        latitude=39.9,
        longitude=116.4,
    )

    result = calculator.calculate(birth_info)

    assert _pillar_text(result.four_pillars.year) == "壬午"
    assert _pillar_text(result.four_pillars.month) == "庚戌"
    assert _pillar_text(result.four_pillars.day) == "癸丑"
    assert _pillar_text(result.four_pillars.hour) == "癸亥"


def test_bazi_uses_lichun_for_year_boundary():
    calculator = BaziCalculator()

    before_lichun = BirthInfo(
        year=2002,
        month=2,
        day=3,
        hour=23,
        minute=0,
        gender="男",
        timezone="Asia/Shanghai",
    )
    after_lichun = BirthInfo(
        year=2002,
        month=2,
        day=4,
        hour=20,
        minute=0,
        gender="男",
        timezone="Asia/Shanghai",
    )

    before_result = calculator.calculate(before_lichun)
    after_result = calculator.calculate(after_lichun)

    assert _pillar_text(before_result.four_pillars.year) == "辛巳"
    assert _pillar_text(before_result.four_pillars.month) == "辛丑"
    assert _pillar_text(after_result.four_pillars.year) == "壬午"
    assert _pillar_text(after_result.four_pillars.month) == "壬寅"
