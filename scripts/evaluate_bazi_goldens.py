from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.engine.bazi_chart_skill import BaziChartSkill
from src.core.models.bazi_chart_models import BaziChartRequest

CASES_PATH = ROOT / "tests" / "evaluation" / "bazi_golden_cases.json"


def compare_case(skill: BaziChartSkill, case: dict[str, Any]) -> list[str]:
    result = skill.chart(BaziChartRequest(**case["request"])).model_dump(mode="json")
    expected = case["expected"]
    mismatches: list[str] = []

    for pillar_name, ganzhi in expected.get("four_pillars", {}).items():
        actual = result["four_pillars"][pillar_name]["ganzhi"]
        if actual != ganzhi:
            mismatches.append(f"four_pillars.{pillar_name}: expected {ganzhi}, got {actual}")

    for key, value in expected.get("request", {}).items():
        actual = result["request"][key]
        if actual != value:
            mismatches.append(f"request.{key}: expected {value}, got {actual}")

    timing = expected.get("timing", {})
    if "timezone" in timing and result["timing"]["timezone"] != timing["timezone"]:
        mismatches.append(
            f"timing.timezone: expected {timing['timezone']}, got {result['timing']['timezone']}"
        )
    if (
        "lunar_is_leap_month" in timing
        and result["timing"]["lunar_date"]["is_leap_month"] is not timing["lunar_is_leap_month"]
    ):
        mismatches.append("timing.lunar_date.is_leap_month mismatch")
    if (
        "location_longitude" in timing
        and result["timing"]["location"]["longitude"] != timing["location_longitude"]
    ):
        mismatches.append(
            "timing.location.longitude: "
            f"expected {timing['location_longitude']}, got "
            f"{result['timing']['location']['longitude']}"
        )

    if "liunian_count" in expected and len(result["liunian"]) != expected["liunian_count"]:
        mismatches.append(
            f"liunian_count: expected {expected['liunian_count']}, got {len(result['liunian'])}"
        )

    for key, value in expected.get("metadata", {}).items():
        actual = result["metadata"][key]
        if actual != value:
            mismatches.append(f"metadata.{key}: expected {value}, got {actual}")

    return mismatches


def main() -> int:
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    skill = BaziChartSkill()
    failures: dict[str, list[str]] = {}

    for case in cases:
        mismatches = compare_case(skill, case)
        if mismatches:
            failures[case["id"]] = mismatches

    summary = {
        "case_count": len(cases),
        "passed": len(cases) - len(failures),
        "failed": len(failures),
        "failures": failures,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
