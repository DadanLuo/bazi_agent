# 八字排盘 Skill 核心算法设计

## 1. 设计目标

- 将排盘与分析能力收敛为单一可复用组件 `BaziChartSkill`
- 保持旧 `BaziCalculator` 兼容
- 对外提供统一结构化返回，而不是散落在多个 LangGraph 节点中的中间字典

## 2. 模块结构

- `src/core/models/bazi_chart_models.py`
  - 请求/响应模型
- `src/core/engine/bazi_chart_skill.py`
  - 输入归一化
  - 四柱排盘
  - 五行/格局/喜用神
  - 大运/流年
  - 节气与时序诊断
- `src/api/bazi_chart_api.py`
  - 标准 HTTP 入口

## 3. 时间与时区策略

1. 优先使用 `ZoneInfo` 解析 IANA 时区 ID，保留历史时区变更。
2. 若输入是固定 UTC 偏移，则回退为固定 `timezone(offset)`。
3. `daylight_saving` 仅在固定 UTC 偏移模式下直接修正偏移量；对于 IANA 时区，系统以时区数据库实际值为准。
4. 额外输出：
   - `utc_datetime`
   - `utc_offset_minutes`
   - `daylight_saving_active`
   - `apparent_solar_datetime`

## 4. 四柱与节气策略

- 四柱、大运、纳音、十神优先使用 `lunar-python` 的 `EightChar` / `Yun` 能力。
- 年柱使用 `getYearInGanZhiExact()` 语义，对立春边界敏感。
- 月柱使用 `getMonthInGanZhiExact()` 语义，对节气边界敏感。
- 闰月不直接决定月柱，但会通过 `lunar.getMonth() < 0` 记录为 `is_leap_month=true`。

## 5. 五行与日主强弱

五行分数仍复用现有 `WuxingCalculator`，保证与项目既有规则一致。

日主强弱新增一层独立评分：

- 显性天干按位置赋权
- 地支按藏干权重与位置赋权
- 月令与日支单独评估 `得令 / 得地`
- 年、月、时干对日主的助抑判断作为 `得势`
- 最终用扶助分与克泄耗分比值映射：
  - `极强`
  - `偏强`
  - `中和`
  - `偏弱`
  - `极弱`

## 6. 格局与喜用神

- 格局判断复用 `GejuEngine`
- 喜用神推导复用 `YongshenEngine`
- Skill 层额外做结构化包装：
  - `pattern`
  - `category`
  - `basis`
  - `summary`

## 7. 大运与流年

- 大运使用 `eight_char.getYun(gender)` 和 `getDaYun()`
- 顺逆排根据性别与年干阴阳补充显示
- 流年使用既有 `LiunianEngine`，并补齐“当前处于哪一步大运”

## 8. 异常与降级

- 输入不合法：抛 `ValidationError`
- 城市无法解析：明确提示改用经纬度
- `lunar-python` 不可用时，旧 `BaziCalculator` 仍保留原有兜底逻辑

## 9. 性能

- 结构化排盘为同步内存计算
- 无外部网络依赖
- 本地基准平均耗时显著低于 500 ms
