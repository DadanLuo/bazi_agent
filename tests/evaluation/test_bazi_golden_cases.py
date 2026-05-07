import json
from pathlib import Path

import pytest

from src.core.engine.bazi_chart_skill import BaziChartSkill
from src.core.models.bazi_chart_models import BaziChartRequest


CASES_PATH = Path(__file__).with_name("bazi_golden_cases.json")


def load_cases():
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))


def assert_expected_subset(result, expected):
    dumped = result.model_dump(mode="json")

    for pillar_name, ganzhi in expected.get("four_pillars", {}).items():
        assert dumped["four_pillars"][pillar_name]["ganzhi"] == ganzhi

    for key, value in expected.get("request", {}).items():
        assert dumped["request"][key] == value

    timing_values = expected.get("timing", {})
    if "timezone" in timing_values:
        assert dumped["timing"]["timezone"] == timing_values["timezone"]
    if "lunar_is_leap_month" in timing_values:
        assert (
            dumped["timing"]["lunar_date"]["is_leap_month"]
            is timing_values["lunar_is_leap_month"]
        )
    if "location_longitude" in timing_values:
        assert dumped["timing"]["location"]["longitude"] == timing_values["location_longitude"]

    if "liunian_count" in expected:
        assert len(dumped["liunian"]) == expected["liunian_count"]

    for key, value in expected.get("metadata", {}).items():
        assert dumped["metadata"][key] == value


@pytest.mark.parametrize("case", load_cases(), ids=lambda case: case["id"])
def test_bazi_chart_matches_golden_case(case):
    skill = BaziChartSkill()
    result = skill.chart(BaziChartRequest(**case["request"]))

    assert_expected_subset(result, case["expected"])
