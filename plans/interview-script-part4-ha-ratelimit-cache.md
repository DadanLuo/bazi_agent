# 面试逐字稿 · 第四部分：高可用 & 限流 & 超时 & 缓存

---

## 一、高可用设计总览

"高可用的本质是：**在部分组件失效时，系统仍然能给用户提供有意义的服务**。

我们的系统有几个可能失效的外部依赖：
1. Redis 连接失败
2. DashScope LLM API 超时/限流
3. DashScope Rerank API 超时/限流
4. ChromaDB 向量检索失败

对每一种失效，我们都设计了对应的降级策略，形成一个故障降级矩阵：

| 组件 | 失效场景 | 降级策略 | 用户感知 |
|------|----------|----------|----------|
| Redis | 连接失败 | 降级到文件存储 | 无感知 |
| Redis | 连接失败 | 限流降级到内存计数 | 无感知（单进程） |
| LLM API | 超时/失败 | 返回结构化排盘数据 | 无 AI 解读文字 |
| Rerank API | 超限 | 降级到融合分数排序 | 检索质量略降 |
| ChromaDB | 检索失败 | 跳过 RAG，直接 LLM 生成 | 解读无古籍引用 |

**核心原则**：任何外部依赖的失效，都不应该导致核心功能（八字计算）不可用。

八字计算引擎是纯 Python 实现，没有外部依赖，只要进程存活就一定能算。这是我们高可用的最后防线。"

---

## 二、Redis 高可用设计

### 2.1 连接失败的优雅降级

"Redis 客户端有懒加载机制：

```python
@property
def client(self) -> Optional[Any]:
    if not REDIS_AVAILABLE:
        return None  # redis 包未安装
    if not self.enable_cache:
        return None  # 配置禁用了缓存

    if self._client is None:
        try:
            self._client = redis.Redis(
                host=self.host, port=self.port,
                socket_timeout=5,           # 连接超时5秒
                socket_connect_timeout=5,   # 建立连接超时5秒
                retry_on_timeout=True       # 超时自动重试
            )
            self._client.ping()             # 验证连接
            logger.info("✅ Redis 连接成功")
        except RedisError as e:
            logger.error(f"❌ Redis 连接失败: {e}")
            self._client = None

    return self._client
```

关键在于：**任何地方调用 `self.client`，如果 Redis 不可用就返回 None**，调用方的 `get/set/exists` 方法都会先检查 `if not self.client: return None/False`，所以 Redis 故障对业务逻辑完全透明。

```python
def get(self, key: str) -> Optional[Any]:
    if not self.client:
        return None  # Redis 不可用，直接返回 None（相当于 cache miss）
    try:
        value = self.client.get(key)
        return json.loads(value) if value else None
    except RedisError as e:
        logger.error(f"缓存读取失败: {e}")
        return None
```

业务代码处理 Redis cache miss 的逻辑就是处理 Redis 故障的逻辑，不需要额外的故障处理代码。"

---

### 2.2 Redis 连接配置的工程考量

"Redis 连接配置有几个生产级细节：

**`socket_timeout=5`**：Redis 操作超时 5 秒，防止 Redis 响应慢阻塞请求处理。如果 Redis 在局域网内，通常几毫秒就能响应，5 秒是非常充裕的，触发说明网络有问题。

**`socket_connect_timeout=5`**：建立 TCP 连接的超时，防止 Redis 服务器不可达时长时间阻塞。

**`retry_on_timeout=True`**：超时自动重试一次，应对偶发的网络抖动。

**`decode_responses=True`**：Redis 返回的所有值自动从 bytes 解码成 str，不需要在业务代码里手动 decode。

这些配置确保即使 Redis 偶发抖动，也不会对请求响应时间造成超过 10 秒的影响。"

---

### 2.3 双写策略

"每次保存会话都做 Redis + 文件双写：

```python
def save(self, force: bool = False):
    # 写 Redis
    if redis_cache and redis_cache.client:
        redis_cache.cache_conversation(
            conversation_id=self.conversation_id,
            messages=self.messages,
            ttl=86400  # 24小时
        )
    # 写文件
    file_storage.save_session(self.session_data)
```

双写的读取策略：优先读 Redis，Redis miss 再读文件。这样 Redis 故障不影响历史会话的加载：

```python
# 加载会话
def load_session(self, conversation_id: str) -> Optional[dict]:
    # 优先 Redis
    if redis_cache:
        cached = redis_cache.get_conversation(conversation_id)
        if cached:
            return cached

    # 降级到文件
    return file_storage.load_session(conversation_id)
```

**一个重要的一致性考量**：双写可能出现 Redis 写成功、文件写失败的情况（比如磁盘满了）。这种情况下，Redis 里的数据和文件里的数据不一致，但 Redis TTL 是 24 小时，超时后 Redis 自动清理，下次加载走文件，如果文件也没有，会话丢失。

这是我们有意接受的 trade-off：会话数据不是关键业务数据，丢失最多是用户需要重新排盘，不会造成严重后果。如果需要更强的一致性保证，可以用两阶段提交或者 WAL（Write-Ahead Log），但那样复杂度大幅增加，不值得。"

---

## 三、缓存设计

### 3.1 双层缓存架构

"我们有两层缓存：

**第一层：Redis 分布式缓存（热数据）**

缓存三类数据：
1. 八字分析结果（TTL 2小时）：相同出生信息不重复跑 LangGraph 流程
2. 会话消息（TTL 24小时）：支持跨请求的对话上下文
3. 检索结果（TTL 5分钟）：相同查询不重复调用向量检索和 Rerank

**第二层：cachetools 本地内存缓存（超热数据）**

对于城市经纬度映射这类几乎不变的数据（城市坐标不会变），用 cachetools 的 `TTLCache` 在进程内存里缓存：

```python
from cachetools import TTLCache
_city_cache = TTLCache(maxsize=500, ttl=3600)
```

本地缓存的优势是访问速度极快（纳秒级），不需要网络 RTT；劣势是多进程不共享，重启丢失。适合几乎不变的配置数据。

**层次设计的逻辑**：
- 超热 + 几乎不变 → 本地内存缓存
- 热数据 + 跨请求需要共享 → Redis
- 持久化需求 → 文件存储"

---

### 3.2 八字排盘结果缓存（核心业务缓存）

"八字排盘结果缓存是最重要的缓存，因为它避免了整个 LangGraph 工作流（10+ 节点、3+ 次 API 调用）的重复执行。

**缓存键设计**：

```python
def _build_bazi_cache_key(self, birth_info: Dict[str, Any]) -> str:
    year = birth_info.get('year', 0)
    month = birth_info.get('month', 0)
    day = birth_info.get('day', 0)
    hour = birth_info.get('hour', 0)
    gender = birth_info.get('gender', 'unknown')
    lon = birth_info.get('longitude') or 120.0
    lat = birth_info.get('latitude') or 30.0
    return f"bazi:{year}_{month}_{day}_{hour}_{gender}_{lon}_{lat}"
```

缓存键包含了所有影响排盘结果的输入：年月日时、性别、经纬度。经纬度影响真太阳时修正，不同出生地的同一时刻的八字柱可能不同。

**TTL 设置 2 小时**：理由是八字排盘结果是确定性计算，同样的输入永远得到同样的输出，理论上可以永久缓存。但设置 2 小时是出于两个考虑：第一，避免内存无限增长（用户量大时缓存条目会很多）；第二，如果排盘引擎有 bug 修复，2 小时后会自动刷新到新结果。

**缓存命中时的处理**：

```python
cached = redis_cache.get_bazi_result(birth_info)
if cached and cached.get('bazi_result'):
    logger.info("命中八字 Redis 缓存")
    state_mgr.update_state({
        'bazi_result': cached.get('bazi_result'),
        'bazi_cache': {'bazi_data': cached.get('bazi_result'), ...}
    })
    response = cached.get('llm_response', '')
    return {'response': response, 'bazi_output': bazi_output}
```

命中缓存时，直接返回之前的 LLM 报告文本，连 LLM 调用都省了，响应时间从 10 秒降到 100 毫秒以内。"

---

### 3.3 缓存装饰器

"我们提供了 `@cached` 和 `@async_cached` 装饰器，方便其他函数使用缓存：

```python
@async_cached(ttl=3600, key_prefix='bazi')
async def analyze_bazi(birth_info):
    ...

# 展开等价于：
async def analyze_bazi(birth_info):
    cache_key = f'bazi:analyze_bazi:{str(args)}:{str(sorted(kwargs.items()))}'
    cached_value = cache_manager.get(cache_key)
    if cached_value is not None:
        return cached_value
    result = await original_analyze_bazi(birth_info)
    cache_manager.set(cache_key, result, ttl=3600)
    return result
```

装饰器通过 `@wraps(func)` 保留了原函数的 `__name__`、`__doc__`、`__module__` 等元信息，不影响函数签名和文档。

**注意事项**：缓存键用 `str(args)` 序列化参数，如果参数包含不可 hash 的复杂对象（如自定义类实例），需要确保其 `__str__` 方法能唯一标识对象，否则不同参数可能碰撞到同一个缓存键。"

---

## 四、限流设计详解

### 4.1 固定窗口 vs 滑动窗口

"限流算法有几种：计数器（固定窗口）、滑动窗口日志、滑动窗口计数器、令牌桶、漏桶。

我们用的是**固定窗口计数器**（Redis INCR + EXPIRE），最简单也最高效：

```python
def _check_redis(self, key: str, limit: int, window: int):
    pipe = self.redis.pipeline()  # 原子操作
    pipe.incr(key)
    pipe.ttl(key)
    results = pipe.execute()

    current_count = results[0]
    ttl = results[1]

    if ttl == -1:  # 首次创建 key，设置过期
        self.redis.expire(key, window)
        ttl = window

    return (current_count <= limit, current_count, max(ttl, 1))
```

**固定窗口的缺点**：窗口边界处可能出现'突刺'——比如窗口是 1 分钟，限制 60 次，用户可以在 00:59 打 60 次请求，在 01:00 又打 60 次，2 秒内发出了 120 次请求，超过了设计的 60 次/分钟。

**我们为什么仍然选择固定窗口**：
1. 实现最简单，Redis 单命令原子操作
2. 对于我们的场景（命理分析，不是高频交易），突刺问题的风险可接受
3. 滑动窗口需要 Redis Sorted Set 存每次请求时间戳，内存消耗更大

如果是严格限流场景（比如金融 API），应该用滑动窗口或令牌桶。"

---

### 4.2 内存降级方案

"当 Redis 不可用时，降级到进程内存计数：

```python
def _check_memory(self, key: str, limit: int, window: int):
    now = time.time()
    # 清理过期时间戳（真正的滑动窗口！）
    self._memory_counters[key] = [
        t for t in self._memory_counters[key] if now - t < window
    ]
    current_count = len(self._memory_counters[key])

    if current_count >= limit:
        oldest = self._memory_counters[key][0]
        ttl = int(window - (now - oldest)) + 1
        return (False, current_count, max(ttl, 1))

    self._memory_counters[key].append(now)
    return (True, current_count + 1, window)
```

有趣的是，**内存降级实现的是真正的滑动窗口**（存每次请求时间戳，过期就删），而 Redis 实现的是固定窗口。这是因为：

- Redis 内存宝贵，用 INCR 计数效率高，不能存每次请求的时间戳
- 进程内存相对充裕，存 list of timestamps 可接受，而且滑动窗口实现更精确

降级时用更精确的算法，是一个有意思的设计选择。"

---

### 4.3 Rerank API 限流（业务级限流）

"除了请求级别的 HTTP 限流，我们还有一个业务级别的限流：Rerank API 调用次数限制。

这是因为 DashScope Rerank API 有免费调用额度限制（1200次/5小时），超额会报错，必须在应用层做保护。

```python
class Reranker:
    def __init__(self):
        self.calls_per_5_hours = 1200
        self.cooldown_seconds = 15
        self._call_count = 0
        self._window_start_time = time.time()
        self._lock = threading.Lock()

    def _check_rate_limit(self) -> bool:
        with self._lock:
            current_time = time.time()
            # 5小时窗口滚动重置
            if current_time - self._window_start_time > 5 * 3600:
                self._window_start_time = current_time
                self._call_count = 0
            if self._call_count >= self.calls_per_5_hours:
                return False
            self._call_count += 1
            return True
```

注意：这里用 `threading.Lock` 而不是 `asyncio.Lock`，因为 Reranker 是在异步函数中被调用，但 `_check_rate_limit` 本身是同步的，用 `threading.Lock` 可以同时被同步和异步代码调用。

**提供状态查询接口**：

```python
def get_status(self) -> Dict[str, Any]:
    return {
        'call_count': self._call_count,
        'remaining_calls': max(0, self.calls_per_5_hours - self._call_count),
        'window_elapsed_seconds': time.time() - self._window_start_time,
    }
```

这样运维可以通过 `/health` 接口查看 Rerank 的剩余调用次数，提前预警。"

---

## 五、超时设计

### 5.1 分层超时

"超时设计遵循'外层超时 > 内层超时'原则，防止超时保护失效：

- **HTTP 请求超时（TimeoutMiddleware）**：LLM 路径 120s，普通路径 30s
- **Redis 操作超时（socket_timeout）**：5s
- **LLM API 调用超时（httpx timeout）**：60s（DashScope SDK 内部设置）
- **LangGraph 节点执行没有超时**：依赖上层的请求超时保护

为什么 TimeoutMiddleware 要给 LLM 路径 120s？因为完整的八字分析需要：向量检索（~1s）+ BM25检索（~0.2s）+ Rerank（~1.5s）+ LLM 生成（~5-10s），加上网络 RTT 和处理时间，总共可能需要 20-30 秒。留 120 秒是为了应对 LLM 高峰期响应慢的情况。"

---

### 5.2 超时 + 降级的联动

"超时和降级有一个联动设计：

**场景**：LLM 调用超时（在 LangGraph 的 llm_generate 节点内），但还在 TimeoutMiddleware 的 120s 窗口内。

**处理链路**：
1. `llm.generate_bazi_report()` 抛出 TimeoutError 或者网络异常
2. `llm_generate_node` 的 try/except 捕获，返回 `{"status": "llm_generation_failed"}`
3. `route_after_llm` 路由到 `safety_check`
4. `generate_report_node` 被跳过（或者用兜底文本填充）
5. `safety_check_node` 把现有的结构化数据（四柱、五行、格局）封装成响应

用户看到的是：**没有 AI 解读的命理报告，但有完整的结构化计算结果**。比 504 错误友好得多。

**场景 2**：整个请求超过 120s（极端情况，LLM 无响应）。

**处理链路**：
`asyncio.wait_for` 超时取消协程，返回 504 with trace_id。这是最后防线，不应该触发，如果频繁触发说明需要检查 LLM API 的响应时间。"

---

## 六、异步存储

### 6.1 AsyncStorageManager

"文件写入是 I/O 操作，同步写会阻塞 asyncio 事件循环（即使用了 `open()` 也会）。我们用后台线程做异步写：

```python
class AsyncStorageManager:
    def __init__(self):
        self._write_queue = queue.Queue(maxsize=1000)  # 写入队列
        self._worker_thread = threading.Thread(target=self._write_worker, daemon=True)
        self._batch_size = 10
        self._flush_interval = 5  # 秒

    def save_session_async(self, session_data):
        try:
            self._write_queue.put_nowait(('save', session_data))
        except queue.Full:
            self._sync_save(session_data)  # 队列满了降级同步写
```

**写入线程的批量策略**：

```python
def _write_worker(self):
    batch = []
    while self._running:
        try:
            task = self._write_queue.get(timeout=1)
            batch.append(task)

            if len(batch) >= self._batch_size:
                self._process_batch(batch); batch = []

            if batch and elapsed >= self._flush_interval:
                self._process_batch(batch); batch = []
        except queue.Empty:
            if batch:
                self._process_batch(batch); batch = []
```

**收集 10 个写入任务或者超过 5 秒**，批量处理。批量写入减少了文件 open/close 次数，提升 I/O 效率。

**队列满了降级同步写**：如果写入积压超过 1000 条（说明磁盘极慢或写入量异常），降级同步写，保证数据不丢失，但会阻塞请求。这是最后一道保护。"

---

### 6.2 文件存储的 gzip 压缩

"会话文件用 gzip 压缩存储：

```python
if self.compression:
    with gzip.open(file_path, 'wt', encoding='utf-8') as f:
        json.dump(session_dict, f, ensure_ascii=False, indent=2)
```

压缩比通常在 5:1 到 10:1，典型的会话 JSON 从 20KB 压缩到 2-4KB。

**为什么在这里压缩**：会话文件是读多写少的，而且每次读取要全文加载，压缩后 I/O 量减少，对磁盘和内存都有好处。

**潜在问题**：gzip 读写比普通 JSON 慢约 20-30%，对于频繁读写的场景不合适。我们的会话读写频率不高（每个用户最多每秒 1-2 次），这点开销可以接受。"

---

## 七、高可用追问与应答

**Q: 如果 Redis 挂了，限流还有效吗？**

"有效，但效果会弱化。Redis 挂了后，每个进程用自己的内存计数，如果有 N 个实例，理论上同一 IP 可以发 N 倍的请求。

实际上我们当前是单实例部署，所以内存限流完全等效于 Redis 限流。如果做了水平扩展，多实例的限流需要依赖 Redis 共享计数，这是内存降级方案的局限性，需要在设计文档里注明。"

**Q: 八字缓存的 TTL 为什么是 2 小时，而不是更长？**

"理论上可以更长，因为排盘结果是确定性的，永远不变。但我们考虑了两点：第一，Redis 内存有限，TTL 越长占用内存越多；第二，如果排盘引擎有 bug 修复（比如某个历史时期的节气计算有误差），TTL 长的话老缓存会持续给出错误结果。2 小时是一个工程上的保守选择，平衡了内存效率和数据新鲜度。"

**Q: 如果两个用户同时请求同一个八字，会有并发问题吗？**

"会出现 cache miss 并发，也叫 'cache stampede'。两个请求几乎同时查缓存，都没命中，都触发 LangGraph 工作流，导致重复计算。

目前我们没有做防 stampede 处理，原因是：命理类应用的并发量不高，真正同一出生信息同时请求的概率极低；而且即使两个请求都算了，结果是一样的，只是多花了一倍计算资源。

如果并发量很高，可以用 Redis SETNX 实现分布式锁，或者用 'promise/future' 模式让后来的请求等第一个请求的结果。"

**Q: 文件存储如果磁盘写满了怎么处理？**

"目前没有磁盘空间检查，写满了会抛 `OSError: [Errno 28] No space left on device`，被 `_sync_save` 的 try/except 捕获，返回 `False`，记录错误日志，但不中断请求处理——响应还是会返回给用户，只是没有持久化。

这是一个已知的 limitation，生产上应该加监控告警（磁盘使用率 > 80% 告警，> 90% 清理旧会话文件）。我们目前没有加，属于 MVP 阶段的技术债。"
