# 八字排盘 Skill 接口规范

## 1. Python 服务接口

```python
from src.core.engine.bazi_chart_skill import BaziChartSkill
from src.core.models.bazi_chart_models import BaziChartRequest

skill = BaziChartSkill()
result = skill.chart(BaziChartRequest(...))
```

### 请求模型 `BaziChartRequest`

必填字段：

- `gender`: `男/女` 或 `male/female`
- `timezone`: IANA 时区 ID 或 UTC 偏移，例如 `Asia/Shanghai`、`+08:00`
- 出生时间二选一：
  - `birth_datetime`
  - `year + month + day + hour`，`minute` 可省略

可选字段：

- `location`: 城市名字符串，或 `{ "latitude": 39.9, "longitude": 116.4 }`
- `daylight_saving`: 固定 UTC 偏移输入时是否加 1 小时 DST 修正
- `analysis_depth`: `基础/详细/专业`
- `flow_years`: 未来流年输出年数，默认随 `analysis_depth` 变化

## 2. HTTP API

### 路由

- `POST /api/v1/bazi/chart`

### 示例请求

```json
{
  "birth_datetime": "2002-10-12T21:31:00",
  "timezone": "Asia/Shanghai",
  "gender": "男",
  "location": "北京",
  "analysis_depth": "专业"
}
```

### 响应结构

```json
{
  "success": true,
  "message": "八字排盘完成",
  "data": {
    "request": {},
    "timing": {},
    "four_pillars": {},
    "geju": {},
    "dayun": {},
    "liunian": [],
    "wuxing": {},
    "metadata": {}
  }
}
```

## 3. 关键响应字段

- `timing`: 归一化后的本地时间、UTC 时间、时区偏移、DST 状态、闰月标记、节气邻接点
- `four_pillars`: 年/月/日/时四柱，每柱含干支、纳音、藏干、十神、旬空、十二长生
- `geju`: 格局名、类别、强弱、判定依据
- `dayun`: 起运时间、顺逆排、10 年大运列表
- `liunian`: 当前年份起的未来若干年预测，含当前所处大运、十神、吉凶等级和建议
- `wuxing`: 五行分数、比例、日主强弱、喜用神、忌神、调候
- `metadata`: 算法标识、耗时、告警、降级标记

## 4. 错误约定

- 非法时区：返回 `400`
- 无法解析城市：返回 `400`，并提示改用经纬度
- 出生时间字段冲突或不完整：返回 `400`
- 内部执行异常：返回 `500`

## 5. 兼容入口

旧接口仍可继续使用：

- `src.core.engine.BaziCalculator.calculate()`

新增结构化结果入口：

- `src.core.engine.BaziCalculator.calculate_chart()`
