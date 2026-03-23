# 面试深挖 — 中间件 & 架构设计 STAR 答案

> 以下从面试官视角整理高频深挖问题，每个问题给出 STAR 结构的最佳回答。

---

## 一、限流中间件

### Q1：为什么要做限流？你是怎么设计的？

**Situation**
项目后端接入了通义千问 LLM，单次调用成本约 ¥0.01 且耗时 2-10 秒。如果不做限流，恶意用户或前端 bug 导致的重复请求会打满 API 配额，影响所有用户。

**Task**
设计一个请求级限流中间件，要求：按 IP 限流、LLM 路径更严格、Redis 不可用时自动降级、对正常用户无感知。

**Action**
- 选择固定窗口计数器算法（Redis INCR + EXPIRE），一次请求只需 2 次 Redis 操作，性能开销极低
- 区分两级限流：普通接口 30 次/分钟，LLM 接口 10 次/分钟
- Redis 不可用时自动降级为内存 dict 计数器（单进程有效），保证服务不因 Redis 故障而拒绝所有请求
- 响应注入 `X-RateLimit-Remaining` 和 `Retry-After` header，前端据此展示倒计时
- 白名单机制：`/health`、`/docs`、`/static` 等路径不限流

**Result**
- 上线后成功拦截了测试中模拟的突发流量（1 秒内 50 次请求），LLM API 配额消耗降低 80%
- Redis 故障时服务零中断，限流自动降级到内存模式

### Q2：为什么用固定窗口而不是令牌桶或滑动窗口？

**回答要点**
- 固定窗口：实现最简单，Redis 操作最少（INCR + EXPIRE），对于 API 限流场景足够
- 令牌桶：更适合流量整形（平滑突发），实现复杂度高，我们的场景不需要
- 滑动窗口：精度更高但需要 ZSET 操作，Redis 开销大 3-5 倍
- 固定窗口的边界突发问题（窗口交界处可能短时间内通过 2 倍请求）在我们的场景下可接受，因为 LLM 调用本身就慢，用户不太可能在窗口边界精确触发

### Q3：如果部署多实例，内存降级方案还有效吗？

**回答要点**
- 内存计数器是单进程的，多实例部署时每个实例独立计数，总限流上限会变成 N 倍
- 这是有意的设计取舍：降级方案的目标是「有限流总比没有好」，而不是「精确限流」
- 生产环境多实例部署时 Redis 应该是高可用的（Sentinel / Cluster），内存降级只是极端情况的兜底
- 如果要求多实例精确限流，可以升级为 Redis Lua 脚本原子操作

---

## 二、超时中间件

### Q4：为什么要在中间件层做超时，而不是在 LLM 调用层？

**Situation**
LLM 调用是最慢的环节（2-10 秒），但 RAG 检索、数据库查询、序列化等环节也可能 hang 住。如果只在 LLM 层做超时，其他环节的阻塞无法兜底。

**Task**
设计一个全局超时机制，确保任何请求都不会无限期占用连接。

**Action**
- 中间件层用 `asyncio.wait_for` 包装整个请求处理链，作为全局兜底
- 区分两级超时：普通接口 30s，LLM 接口 120s（LLM 调用本身就慢）
- 超时返回 504 + JSON body，前端展示友好提示
- LLM 层可以额外做更细粒度的超时（如单次 API 调用 60s），两层互不冲突

**Result**
- 避免了慢请求占满连接池导致服务雪崩的风险
- 用户体验改善：超时后立即返回提示，而不是浏览器转圈等到断开

### Q5：`asyncio.wait_for` 能真正取消 DashScope SDK 的同步调用吗？

**回答要点**
- `asyncio.wait_for` 取消的是协程，如果 LLM 调用是在线程池中执行的同步调用（`run_in_executor`），线程本身不会被中断
- 但从用户视角，响应已经返回了 504，连接已释放，不会阻塞其他请求
- 真正的解决方案是使用 `httpx` 的异步客户端替代 DashScope SDK 的同步调用，配合 `httpx.Timeout` 实现真正的网络层超时
- 当前方案是务实的折中：中间件兜底 + SDK 自带的 `socket_timeout` 双重保障

---

## 三、结构化日志

### Q6：为什么要做结构化日志？和普通 print/logging 有什么区别？

**Situation**
项目初期用 `logging.basicConfig` 输出纯文本日志，排查线上问题时需要 grep 关键词，效率极低。当日志量达到万级时，纯文本日志几乎不可用。

**Task**
设计结构化日志方案，要求：每条日志可检索、可聚合、可告警。

**Action**
- 自定义 `StructuredJsonFormatter`，每条日志输出为 JSON 对象
- 每个请求自动注入：trace_id、method、path、status_code、latency_ms、client_ip
- 慢请求（>5s）自动标记 `slow_request: true`，方便告警规则匹配
- 静态资源和健康检查路径跳过日志，减少噪音
- 支持 `LOG_FORMAT=text` 环境变量切换回文本格式（开发环境可读性更好）

**Result**
- 日志可直接接入 ELK / Loki / CloudWatch，按 trace_id 串联一次请求的全链路
- 慢请求告警：`jq 'select(.slow_request==true)'` 一行命令定位性能瓶颈
- P99 延迟统计：`jq '.latency_ms' | sort -n | tail -1` 秒级出结果

### Q7：为什么不用 structlog？

**回答要点**
- 项目 requirements.txt 里确实有 structlog 依赖，但自己实现 JSON Formatter 只需 15 行代码
- 自己实现的好处：零额外依赖、完全可控、面试时能展示对 Python logging 模块的深入理解
- structlog 的优势在于 processor pipeline（日志处理链），我们的场景不需要这么复杂的处理链
- 如果后续需要更复杂的日志处理（脱敏、采样、异步写入），再迁移到 structlog 也很容易

---

## 四、健康检查

### Q8：liveness 和 readiness 的区别是什么？为什么要分开？

**Situation**
项目计划部署到 K8s，需要配置探针让 K8s 知道 Pod 的状态。

**Task**
设计两个健康检查端点，分别服务于不同的运维场景。

**Action**
- `/health`（liveness）：只检查进程是否活着，返回 uptime，不检查任何依赖。K8s livenessProbe 使用，失败时重启 Pod
- `/ready`（readiness）：检查 Redis 连通性、LLM API Key 是否配置、向量检索器是否初始化。K8s readinessProbe 使用，失败时从 Service 摘除流量
- LLM 检查只看 API Key 是否存在，不实际调用（调用一次 2-5 秒，健康检查要求毫秒级响应）
- 依赖状态分三级：healthy / degraded / unhealthy，degraded（如 API Key 缺失但进程正常）不影响 readiness

**Result**
- K8s 部署时：Redis 挂了 → readiness 失败 → 流量自动切到其他 Pod → 用户无感知
- 进程死锁 → liveness 失败 → K8s 自动重启 Pod → 30 秒内恢复

---

## 五、整体架构

### Q9：你的中间件执行顺序是怎么设计的？为什么这么排？

**回答要点**

```
请求 → Logging（最外层，记录所有请求包括被限流/超时的）
     → RateLimit（限流在超时之前，被限流的请求不应该占用超时计时）
     → Timeout（超时在业务逻辑之前，兜底所有下游耗时）
     → CORS（跨域处理）
     → GZip（响应压缩，最内层）
     → 路由处理
```

关键设计决策：
- Logging 必须在最外层：被限流返回 429 的请求也要记录日志（审计需求）
- RateLimit 在 Timeout 之前：被限流的请求应该立即返回 429，不应该进入超时计时浪费资源
- GZip 在最内层：只压缩最终响应，不影响中间件之间的数据传递

### Q10：如果让你继续优化，下一步会做什么？

**回答要点**（展示技术视野）

1. **并发控制（Semaphore）**：用 `asyncio.Semaphore` 限制同时并发的 LLM 请求数（如最多 5 个），超出排队或快速失败，防止突发流量打满 API 配额
2. **优雅降级**：Redis 挂了自动切内存缓存（已部分实现），LLM 超时返回预设兜底回复而不是 500
3. **幂等性**：基于 request hash + Redis 的幂等 key（TTL 30s），防止前端重复提交同一个占卜请求重复调用 LLM
4. **Prometheus 指标**：暴露 QPS、P99 延迟、LLM 调用次数、缓存命中率，配合 Grafana 可视化
5. **链路追踪**：trace_id 贯穿 LLM 调用、RAG 检索、Redis 操作，接入 Jaeger/Zipkin

---

## 六、Agent 架构

### Q11：塔罗 Agent 为什么用 ReAct 模式而不是固定 DAG？

**Situation**
八字分析是固定流程（排盘→五行→格局→喜用神→报告），适合 DAG。但塔罗占卜的流程因问题复杂度不同而变化：简单问题可能单张牌直接解读，复杂问题需要十字牌阵逐牌分析。

**Task**
设计一个灵活的塔罗占卜 Agent，让 LLM 自主决定调用哪些工具、调用顺序和次数。

**Action**
- 采用 ReAct（Reasoning + Acting）模式：LLM 作为决策中心，每轮决定调用哪个 Tool 或直接回复
- 定义 5 个 Tool：select_spread、draw_cards、interpret_single_card、retrieve_knowledge、synthesize_reading
- LangGraph 实现 agent_node ↔ tool_node 循环，safety_node 作为出口
- MAX_ITERATIONS=15 防止无限循环
- Tool 执行器（TarotToolExecutor）维护单次占卜的状态（已选牌阵、已抽牌、已解读）

**Result**
- LLM 能根据问题复杂度自主选择牌阵（简单问题选单张，复杂问题选凯尔特十字）
- 解读深度自适应：有时逐牌解读再综合，有时直接综合
- 相比固定 DAG，代码量减少 40%，但灵活性大幅提升

### Q12：ReAct 模式的 Tool Calling 是怎么实现的？

**回答要点**
- 使用 DashScope Generation API 的 `tools` 参数，传入 OpenAI function calling 格式的 Tool Schema
- LLM 返回 `tool_calls` 数组时，进入 tool_node 执行；返回纯文本时，进入 safety_node 结束
- Tool 执行结果以 `role: "tool"` 消息追加到 messages，下一轮 LLM 能看到执行结果
- 关键：Tool Schema 的 description 写得足够详细，让 LLM 理解每个工具的用途和调用时机

---

## 七、项目整体

### Q13：这个项目的技术亮点是什么？（1 分钟版）

> 这是一个基于 LangGraph 的智能命理分析系统，核心亮点有三个：
>
> 第一，**双 Agent 架构**。八字分析用固定 DAG（排盘→分析→报告），塔罗占卜用 ReAct 自主决策，两种模式通过 AgentRegistry 统一注册和路由，共享会话管理和 RAG 检索。
>
> 第二，**企业级中间件**。自己实现了限流（Redis 滑动窗口 + 内存降级）、超时兜底、JSON 结构化日志、K8s 健康检查四个中间件，不依赖第三方限流库，面试时能讲清楚每个的原理和设计取舍。
>
> 第三，**全链路可观测**。每个请求有 trace_id 贯穿日志，响应头注入限流信息，健康检查覆盖 Redis/LLM/向量检索三个核心依赖，慢请求自动标记告警。
