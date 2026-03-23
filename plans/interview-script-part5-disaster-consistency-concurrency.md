# 面试逐字稿 · 第五部分：高容灾 & 数据一致性 & 并发控制

---

## 一、高容灾设计

### 1.1 什么是我们语境下的容灾

"容灾（Disaster Recovery）关注的是：**在灾难性事件（服务器宕机、数据中心故障、数据损坏）发生后，系统如何恢复**。

对于我们这个体量的应用，容灾主要考虑以下场景：
1. **进程崩溃**：uvicorn 进程异常退出
2. **Redis 宕机**：Redis 服务不可用，数据丢失
3. **磁盘损坏**：会话文件损坏
4. **部分数据损坏**：JSON 文件写到一半进程崩溃

我来逐一分析我们的应对。"

---

### 1.2 进程崩溃的容灾

"**进程崩溃的影响**：正在处理中的请求会丢失，用户得到连接断开错误。

**恢复机制**：
1. 使用进程守护工具（supervisor 或 systemd）自动重启 uvicorn
2. 重启后，Redis 里的热数据仍然在（Redis 独立进程，不受影响）
3. 文件里的持久化数据也在
4. 新进程启动后，已有会话可以从 Redis 或文件加载恢复

**对正在处理的请求**：LangGraph 工作流不是幂等的（调用了 LLM），所以崩溃中断的请求无法自动恢复，用户需要重新发起请求。这是可以接受的，命理分析不是金融交易，不需要 exactly-once 语义。

**应用启动时的容错**：

```python
# main.py 的 lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    ...
    try:
        from src.agents.bazi_agent import BaziAgent
        AgentRegistry.register(BaziAgent())
    except Exception as e:
        logger.warning(f"Agent 注册失败: {e}")  # 不崩溃，只记录
    
    # chat_api 注册也是容错的
    try:
        from src.api.chat_api import router as chat_router
        app.include_router(chat_router)
    except Exception as e:
        logger.warning(f"多轮对话路由注册失败（不影响核心功能）: {e}")
```

即使 Agent 注册失败、多轮对话路由失败，核心的排盘 API (`/api/v1/bazi/analyze`) 仍然能正常工作。这是**启动时的部分降级**，保证最小可用集。"

---

### 1.3 Redis 宕机的数据容灾

"**Redis 宕机的影响**：
- 缓存失效：所有请求都走全量计算，响应变慢（从 ~100ms 变成 ~10s）
- 会话数据：Redis 里的会话消息不可用

**恢复机制**：
- 文件存储作为 cold backup，会话数据可以从文件恢复
- Redis 重启后缓存从空开始预热，随着请求进来逐渐填充

**Redis 持久化配置建议**（项目中未实现，但面试时可以提）：
在生产环境，Redis 应该开启 AOF（Append Only File）持久化，记录每条写命令，Redis 重启后重放 AOF 恢复数据。

```conf
# redis.conf
appendonly yes
appendfsync everysec  # 每秒刷盘，平衡性能和持久化
```

我们的项目对 Redis 数据的持久性要求不高（有文件存储兜底），所以目前没有配置 Redis 持久化，但在真正的生产部署中这是必须的。"

---

### 1.4 文件数据损坏的容灾

"**文件损坏场景**：JSON 写到一半进程崩溃，导致文件格式不完整。

**我们的处理**：

```python
def load_session(self, conversation_id: str) -> Optional[SessionData]:
    try:
        with gzip.open(file_path, 'rt', encoding='utf-8') as f:
            session_dict = json.load(f)
        return SessionData(**session_dict)
    except Exception as e:
        logger.error(f"加载会话失败: {e}")
        return None  # 返回 None 而不是抛异常
```

损坏的文件会被捕获异常，返回 None。上层调用方收到 None 会创建新会话，损失的是这个会话的历史记录，用户体验是'需要重新排盘'，不会 500 错误。

**预防措施（原子写）**：更好的做法是用原子写——先写临时文件，写完再 rename 到目标文件：

```python
# 更安全的写法（项目中可以加）
import os, tempfile

with tempfile.NamedTemporaryFile(
    mode='wt', suffix='.tmp',
    dir=file_path.parent, delete=False
) as tmp:
    json.dump(session_dict, tmp)
    tmp_path = tmp.name

os.rename(tmp_path, file_path)  # 原子操作
```

`os.rename` 在同一文件系统内是原子的（POSIX 语义），这样要么旧文件、要么新文件，不会出现'写到一半'的状态。目前我们没有实现这个，是 v0.3.0 的优化计划。"

---

## 二、数据一致性

### 2.1 Redis + 文件双写的一致性问题

"双写最典型的一致性问题：先写 Redis 成功，写文件失败。

```python
def save(self):
    # 写 Redis
    redis_success = False
    if redis_cache:
        redis_success = redis_cache.cache_conversation(...)
    
    # 写文件（不依赖 Redis 是否成功）
    file_success = file_storage.save_session(...)
    
    if not file_success:
        logger.error("文件写入失败，仅 Redis 有最新数据")
```

**这是 CP 还是 AP？**

在 CAP 定理的语境下，我们的双写是一个最终一致性（Eventual Consistency）设计：

- Redis 和文件可能在短时间内不一致（Redis 有新数据，文件还是旧数据）
- TTL 过期后 Redis 数据消失，下次从文件读，恢复一致
- 如果文件写失败，会话的最新状态只在 Redis，Redis 重启就丢了

**我们接受这种一致性级别的理由**：会话数据不是强一致性需求。命理分析应用中，如果用户刷新页面后少了一条对话记录，影响很小；但如果为了强一致性引入分布式事务，系统复杂度大幅上升，代价不匹配。

**对比金融场景**：如果是支付系统，每笔交易必须严格一致，就需要两阶段提交（2PC）或者 Saga 模式，错误时补偿回滚。命理系统不需要这种强度。"

---

### 2.2 LangGraph 状态的一致性

"LangGraph 每次 `ainvoke` 是一个独立的事务：

- 输入是初始 state dict
- 输出是最终 state dict
- 中间节点的状态修改在节点返回之前不可见（节点只返回 partial update，LangGraph merge）

这意味着：**如果 `ainvoke` 在中间某个节点崩溃，不会有'半完成'状态被写入存储**——因为我们只在 `ainvoke` 完成后才把结果写入 Redis 和文件：

```python
result = await bazi_app.ainvoke(graph_input)  # 完整执行

# 只有 ainvoke 完成后才写 Redis
if redis_cache:
    redis_cache.cache_bazi_result(birth_info=birth_info, result={...})

# 只有 ainvoke 完成后才写文件
state_manager.save()
```

这确保了存储里只有完整的分析结果，不会有中间状态。

**边界情况**：`ainvoke` 抛异常时（不是通过条件路由返回 failed，而是真正的 Python 异常），catch 住异常，不做任何存储操作，返回错误响应。会话状态保持调用前的状态，用户下次还是从原来的状态继续。"

---

### 2.3 UnifiedSession 的状态同步

"UnifiedSession 有两个数据视图：
1. 自身的 Pydantic 模型（用于 Redis/文件持久化）
2. 转换成的 dict（用于 LangGraph ainvoke）

同步逻辑：

```python
# 调用前：session → graph state
graph_input = session.to_graph_state()
result = await bazi_app.ainvoke(graph_input)

# 调用后：graph result → session
session.absorb_graph_result(result)
```

`absorb_graph_result` 把 LangGraph 的输出合并回 session：

```python
def absorb_graph_result(self, graph_output):
    # 更新分析状态
    for key in ANALYSIS_STATE_KEYS:
        if key in graph_output:
            self.analysis_state[key] = graph_output[key]
    
    # 更新八字缓存（如果有新排盘结果）
    if graph_output.get('bazi_result'):
        self.bazi_cache = BaziCacheData(
            bazi_data=graph_output['bazi_result'],
            analysis_result=graph_output.get('final_report', {}),
        )
    
    self.metadata.updated_at = datetime.now()
```

这个设计的关键是：`to_graph_state()` 和 `absorb_graph_result()` 是互逆的，数据在两个表示之间转换时不会丢失或变形。这是通过明确定义 `ANALYSIS_STATE_KEYS` 列表（两边都知道要同步哪些字段）来保证的。"

---

## 三、并发控制

### 3.1 LangGraph 并发安全性

"LangGraph `app`（编译后的图）是无状态的，所有状态都在每次 `ainvoke` 的参数里。多个并发请求调用 `app.ainvoke(state1)` 和 `app.ainvoke(state2)`，它们完全独立，没有任何共享状态，天然并发安全。

Python 的 asyncio 是单线程事件循环，不存在真正的多线程并发问题（GIL）。`await` 点是唯一的切换机会，I/O 等待时让出 CPU。

**潜在的并发问题在哪里？**

全局变量！如果某个模块级变量在请求间共享，就可能有并发问题。我们检查了以下几个：

1. `calculator = BaziCalculator()`（nodes.py 模块级变量）：BaziCalculator 是无状态的，每次 `calculate` 方法调用都是纯函数，并发安全。
2. `retriever = KnowledgeRetriever()`：向量检索是只读的（读 ChromaDB），并发安全。
3. `llm = DashScopeLLM()`：每次 `acall` 都是独立的 HTTP 请求，并发安全。
4. `reranker._call_count`（Reranker 的计数器）：**有并发问题**！用 `threading.Lock` 保护。"

---

### 3.2 Reranker 计数器的并发控制

"Reranker 的调用计数器是全局共享状态，需要保护：

```python
class Reranker:
    def __init__(self):
        self._call_count = 0
        self._window_start_time = time.time()
        self._lock = threading.Lock()

    def _check_rate_limit(self) -> bool:
        with self._lock:  # 临界区：读 + 写 是原子的
            current_time = time.time()
            if current_time - self._window_start_time > 5 * 3600:
                self._window_start_time = current_time
                self._call_count = 0
            if self._call_count >= self.calls_per_5_hours:
                return False
            self._call_count += 1
            return True
```

`with self._lock` 保证了'检查 + 自增'是原子的，不会出现两个请求都通过检查但总数超限的情况（TOCTOU 问题，Time-of-check to time-of-use）。

**为什么用 threading.Lock 而不是 asyncio.Lock？**

因为这段代码是同步的（不是 async 函数），asyncio.Lock 只能在 async context 里使用。而 threading.Lock 可以在同步代码里直接用，也可以从异步代码里调用同步函数间接使用，通用性更强。

如果 `_check_rate_limit` 是 async 函数，就应该用 `asyncio.Lock`，代价是调用方要 await。"

---

### 3.3 内存限流计数器的并发

"限流中间件的内存计数器也有并发问题：

```python
self._memory_counters: dict = defaultdict(list)

def _check_memory(self, key: str, limit: int, window: int):
    now = time.time()
    self._memory_counters[key] = [
        t for t in self._memory_counters[key] if now - t < window
    ]
    current_count = len(self._memory_counters[key])
    ...
    self._memory_counters[key].append(now)
```

**asyncio 单线程保证**：由于 asyncio 是单线程，`dispatch` 函数中的这段代码不会被其他协程中断（没有 `await` 点），所以没有并发问题。

但如果把这个代码放到多线程环境（比如 ThreadPoolExecutor），就会有 race condition。这是 asyncio 应用中常见的'假并发'安全——代码看起来有并发问题，但实际上 asyncio 的单线程模型保证了它的安全。"

---

### 3.4 会话的并发访问

"同一个 `conversation_id` 的会话可能被并发访问吗？

**场景**：用户在两个标签页打开了同一个对话，同时发送消息。

**当前行为**：两个请求会分别加载 session，分别修改，分别保存。如果几乎同时进来，可能出现'最后写入者获胜'（Last Write Wins）——第二个请求加载的是旧 session（没有第一个请求的 assistant 消息），保存后会覆盖第一个请求的结果，导致第一个请求的对话记录丢失。

**我们的处置**：没有做会话锁，接受这种冲突。理由：
1. 命理应用不是协作编辑场景，同一用户同时在两个标签发消息的概率很低
2. 即使冲突，用户会发现上一条回复消失，重新问一次即可，没有数据损坏

**如果要解决**，可以用 Redis 的 SETNX 实现会话级分布式锁：

```python
lock_key = f"session_lock:{conversation_id}"
if redis.set(lock_key, "1", nx=True, ex=10):  # 10秒锁
    try:
        # 处理请求
    finally:
        redis.delete(lock_key)  # 释放锁
else:
    return {"error": "会话正在被处理，请稍后重试"}
```

但这会引入额外的延迟（加锁/解锁操作），在并发冲突概率极低的场景不值得。"

---

### 3.5 BM25 索引的并发安全

"BM25 索引在初始化时构建，之后只读。`BM25Retriever.search()` 不修改索引，并发安全。

如果要支持实时增量更新索引（比如用户上传新古籍），就需要保护写操作：

```python
class BM25Retriever:
    def __init__(self):
        self._index_lock = asyncio.Lock()  # 或 threading.RLock

    async def add_documents(self, docs):
        async with self._index_lock:
            # 重建索引
            self._rebuild_index(self._all_docs + docs)

    def search(self, query, top_k):
        # 只读，不需要锁
        return self._search_in_current_index(query, top_k)
```

当前版本不支持在线更新，所以不存在写并发问题。这是一个有意识的简化。"

---

## 四、数据一致性的面试延伸话题

### 4.1 CAP 定理的应用理解

"面试可能问：'你的系统在 CAP 定理里是 CP 还是 AP？'

诚实回答：**AP 偏向**。

- 我们优先保证可用性（A）：Redis 挂了，继续服务；文件写失败，不中断请求
- 我们放弃了一部分一致性（C）：双写存在短暂不一致窗口，会话数据可能丢失
- 分区容忍性（P）：单机部署，P 不是主要考量（网络分区不影响单机）

对于命理分析这种非关键业务，AP 是正确选择。如果是金融系统，需要 CP（比如 Zookeeper），宁可服务不可用，也不能有数据不一致。"

---

### 4.2 幂等性设计

"面试可能问：'你的 API 是幂等的吗？'

**GET/DELETE 请求**：天然幂等。

**POST /api/v1/bazi/analyze**：

如果提交相同出生信息，由于有缓存，第二次请求会命中 Redis 缓存，返回第一次的结果。从用户角度看是幂等的（相同输入，相同输出）。

但从系统状态看不是严格幂等——第一次请求会创建会话、写 Redis、写文件；第二次虽然结果相同，但可能更新会话的 message_count 等元数据。

**POST /api/v1/chat/chat**：

不幂等。每次请求都会在会话里添加新消息，相同的请求重复发两次，消息列表里会有两条用户消息和两条 assistant 消息。

如果要实现幂等（比如网络重试时不重复添加消息），可以在请求体里加 `request_id`，服务端检查这个 `request_id` 是否已经处理过。但我们目前没有实现，是一个已知的 limitation。"

---

### 4.3 最终一致性的实际体现

"一个具体的最终一致性场景：

1. 用户发请求，会话数据写入 Redis（成功）和文件（成功）
2. Redis 突然宕机，Redis 里的数据丢失
3. Redis 重启后为空
4. 用户下次请求，从 Redis 读（miss）→ 从文件读（成功）→ 加载了旧会话
5. 请求处理完，重新写入 Redis

从步骤 2 到步骤 5，Redis 和文件的状态是一致的（因为文件有最新数据）。这是通过'Redis 重启后缓存失效，从文件重新加载'实现的最终一致。

**注意**：步骤 2 到 5 之间如果还有其他请求，这些请求看到的是文件里的旧数据，可能会在旧数据基础上添加新消息，然后覆盖写。这是最终一致性场景下的一种竞争，在我们的应用中是可接受的。"

---

## 五、容灾追问与应答

**Q: 如果知识库（ChromaDB）文件损坏，怎么恢复？**

"ChromaDB 的数据在 `src/chroma_db/` 目录。如果损坏：

1. 删除损坏的 chroma_db 目录
2. 重启应用，触发知识库重建脚本
3. 脚本从 `src/core/` 的原始 JSON 数据文件重新 embedding 并构建索引

BM25 索引也有类似的机制，从原始文档重建。

这是'以原始数据为 source of truth'的设计，存储的只是索引，原始数据永远是可信的。"

**Q: 如果 DashScope API Key 失效怎么办？**

"API Key 失效后：
- Embedding 调用会返回 401 错误，ChromaDB 查询的 query embedding 生成失败
- LLM 调用返回 401，llm_generate 节点失败

降级路径：向量检索失败 → 退化到纯 BM25 检索（如果配置了）；LLM 失败 → 返回结构化排盘数据（无 AI 解读）。

监控告警：需要监控 DashScope API 的调用成功率，一旦出现大量 401/429，立即告警，运维更换 API Key 或者等配额重置。"

**Q: 多实例部署时，BM25 索引如何同步？**

"目前 BM25 索引是进程内存里的对象（加载自文件），多实例各自独立加载。如果知识库更新（新增古籍），需要滚动重启所有实例，让它们重新加载新索引。

这是一个典型的'配置分发'问题。更好的方案是把 BM25 索引也存到共享存储（如 Redis 或 NFS），实例动态加载。但对于我们当前的规模，重启重建完全够用。"
