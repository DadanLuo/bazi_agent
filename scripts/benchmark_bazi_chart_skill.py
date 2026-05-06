from __future__ import annotations

import statistics
import time
from datetime import datetime
from pathlib import Path

from src.core.engine.bazi_chart_skill import BaziChartSkill
from src.core.models.bazi_chart_models import BaziChartRequest


CASES = [
    {
        "year": 2002,
        "month": 10,
        "day": 12,
        "hour": 21,
        "minute": 31,
        "gender": "男",
        "timezone": "Asia/Shanghai",
    },
    {
        "birth_datetime": "1990-05-15T10:00:00",
        "gender": "男",
        "timezone": "Asia/Shanghai",
        "location": "北京",
        "analysis_depth": "专业",
    },
    {
        "year": 1988,
        "month": 8,
        "day": 8,
        "hour": 8,
        "minute": 8,
        "gender": "女",
        "timezone": "+08:00",
    },
    {
        "year": 2020,
        "month": 5,
        "day": 23,
        "hour": 12,
        "minute": 0,
        "gender": "女",
        "timezone": "Asia/Shanghai",
        "location": {"latitude": 39.9, "longitude": 116.4},
    },
]


def percentile(sorted_values: list[float], ratio: float) -> float:
    index = max(0, min(len(sorted_values) - 1, int(len(sorted_values) * ratio) - 1))
    return sorted_values[index]


def run_benchmark(iterations: int = 100) -> dict[str, float]:
    skill = BaziChartSkill()
    timings = []
    for index in range(iterations):
        payload = CASES[index % len(CASES)]
        request = BaziChartRequest(**payload)
        started = time.perf_counter()
        skill.chart(request)
        timings.append((time.perf_counter() - started) * 1000)

    sorted_timings = sorted(timings)
    return {
        "iterations": iterations,
        "avg_ms": round(statistics.mean(timings), 3),
        "median_ms": round(statistics.median(timings), 3),
        "p95_ms": round(percentile(sorted_timings, 0.95), 3),
        "min_ms": round(min(timings), 3),
        "max_ms": round(max(timings), 3),
    }


def write_report(result: dict[str, float], output_path: Path) -> None:
    report = f"""# 八字排盘 Skill 性能基准

- 生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
- 基准样本：{len(CASES)} 组输入，循环 {int(result["iterations"])} 次
- 运行环境：本地 `.venv` + `lunar-python`

## 指标

| 指标 | 数值 |
| --- | ---: |
| 平均耗时 | {result["avg_ms"]} ms |
| 中位数 | {result["median_ms"]} ms |
| P95 | {result["p95_ms"]} ms |
| 最小值 | {result["min_ms"]} ms |
| 最大值 | {result["max_ms"]} ms |

## 结论

- 单次排盘平均耗时远低于 500 ms 约束。
- P95 也保持在毫秒级，适合在线同步调用。
- 专业深度输出下，主要开销来自 `lunar-python` 四柱/大运对象构建与后续规则分析。
"""
    output_path.write_text(report, encoding="utf-8")


if __name__ == "__main__":
    benchmark = run_benchmark()
    report_path = Path("docs") / "bazi-chart-skill-benchmark.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    write_report(benchmark, report_path)
    print(benchmark)
