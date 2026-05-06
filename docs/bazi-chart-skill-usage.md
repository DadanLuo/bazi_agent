# 八字排盘 Skill 使用示例与最佳实践

## 1. 基础示例

```python
from src.core.engine.bazi_chart_skill import BaziChartSkill
from src.core.models.bazi_chart_models import BaziChartRequest

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
print(result.four_pillars.day.ganzhi)
print(result.geju.pattern)
print(result.wuxing.favorable_elements)
```

## 2. 推荐输入方式

- 已知 ISO 时间字符串时，优先用 `birth_datetime`
- 已知历史出生地且可能受 DST 影响时，优先用 IANA 时区，例如 `Asia/Shanghai`
- 城市解析失败时，直接传经纬度对象，避免歧义

## 3. 输出消费建议

- 前端展示排盘时，直接读 `four_pillars`
- 专业分析页同时展示：
  - `timing`
  - `wuxing`
  - `geju`
  - `dayun`
  - `liunian`
- 若需要兼容旧逻辑，保留 `BaziCalculator.calculate()`；若要新结构，调用 `calculate_chart()`

## 4. 集成测试建议

- 节气边界：立春前后、节交接前后
- 时区边界：UTC 偏移输入与 IANA 输入一致性
- 闰月样本：验证 `timing.lunar_date.is_leap_month`
- 城市解析失败：验证错误信息可操作
- 性能回归：持续跟踪 P95 是否仍低于 500 ms

## 5. 已覆盖测试

- `tests/test_bazi_chart_skill.py`
- `tests/test_bazi_chart_api.py`
- `tests/test_bazi_calendar_accuracy.py`
