# 面试逐字稿 · 第六部分：测试设计 & 边界条件 & 反问环节

---

## 一、测试体系设计

### 1.1 测试分层策略

"我们的测试按分层策略组织，从底层到上层：

**第一层：单元测试（核心算法）**

专门测试 `BaziCalculator`、`WuxingCalculator`、`GejuEngine`、`YongshenEngine` 这些纯函数。这些函数有明确的输入输出，没有外部依赖，最适合单元测试。

```python
# test_simple.py - 核心计算单元测试
async def test_core():
    birth_info = BirthInfo(year=1990, month=1, day=1, hour=12, gender='男')
    calculator = BaziCalculator()
    result = calculator.calculate(birth_info)

    assert result.four_pillars.year is not None
    assert result.wuxing_score.total() > 0
```

这类测试不需要任何外部服务（不需要 Redis、不需要 DashScope API），可以在本地离线运行，CI 中也能跑。

**第二层：工作流集成测试**

测试整个 LangGraph 工作流，验证节点之间的数据流是否正确：

```python
# test_workflow.py
async def test_workflow():
    initial_state = {
        "user_input": {"year": 1990, "month": 1, ...},
        "status": "initialized",
        "messages": []
    }
    final_state = await app.ainvoke(initial_state)
    assert final_state.get('status') == 'safety_checked'
    assert final_state.get('bazi_result') is not None
```

这类测试需要 DashScope API（RAG + LLM），在 CI 中可以 mock 掉 API 调用，本地测试时用真实 API。

**第三层：超时测试**

```python
# test_workflow_timeout.py
async def test_workflow_with_timeout():
    try:
        final_state = await asyncio.wait_for(
            app.ainvoke(initial_state),
            timeout=30.0
        )
    except asyncio.TimeoutError:
        print('工作流超时，可能 API 卡住了')
```

超时测试用于验证在 API 响应慢时，系统能正确降级而不是永远挂起。

**第四层：API 级别 E2E 测试（demo_test.py）**

```python
# demo_test.py
async def test_full_api():
    async with httpx.AsyncClient() as client:
        # 新建会话 + 排盘
        resp = await client.post('/api/v1/chat/chat', json={
            "query": "帮我算下命，1990年1月1日中午12点，男，北京",
            "user_id": "test_user"
        })
        data = resp.json()
        assert data['success'] == True
        conversation_id = data['data']['conversation_id']

        # 追问
        resp2 = await client.post('/api/v1/chat/chat', json={
            "query": "那2026年运势怎么样？",
            "user_id": "test_user",
            "conversation_id": conversation_id
        })
        assert resp2.json()['data']['intent'] == 'FOLLOW_UP'
```

E2E 测试验证完整的用户旅程，是上线前的最后检查。"

---

### 1.2 Mock 策略

"对外部依赖做 Mock 是测试的关键：

**Mock DashScope LLM**：

```python
from unittest.mock import AsyncMock, patch

@patch('src.llm.dashscope_llm.DashScopeLLM.acall')
async def test_follow_up_without_api(mock_llm):
    mock_llm.return_value = "这是模拟的 LLM 回复"

    response = await _handle_follow_up(state_mgr, "2026年运势如何？", session_data)
    assert response == "这是模拟的 LLM 回复"
    mock_llm.assert_called_once()
```

**Mock Redis**：

```python
from unittest.mock import MagicMock

mock_redis = MagicMock()
mock_redis.get.return_value = None  # 模拟 cache miss
mock_redis.set.return_value = True

redis_cache_manager = RedisCacheManager(enable_cache=False)  # 或者注入 mock
```

**Mock Reranker**（测试检索流程不实际调用 API）：

```python
@patch.object(Reranker, '_check_rate_limit', return_value=False)
def test_rerank_fallback(mock_limit):
    # 强制触发降级排序
    reranker = Reranker()
    results = reranker.rerank("测试查询", [{"content": "文档1"}, {"content": "文档2"}])
    assert len(results) > 0  # 有结果（使用降级排序）
```"

---

## 二、边界条件测试

### 2.1 八字计算边界条件

"八字计算是纯数学计算，有很多边界情况：

**历史极端日期**：

```python
# 夏令时边界（1986-1991年中国实行过夏令时）
test_cases = [
    BirthInfo(year=1986, month=4, day=12, hour=2, gender='男'),  # 夏令时开始
    BirthInfo(year=1991, month=9, day=15, hour=2, gender='男'),  # 最后一年夏令时
    BirthInfo(year=1992, month=1, day=1, hour=0, gender='男'),   # 夏令时废除后
]
```

我们在 `SolarTermsCalculator.adjust_dst()` 里硬编码了夏令时区间（1986-1991年），对这个区间内出生的人做时间调整。边界日期（夏令时开始和结束当天的凌晨2点）是最容易出 bug 的地方，需要专门测试。

**子时跨日问题**：

23:00-24:00 是'早子时'，属于当天（第二天0:00开始才是'晚子时'，属于次日时柱）。

```python
# 子时边界测试
early_zi = BirthInfo(year=1990, month=1, day=1, hour=23, minute=30, gender='男')
# 时柱应该是'壬子'，还是属于当天

late_zi = BirthInfo(year=1990, month=1, day=2, hour=0, minute=30, gender='男')
# 时柱是否与 early_zi 相同（都是子时）？
```

这在八字学中是有争议的，我们的实现采用'早晚子时严格区分'的传统规则。

**节气换月边界**：

月柱按节气而非公历月份换月，比如 2024 年 2 月 4 日（立春）前是丑月，4 日后是寅月。节气的精确时刻（到分钟）是天文计算得到的，边界时刻的判断需要特别测试：

```python
# 立春当天边界
day_before = BirthInfo(year=2024, month=2, day=3, hour=23, gender='男')   # 丑月
day_on     = BirthInfo(year=2024, month=2, day=4, hour=17, gender='男')   # 立春后，寅月
day_on_before = BirthInfo(year=2024, month=2, day=4, hour=15, gender='男') # 立春前（如果立春在16:27），丑月
```

**真太阳时修正的极端经度**：

```python
# 新疆（极西）vs 黑龙江（极东）
xinjiang = BirthInfo(year=1990, month=1, day=1, hour=12, longitude=75.5, latitude=39.5, gender='男')
heilongjiang = BirthInfo(year=1990, month=1, day=1, hour=12, longitude=134.8, latitude=48.3, gender='男')
# 两地真太阳时差约3小时，时柱可能不同
```"

---

### 2.2 RAG 检索边界条件

"RAG 检索的边界条件：

**空查询**：

```python
results = retriever.search("", top_k=5)
assert results == []  # 或者返回空列表，不应该崩溃
```

**超长查询**：

```python
very_long_query = "甲" * 1000  # 1000字查询
# Embedding API 有 token 限制，超限应该截断而不是报错
```

**查询包含特殊字符**：

```python
special_chars = "正印格！@#$%"
# BM25 分词应该能处理，不崩溃
```

**ChromaDB 空集合**：知识库为空时，检索应该返回空列表而不是报错：

```python
empty_retriever = KnowledgeRetriever(collection_name="empty_test")
results = empty_retriever.search("任意查询", top_k=5)
assert results == []
```

**Rerank 输入只有 1 个文档**：

```python
single_doc = [{"content": "只有一篇文档", "id": "1"}]
results = reranker.rerank("查询", single_doc, top_k=5)
assert len(results) == 1  # top_k > 文档数，应该返回实际文档数
```"

---

### 2.3 API 输入边界条件

"对 FastAPI 接口的边界输入测试：

**日期边界**：

```python
# 无效日期
invalid_cases = [
    {"year": 1900, "month": 2, "day": 29},  # 1900年不是闰年
    {"year": 2023, "month": 13, "day": 1},   # 月份超范围
    {"year": 2023, "month": 1, "day": 32},   # 日期超范围
    {"year": 999, "month": 1, "day": 1},     # 年份太小（公历999年前）
    {"year": 9999, "month": 12, "day": 31},  # 未来极端日期
]
# BirthInfo Pydantic 校验应该拒绝这些
```

**性别字段**：

```python
gender_cases = ["male", "female", "男", "女", "M", "F", "1", "0", ""]
# 应该只接受 male/female/男/女，其他应该报 400
# 代码里 GENDER_TO_CHINESE.get(gender_raw, "男") 有默认值，但 Pydantic 校验应该先过
```

**特殊字符注入**：

```python
xss_attempt = {"query": "<script>alert('xss')</script>"}
sql_injection = {"query": "'; DROP TABLE sessions; --"}
# FastAPI 通过 Pydantic 接收 JSON，不做 SQL 查询，这些不应该有实际危害
# 但要测试系统不崩溃，返回的响应里不包含原始特殊字符
```

**超长输入**：

```python
very_long_query = "a" * 100000  # 10万字
# 应该触发 Pydantic 的 max_length 校验（如果配置了的话）
# 或者在意图识别/LLM 调用前截断
```"

---

### 2.4 并发边界条件

"并发场景的边界测试：

**同一 conversation_id 的并发请求**：

```python
async def test_concurrent_same_session():
    conversation_id = "test_concurrent"

    # 并发发送 5 个请求到同一会话
    tasks = [
        send_chat_message(f"问题 {i}", conversation_id)
        for i in range(5)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 不应该有任何请求报错（即使数据竞争）
    errors = [r for r in results if isinstance(r, Exception)]
    assert len(errors) == 0
```

**限流边界**：

```python
async def test_rate_limit():
    # 快速发送 limit+1 个请求
    for i in range(RATE_LIMIT + 1):
        resp = await client.post("/api/v1/chat/chat", ...)

    # 最后一个应该得到 429
    assert resp.status_code == 429
    assert resp.json()["error"] == "RATE_LIMIT_EXCEEDED"
    assert "Retry-After" in resp.headers
```"

---

## 三、已知问题 & 技术债

### 3.1 面试时如何坦诚地说技术债

"面试官会欣赏能清楚说出系统局限性的候选人，这说明你不是在背稿，而是真的理解了系统。

我们的已知技术债：

**第一，会话并发写冲突**：同一用户同时发两条消息，后写入的会覆盖前写入的 assistant 消息。解法是会话级分布式锁，但我们没有实现。影响评级：低（用户极少在多标签同时操作）。

**第二，磁盘满没有告警**：文件写入失败时只记录日志，没有主动告警。解法是加 prometheus 监控 + 告警规则。影响评级：中（磁盘满了用户数据会丢失，但系统不崩溃）。

**第三，BM25 索引热更新**：目前更新知识库需要重启服务。解法是实现在线增量索引更新 + 原子交换。影响评级：低（知识库更新频率极低）。

**第四，文件写入非原子**：JSON 写到一半崩溃会产生损坏文件。解法是先写临时文件再 rename。影响评级：中（崩溃场景下会话数据丢失，但文件不会损坏其他文件）。

**第五，LLM Prompt 没有版本管理**：Prompt 存在文件里，但没有 A/B 测试机制，没有效果评估指标。解法是引入 prompt management 系统（如 LangSmith）。影响评级：中（Prompt 质量直接影响用户体验）。"

---

## 四、系统监控 & 可观测性

### 4.1 日志体系

"我们用结构化日志（JSON 格式），通过 `LoggingMiddleware` 统一格式：

```python
# 每个请求记录
{
    "timestamp": "2026-03-22T10:30:00Z",
    "trace_id": "a3f4e2...",
    "method": "POST",
    "path": "/api/v1/chat/chat",
    "status_code": 200,
    "duration_ms": 8432,
    "user_id": "user_001"
}
```

结构化日志的好处是可以直接被 Elasticsearch、Loki 等日志系统索引，通过 trace_id 过滤出单次请求的完整链路。

每个 LangGraph 节点也会打日志：`logger.info("【节点 N】执行 XXX...")`，加上 trace_id，可以看到每次请求在哪个节点花了多少时间。"

---

### 4.2 健康检查端点

"健康检查 `/api/v1/bazi/health` 返回系统各组件状态：

```python
@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "components": {
            "calculator": "ok",
            "redis": "connected" if redis_cache.client else "disconnected",
            "chromadb": "ok",
            "reranker": {
                "status": "ok",
                "remaining_calls": reranker.get_remaining_calls()
            }
        }
    }
```

这个端点用于：
1. 负载均衡器的健康探测（只有 200 才转发流量）
2. 运维手工检查系统状态
3. Rerank 调用次数预警（剩余次数 < 100 时告警）"

---

## 五、反问环节（面试结尾）

### 5.1 反问问题库

"反问环节同样重要，好的问题能展示你对技术深度和工程实践的关注。以下是针对不同面试场景的问题：

**针对技术栈偏大模型/AI 的团队**：

1. '贵团队在生产环境的 LLM 应用里，怎么做 prompt 版本管理？有没有引入 LLMOps 工具？'
2. '对于 RAG 系统的评估，你们有没有做 RAGas 这类自动化评估？还是主要靠人工？'
3. '在处理 LLM 输出的稳定性问题上（比如 JSON 格式不对），你们有什么工程实践？'

**针对后端偏向分布式的团队**：

1. '我对服务级别的限流和熔断（比如 Sentinel、Resilience4j）很感兴趣，贵团队的微服务间调用是怎么做稳定性保护的？'
2. '分布式 Session 管理这块，贵团队是用 Redis + 本地内存双层，还是有其他方案？'

**针对平台/基础设施团队**：

1. '贵团队的可观测性体系是怎么搭建的？Tracing 是用 Jaeger 还是 Zipkin，还是 OTel？'
2. '容器化之后，LangGraph 这类有状态的工作流任务，你们是怎么做调度和故障恢复的？'

**通用好问题（任何技术面试都适用）**：

1. '这个职位最近3个月主要在解决什么技术挑战？'
2. '团队现在技术决策最大的约束是什么，是团队规模、成本，还是技术债？'
3. '您觉得来这个团队要做好工作，最需要补强的技术能力是什么？'"

---

### 5.2 如何应对'你不会的问题'

"面试中一定会被问到不会的问题，正确的应对方式：

**正确做法**：

'这个具体实现我没有做过，但我可以从已知的原理推导一下。[思考]...我认为大概是这样，不过我不确定具体细节，回去我会深入了解一下。'

**错误做法**：
- 直接说'不知道'，没有任何思考
- 硬撑，乱说一通，被面试官发现更糟

**几个常被问到的知识点（可以提前准备）**：

1. **向量数据库的 ANN 算法**：HNSW、IVF-PQ、ScaNN 的原理和对比
2. **Redis 集群模式**：主从复制、哨兵、Cluster 三种模式的区别
3. **异步框架的事件循环**：asyncio 的 event loop、协程调度机制
4. **LangChain vs LangGraph vs AutoGen**：三者的适用场景和设计哲学

这些都是从我们项目延伸出去的知识点，可以说'我在项目里用了 X，但对更底层的 Y 了解还不够深入，我有兴趣深入学习'。"

---

## 六、最终总结（面试收尾）

### 6.1 一页纸项目总结

"如果面试官问'用一两分钟总结一下这个项目'：

'这个项目是一个完整的 AI Agent 工程实践，核心技术点有四个：

第一，LangGraph 11 节点状态机工作流，每个节点职责单一，通过条件路由实现故障转移，任何节点失败都有降级路径，不会崩溃。

第二，三层 RAG 检索架构：BM25 关键词召回 + 向量语义召回 + Cross-encoder Rerank 精排，配合四种可切换的检索模式，在精准度和性能之间灵活权衡。

第三，生产级可靠性：限流（分级+Redis降级）、超时（分层120s/30s）、缓存（双层Redis+本地）、双写（Redis+文件），每个外部依赖都有对应的降级方案。

第四，可扩展的 Agent 架构：BaseAgent 抽象层 + AgentRegistry 插件注册，新增功能域只需实现接口，不改框架代码。

最大的技术亮点是：**不是简单地把问题甩给 LLM，而是用规则引擎保证计算准确性，用 LLM 提供语言表达质量，两者分工明确**。这比纯 prompt engineering 更可控、更可测试。'"

---

### 6.2 常见 HR/行为问题的项目关联

**Q: 讲一个你解决了困难技术问题的例子**

'项目里最难的一个问题是 LangGraph 状态和持久化层的双重表示问题。LangGraph 要求状态是 TypedDict，但 Redis/文件存储需要 Pydantic BaseModel 做序列化，两边的字段名、嵌套结构都不完全一样，导致我每次存取都要写大量的转换代码，很容易出 bug。

我重新设计了 UnifiedSession，作为两套系统之间的桥梁，内部封装了 `to_graph_state()` 和 `absorb_graph_result()` 两个互逆的转换方法。这样调用方只需要操作 UnifiedSession，不需要关心底层的格式差异。这个重构同时也解决了 bazi_result、tarot_result 这些分析结果的存储问题，之前它们都是散落在不同地方的，现在统一由 UnifiedSession 管理。'

**Q: 你怎么保证代码质量？**

'主要靠三个实践：第一，每个核心模块都有对应的测试用例，包括边界条件；第二，关键设计决策写注释说明理由，比如为什么用 ThreadingLock 而不是 asyncio.Lock；第三，函数和类的职责明确，我有意识地避免把多个职责塞进一个函数，比如缓存操作、业务逻辑分开。'

**Q: 你在这个项目里最大的收获是什么？**

'最大的收获是对"高可用"从概念到具体实现的理解。之前觉得高可用就是"加个 try/catch"，做完这个项目才明白：高可用是一个系统性的设计——不只是错误处理，还包括降级策略、优雅关闭、健康检查、监控告警，以及接受某些 trade-off（比如放弃强一致性换取可用性）。

另一个收获是对异步编程的深入理解。asyncio 的单线程模型、与 threading.Lock 的配合、asyncio.wait_for 的实现原理，这些在实际项目里碰到真实问题时才能真正理解，光看文档是不够的。'
