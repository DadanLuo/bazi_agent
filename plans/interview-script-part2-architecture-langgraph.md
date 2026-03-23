# 面试逐字稿 · 第二部分：整体架构 & LangGraph 工作流

---

## 一、整体架构概述（画图式讲解）

"好，我来讲一下整体架构，我会按照请求的流转路径来讲。

一个请求进来之后，第一层是**中间件层**，这里有五个中间件按洋葱模型嵌套，从外到内依次是：结构化日志中间件、限流中间件、超时中间件、CORS 中间件、GZip 压缩中间件。

通过中间件之后，请求到达 **FastAPI 路由层**，分两条主路径：
- `/api/v1/bazi/analyze`：直接调用八字排盘，走完整 LangGraph 工作流
- `/api/v1/chat/chat`：多轮对话入口，先做意图识别，再按意图路由

核心业务在 **LangGraph 工作流层**，这是一个 11 节点的有向无环图（DAG），节点按顺序执行，每个节点执行后通过条件边决定下一个节点。

工作流执行过程中，中间节点会访问 **底层服务层**：
- 天文排盘引擎（纯 Python 计算，不依赖外部 API）
- ChromaDB 向量存储（本地持久化）
- DashScope API（Embedding、Rerank、LLM）

执行结果通过 **存储层** 持久化：Redis 写热数据，文件存储写冷数据，双写保证可用性。"

---

## 二、中间件架构详解

### 2.1 洋葱模型

"FastAPI/Starlette 的中间件是洋葱模型，后注册的先执行。我们的注册顺序是：

```python
app.add_middleware(GZipMiddleware)          # 最内层，最后执行
app.add_middleware(CORSMiddleware)          # 内层
app.add_middleware(TimeoutMiddleware)       # 中层
app.add_middleware(RateLimitMiddleware)     # 外层
app.add_middleware(LoggingMiddleware)       # 最外层，最先执行
```

所以请求进来的顺序是：Logging → RateLimit → Timeout → CORS → GZip → 路由处理器。

注意 **Timeout 在 RateLimit 里面**，这是有意为之的。如果调换顺序，超时中间件先执行，那么超时计时从请求进入 Timeout 开始，这时候 RateLimit 还没检查，如果 RateLimit 做了很多计算，占用了超时预算，不合理。把 Timeout 放在 RateLimit 里面，超时计时只计算实际业务处理的时间。"

### 2.2 限流中间件（面试重点）

"限流中间件的设计有几个值得展开说的点：

**分级限流**：区分 LLM 路径和普通路径，LLM 路径的限制更严格。因为调用大模型的成本高，要防止某个用户疯狂刷接口。具体在代码里：

```python
LLM_PATH_PREFIXES = ("/api/v1/chat/chat", "/api/v1/chat/followup")
is_llm_path = any(path.startswith(p) for p in LLM_PATH_PREFIXES)
limit = RATE_LIMIT_LLM_PER_MINUTE if is_llm_path else RATE_LIMIT_PER_MINUTE
```

**Redis 优先，内存降级**：限流计数优先存 Redis，支持多实例共享计数；如果 Redis 不可用，自动降级到进程内存计数。内存降级有个局限：只对单进程有效，如果有多个实例，每个实例独立计数，相当于限制放宽了倍数，但至少不会崩溃。

**Redis 实现用 INCR + EXPIRE 固定窗口**：

```python
pipe = self.redis.pipeline()
pipe.incr(key)
pipe.ttl(key)
results = pipe.execute()

current_count = results[0]
ttl = results[1]
if ttl == -1:  # key 刚被创建，还没设置过期时间
    self.redis.expire(key, window)
```

用 pipeline 做原子操作，避免 INCR 和 EXPIRE 之间的竞态。

**透传 Retry-After Header**：限流触发时，响应头会带 `Retry-After` 字段，告诉客户端多久之后可以重试，这是标准 HTTP 429 的最佳实践。"

### 2.3 超时中间件

"超时中间件用 `asyncio.wait_for` 包裹 `call_next`：

```python
response = await asyncio.wait_for(call_next(request), timeout=timeout)
```

LLM 路径超时设置 120 秒，普通路径 30 秒。超时返回 504 Gateway Timeout，带 trace_id 方便排查日志。

为什么用 `asyncio.wait_for` 而不是用 threading 的 Timer？因为我们用的是 async 框架，`asyncio.wait_for` 是协程级别的取消，不会影响其他并发请求，overhead 极低。如果用 threading，会引入跨线程的复杂性。"

---

## 三、LangGraph 工作流详解

### 3.1 节点总览（11节点状态机）

"LangGraph 图由 11 个节点构成，我按执行顺序介绍：

| 编号 | 节点名 | 职责 | 可能失败 |
|------|--------|------|----------|
| 1 | validate_input | 输入验证（Pydantic） | 缺字段/类型错误 |
| 2 | calculate_bazi | 四柱排盘（天文算法） | 极端日期 |
| 3 | analyze_wuxing | 五行得分计算 | 几乎不失败 |
| 4 | determine_geju | 格局判定（规则引擎） | 规则缺失 |
| 5 | find_yongshen | 喜用神推导（规则引擎） | 规则缺失 |
| 6 | check_liunian | 流年运势分析 | 几乎不失败 |
| 7 | analyze_dayun | 大运分析 | 几乎不失败 |
| 8 | retrieve_knowledge | RAG 古籍检索 | 网络/API失败 |
| 9 | llm_generate | 大模型报告生成 | 网络/超时/限流 |
| 10 | generate_report | 组装最终报告 | 几乎不失败 |
| 11 | safety_check | 安全输出封装 | 最终兜底节点 |

每个节点的设计原则是：**输入从 state 读，输出写回 state，副作用最小化**。节点函数的签名是 `(state: BaziAgentState) -> Dict[str, Any]`，返回值是 partial state update，LangGraph 会自动 merge 进全局 state。"

### 3.2 状态定义（BaziAgentState）

"状态定义是整个工作流的核心数据契约。我们用 TypedDict 定义，而不是 Pydantic BaseModel，原因是 LangGraph 的状态合并机制需要 dict-like 的类型。

状态字段按职能分组：

```python
class BaziAgentState(TypedDict, total=False):
    # 基础输入
    user_input: Dict[str, Any]          # 原始用户输入
    validated_input: Dict[str, Any]      # 验证后的输入

    # 八字分析结果（各节点依次填充）
    bazi_result: Dict[str, Any]          # 四柱排盘结果
    wuxing_analysis: Dict[str, Any]      # 五行分析
    geju_analysis: Dict[str, Any]        # 格局分析
    yongshen_analysis: Dict[str, Any]    # 喜用神分析
    liunian_analysis: Dict[str, Any]     # 流年分析
    dayun_analysis: Dict[str, Any]       # 大运分析

    # RAG 检索
    knowledge_context: str               # 检索到的知识上下文
    retrieved_docs: List[Dict]           # 检索文档列表
    rag_queries: List[str]               # 检索查询列表
    llm_response: str                    # LLM 生成的报告

    # 最终输出
    final_report: Dict[str, Any]         # 组装后的完整报告
    safe_output: Dict[str, Any]          # 安全包装后的输出
    status: str                          # 当前状态标识
    error: str                           # 错误信息
```

`total=False` 表示所有字段都是可选的，这样每个节点只需要返回它关心的字段，不需要把所有字段都带上。"

### 3.3 条件路由（故障转移核心）

"每个节点执行完之后，都有一个对应的路由函数决定下一步走哪里。这是我们实现故障转移的核心机制：

```python
def route_after_calculation(state: BaziAgentState) -> Literal["analyze_wuxing", "safety_check"]:
    if state.get("status") == "calculation_failed":
        logger.warning("排盘计算失败，跳转至安全节点")
        return "safety_check"
    return "analyze_wuxing"
```

所有路由函数都遵循同一模式：
- 检查 `state["status"]` 是否以 `_failed` 结尾
- 失败则路由到 `safety_check`（最终兜底节点）
- 成功则路由到下一个正常节点

这种设计的好处是：**任何一个节点失败，都不会导致整个 workflow 崩溃**，而是优雅地降级到安全输出节点，返回一个包含错误信息的响应，让前端能正常显示。

面试官常问：'为什么要单独设一个 safety_check 节点，而不是在路由函数里直接返回 END？'

答：因为我们希望**无论走什么路径，最终输出都经过统一的安全检查和格式封装**。safety_check 节点负责把 `final_report` 包装成 `safe_output`，包括敏感内容过滤、格式标准化。如果直接 END，那每条错误路径都要单独处理输出格式，代码重复且容易遗漏。"

### 3.4 知识检索节点（RAG 节点的工程细节）

"第 8 个节点 retrieve_knowledge 是 RAG 接入点，有几个工程细节值得说：

**查询构建**：不是把用户原始输入直接扔给检索器，而是根据排盘结果构建 3 个语义更具体的查询：

```python
# 1. 基于日主和月令（最核心的命理要素）
queries.append(f"{day_master}日主生于{month_zhi}月")

# 2. 基于格局（如果不是常格）
if geju_type != "常格":
    queries.append(f"{geju_type}的特点与喜忌")

# 3. 基于喜用神
queries.append(f"{' '.join(yongshen)}五行的含义与应用")
```

这样检索的精准度比'帮我分析这个八字'高很多。

**结果去重**：三个查询可能检索到重叠的文档，用内容 hash 去重：

```python
seen_content = set()
for doc in all_docs:
    content = doc.get("content", "")
    if content not in seen_content:
        unique_docs.append(doc)
        seen_content.add(content)
```

**容错降级**：如果检索器未初始化（比如 ChromaDB 文件损坏），节点返回 `knowledge_skipped` 而不是 `failed`，后续的 LLM 节点会检测到 knowledge_context 为空，使用默认提示词继续生成，而不会中断。

**知识上下文截断**：`format_context(unique_docs, max_length=2000)` 对检索结果做截断，避免 context 太长占满 LLM 的 token 预算。"

### 3.5 LLM 生成节点

"第 9 个节点 llm_generate，把前面所有节点的结果打包给 LLM：

```python
bazi_data = {
    "birth_info": state.get("bazi_result", {}).get("birth_info", {}),
    "four_pillars": ...,
    "wuxing_analysis": ...,
    "geju_analysis": ...,
    "yongshen_analysis": ...,
    "liunian_analysis": {}
}
knowledge_context = state.get("knowledge_context", "")
report_content = llm.generate_bazi_report(bazi_data, knowledge_context)
```

这里有个设计原则：**LLM 节点只做语言生成，不做逻辑计算**。所有命理逻辑都在前面的规则引擎节点里完成了，LLM 拿到的是已经计算好的五行分数、格局类型、喜用神，它的职责是把这些结构化数据转化成通俗易懂的自然语言。

这和'让 LLM 直接算命'的方案有本质区别：规则引擎保证了计算准确性，LLM 保证了表达质量，两者各司其职。"

### 3.6 简化版 Graph

"除了完整版的 `bazi_graph`，我们还有一个 `simple_graph`，去掉了 RAG 检索和 LLM 生成节点，只保留排盘计算部分，响应时间从约 10 秒降到 1-2 秒。

两个图通过 `analysis_mode` 参数切换：

```python
if analysis_mode == "simple":
    result = await simple_app.ainvoke(graph_input)
else:
    result = await bazi_app.ainvoke(graph_input)
```

简化版适合演示场景和快速预览，完整版适合用户需要详细解读的场景。这种双图设计让我们可以在不牺牲用户体验的情况下控制 API 调用成本。"

---

## 四、多轮对话架构

### 4.1 意图识别 + 路由分发

"多轮对话的核心是意图识别。我们定义了 5 种意图类型：

```
NEW_ANALYSIS   → 用户提供出生信息，触发新的排盘
FOLLOW_UP      → 用户在已有排盘基础上追问
TOPIC_SWITCH   → 用户换了话题（比如从八字换到风水）
CLARIFICATION  → 用户对某个概念不理解，要求解释
GENERAL_QUERY  → 其他通用问题
```

意图识别基于关键词匹配和会话上下文，不依赖 LLM，所以非常快（毫秒级），不增加延迟。

识别到意图后，分发到对应的处理函数：

```python
INTENT_HANDLERS = {
    "FOLLOW_UP":     _handle_follow_up,
    "TOPIC_SWITCH":  _handle_topic_switch,
    "CLARIFICATION": _handle_clarification,
    "GENERAL_QUERY": _handle_general_query,
}
handler = INTENT_HANDLERS.get(intent, _handle_general_query)
response = await handler(state_manager, user_query, session_data)
```

不同意图使用不同的上下文构建策略：
- FOLLOW_UP：使用完整对话历史 + RAG检索 + 八字缓存数据
- TOPIC_SWITCH：只用最近 3 条消息，避免旧话题干扰  
- CLARIFICATION：只用最近 2 轮，轻量上下文
- GENERAL_QUERY：标准 RAG 流程"

### 4.2 槽位填充（Slot Filling）

"槽位填充是对话系统的经典设计。每个 Agent 声明自己需要的槽位，系统负责从用户输入中提取和补全：

```python
class SlotSchema:
    def __init__(self, slots: Dict[str, Dict[str, Any]]):
        self.slots = slots

    def get_missing(self, filled: Dict[str, Any]) -> List[str]:
        return [
            name for name, schema in self.slots.items()
            if schema.get("required") and name not in filled
        ]
```

BaziAgent 定义了 6 个槽位：birth_year、birth_month、birth_day 为必填，birth_hour、birth_place、gender 中 gender 也是必填，birth_hour 和 birth_place 可选。

如果用户说'帮我算命，我是1990年1月1日出生的男性'，系统能提取 birth_year=1990、birth_month=1、birth_day=1、gender=男，然后发现 birth_hour 未填，使用默认值 12（正午）。

如果必填槽位缺失，系统会追问：'还需要以下信息：出生月、性别'，直到槽位填满才触发排盘。"

### 4.3 会话记忆与摘要

"会话记忆有个'上下文窗口溢出'的问题：对话轮数一多，历史消息超过 LLM 的 context window，就没法把完整历史送给 LLM。

我们的解法是**会话摘要**：

```python
if session_data.metadata.message_count > 10:
    summarizer = ConversationSummarizer(llm)
    openai_msgs = session_data.get_openai_format()
    summarizer.compress_conversation(openai_msgs, summary_threshold=10, keep_latest=5)
```

当对话超过 10 轮时，把早期的对话压缩成一段摘要文本，只保留最近 5 轮的完整消息。这样 LLM 拿到的上下文既包含早期对话的要点，又有最近的完整对话，不会超 token 限制。

这是一种 **sliding window + summarization** 的混合策略，比纯滑动窗口（直接丢掉早期消息）保留了更多有效信息。"

---

## 五、整体架构总结（一句话版本）

"整体架构可以概括为：**FastAPI 中间件洋葱 + LangGraph 11 节点 DAG + 混合 RAG 检索 + Redis 双写存储**。

核心设计理念是：
1. **关注点分离**：计算、检索、生成、存储各自独立，节点间只通过 state dict 通信
2. **每个环节都有故障处理**：从中间件的限流超时，到 LangGraph 的条件路由兜底，到 Redis 的文件降级，系统在任何单点故障下都能给出有意义的响应
3. **可观测性**：每个节点都有 logger 记录，配合 LoggingMiddleware 的 trace_id，可以追踪任意请求的完整链路"

---

## 六、常见追问与应答

**Q: LangGraph 和传统的函数链式调用比，具体好在哪里？**

"好在两点：第一，状态是显式的全局对象，不是散落的局部变量，任何节点都能读到任何其他节点的结果，调试时可以直接 dump 完整状态；第二，条件路由是声明式的，错误处理集中在路由函数里，而不是每个函数里都要写 try/catch 然后决定下一步怎么办，代码结构更清晰。"

**Q: 如果 LLM 调用超时，用户看到的是什么？**

"有两层保护。第一层是 TimeoutMiddleware，120 秒超时返回 504；第二层是 `route_after_llm` 路由函数，如果 LLM 节点返回 `llm_generation_failed`，直接跳到 `safety_check`，safety_check 检测到没有 final_report，会返回一个包含基础排盘数据（四柱、五行、格局）的简化报告，而不是空响应。所以用户至少能看到结构化的排盘数据，只是没有 AI 解读文字。"

**Q: trace_id 是怎么实现的？**

"用 Python 的 contextvars，每个请求进入 LoggingMiddleware 时生成一个 UUID，存入 `contextvars.ContextVar`，整个请求生命周期内的任何地方都可以通过 `get_trace_id()` 取到这个 ID，日志里统一打印，方便在日志系统里过滤某一次请求的完整链路。这比传参更优雅，不需要把 trace_id 一层层往下传。"

**Q: LangGraph 图是每次请求重新创建，还是单例？**

"单例。`create_bazi_graph()` 在模块加载时调用一次，`bazi_graph.compile()` 的结果赋给模块级变量 `app`，所有请求共享同一个编译后的图。

每次请求调用 `app.ainvoke(initial_state)` 时，传入的是一个全新的 state dict，所以请求间的状态完全隔离。图的结构（节点和边）是不可变的，线程安全。"
