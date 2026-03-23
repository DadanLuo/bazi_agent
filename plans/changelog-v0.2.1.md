# 本次修改内容总结

## 一、塔罗 Agent API 路由接入

### 改动文件：`src/api/chat_api.py`

**新增 import**
- `AgentRegistry`（Agent 注册表）
- `UnifiedSession`、`SessionMetadata`、`TarotCacheData`（数据契约）

**新增函数**

| 函数 | 作用 |
|------|------|
| `_build_temp_unified_session()` | 从旧体系 SessionData 构造临时 UnifiedSession，供 TarotAgent 使用 |
| `_extract_tarot_slots()` | 从用户 query 中提取塔罗 slots（question_type / spread_type / specific_question） |
| `_handle_tarot_analysis()` | 调用 TarotAgent.handle_analysis()，将 graph_result 回写 state_manager |
| `_handle_tarot_followup()` | 从 state 恢复 tarot_cache，调用 TarotAgent.handle_followup() |

**修改逻辑**

- `handle_chat()` 路径B：意图识别后增加塔罗路由检测（`agent_type` 显式指定 > 关键词自动检测），响应体增加 `tarot_output`
- `handle_followup()`：检测 `tarot_cache` 存在时优先走塔罗追问
- 八字流程完全未动

---

## 二、企业级中间件

### 新增文件

| 文件 | 说明 |
|------|------|
| `src/config/middleware_config.py` | 中间件配置中心，支持环境变量覆盖 |
| `src/middleware/rate_limit.py` | 滑动窗口限流（Redis INCR+EXPIRE，降级内存计数器） |
| `src/middleware/timeout.py` | 请求超时兜底（普通 30s，LLM 120s） |
| `src/middleware/logging_middleware.py` | JSON 结构化日志 + 慢请求标记 |
| `src/api/health.py` | `/health` 存活探针 + `/ready` 就绪探针 |

### 修改文件

| 文件 | 改动 |
|------|------|
| `src/core/exceptions.py` | 新增 `RateLimitError`（429）、`RequestTimeoutError`（504） |
| `src/main.py` | 注册 4 个中间件（GZip → CORS → Timeout → RateLimit → Logging）+ 健康检查路由，删除旧 request_context_middleware |

### 中间件执行顺序（洋葱模型）

```
请求 → LoggingMiddleware（生成 trace_id，记录开始时间）
     → RateLimitMiddleware（检查限流，超限返回 429）
     → TimeoutMiddleware（设置超时，超时返回 504）
     → CORSMiddleware
     → GZipMiddleware
     → 路由处理
     ← 响应原路返回，Logging 记录耗时和状态码
```

---

## 三、前端联调

### 改动文件：`static/index.html`

**CSS 新增**
- Tab 切换栏样式（`.tab-bar`、`.tab`、`.tab.active`）
- 塔罗牌卡片样式（`.tarot-card`、正/逆位颜色区分、关键词标签）
- 429 倒计时样式（`.error-countdown`）

**HTML 结构改动**
- 左栏：`<h2>输入信息</h2>` → Tab 栏（八字分析 | 塔罗占卜），八字表单包入 `panelBazi`，新增 `panelTarot`（问题输入 + 牌阵选择 + 开始占卜按钮）
- 中栏：`resultArea` 之后新增 `tarotResultArea`（牌阵名称 + 牌卡容器 + AI 解读报告）
- 右栏：chat 提示文字加 id，支持动态切换

**JS 改动**

| 新增函数 | 作用 |
|----------|------|
| `switchTab(tab)` | 切换 Tab，toggle 面板和结果区可见性 |
| `analyzeTarot()` | 发送 agent_type="tarot" 请求，渲染结果 |
| `renderTarotResult()` | 渲染牌阵名称 + 牌卡 + 解读报告 |
| `showTarotLoading()` / `hideTarotLoading()` | 塔罗加载动画 |
| `handleHttpError()` | 统一处理 429/504 错误 |
| `startRetryCountdown()` | 429 倒计时显示 |

| 修改函数 | 改动 |
|----------|------|
| `analyzeBazi()` | fetch 错误分支改为调用 `handleHttpError()` |
| `sendChat()` | 守卫条件增加 `lastTarotResult`；错误分支增加 429/504 友好提示 |
| `showLoading()` / `hideLoading()` | 增加 `btnTarot` disabled 控制 |

---

## 四、文件变更清单

```
新增 (7):
  src/config/middleware_config.py
  src/middleware/rate_limit.py
  src/middleware/timeout.py
  src/middleware/logging_middleware.py
  src/api/health.py
  plans/p0-enterprise-middleware.md
  plans/changelog-v0.2.1.md          ← 本文件

修改 (4):
  src/api/chat_api.py                ← 塔罗路由接入
  src/core/exceptions.py             ← +RateLimitError, +RequestTimeoutError
  src/main.py                        ← 中间件注册 + 健康检查
  static/index.html                  ← 塔罗 UI + 错误友好提示
```
