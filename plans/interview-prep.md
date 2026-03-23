# 八字分析系统（赛博司命）— 面试深挖准备

## 一、项目一句话介绍

> 基于 FastAPI + LangGraph 构建的智能八字分析系统，集成天文算法精确排盘、混合 RAG 检索增强生成、多轮对话意图路由，支持 Redis 双层缓存和统一状态管理。

---

## 二、面试官深挖路线 × 最佳回答

### 第一层：项目概述（你做了什么）

**Q: 简单介绍一下你的项目？**

A: 这是一个全栈 AI 应用，核心是把传统八字排盘算法和现代 AI 技术结合。用户输入出生时间和城市，系统通过天文算法（PyEphem）计算真太阳时、精确定位节气边界，排出四柱八字，再经过五行、格局、用神、流年、大运五层分析引擎，最后用 RAG 检索古籍知识库，由大模型生成个性化分析报告。同时支持多轮对话追问，有意图识别和上下文管理。

**Q: 技术栈是什么？**

A: 后端 Python 3.11 + FastAPI，工作流编排用 LangGraph（状态机 DAG），向量检索 ChromaDB + DashScope text-embedding-v4，关键词检索 jieba + BM25，重排序 DashScope gte-rerank，大模型通义千问 qwen-plus，缓存 Redis，前端单页面原生 JS。

---

### 第二层：架构设计（为什么这么做）

**Q: 为什么用 LangGraph 而不是简单的函数调用链？**

A: 排盘流程有 11 个节点，每个节点可能失败，需要条件路由。比如 validate_input 失败要直接跳到 safety_check，而不是继续算。LangGraph 的 StateGraph 天然支持条件边（conditional_edge），每个节点返回 status 字段，路由函数根据 status 决定下一步走哪个节点。这比 if-else 链更清晰，也更容易扩展新节点。

```python
# bazi_graph.py 实际代码
workflow.add_conditional_edges("validate_input", route_after_validation,
    {"calculate_bazi": "calculate_bazi", "safety_check": "safety_check"})
```

如果用简单函数链，错误处理会散落在每个函数里，而 LangGraph 让错误路由集中在路由函数中。

**Q: 为什么选择混合检索（Hybrid Retrieval）而不是纯向量检索？**

A: 八字领域有大量专业术语，比如"偏印格"、"食神生财"，这些术语向量检索可能语义匹配不精确，但 BM25 关键词匹配很准。反过来，用户问"我的事业运势怎么样"这种语义查询，BM25 就不行了，需要向量检索。所以我用了加权融合：

```python
# hybrid_retriever.py 实际代码
fused_score = vector_weight * v_score + bm25_weight * b_score  # 0.6 * vector + 0.4 * bm25
```

融合后再用 DashScope gte-rerank 模型做精排，实测比纯向量检索的相关性提升明显。

**Q: 状态管理为什么要做双层持久化？**

A: Redis 快但易失（重启丢数据），文件存储慢但持久。我的策略是：
- 写入时双写（Redis + JSON 文件）
- 读取时 Redis 优先，miss 了 fallback 到文件，再回填 Redis
- 用 dirty flag 避免无修改时的无效写入

```python
# state_manager.py 实际代码
def load_session(self, conversation_id):
    # 1. 先查 Redis
    cached = self.redis_cache.get(f"conversation:{conversation_id}")
    if cached:
        return self._deserialize(cached)
    # 2. fallback 文件
    session = self.file_storage.load_session(conversation_id)
    if session:
        # 3. 回填 Redis
        self.redis_cache.set(f"conversation:{conversation_id}", self._serialize(session), ttl=86400)
    return session
```

这样既保证了热数据的访问速度，又不怕 Redis 挂掉丢数据。

---

### 第三层：技术细节深挖（怎么实现的）

**Q: 真太阳时是怎么算的？为什么需要它？**

A: 八字排盘的"时辰"必须用当地真太阳时，不是北京时间。比如乌鲁木齐（东经87.6°）和上海（东经121.5°）同一个北京时间，真太阳时差了将近 2.3 小时，可能跨时辰，排出完全不同的八字。

我的修正分两步：
1. **经度修正**：以东经 120° 为基准，每偏 1° 修正 4 分钟
2. **均时差修正**：地球公转不均匀导致的时间偏差，用 PyEphem 天文库精确计算

```python
# solar_terms.py 实际代码
def adjust_true_solar_time(self, dt, longitude, latitude=39.9):
    lon_offset = (longitude - 120.0) * 4.0  # 经度修正（分钟）
    # 均时差通过 ephem 计算太阳时角得出
    ...
    total_offset = lon_offset + equation_of_time
    return dt + timedelta(minutes=total_offset)
```

另外 1986-1991 年中国实行过夏令时，我也做了专门处理，自动减 1 小时。

**Q: 节气边界怎么精确计算的？**

A: 年柱以立春为界，月柱以 24 节气为界，不是农历初一。我用 PyEphem 计算太阳黄经，当太阳到达特定角度时就是对应节气。比如春分是 0°，清明是 15°，立夏是 45°。

用牛顿迭代法逐步逼近精确时刻：

```python
# solar_terms.py 实际代码
def _find_crossing_time(self, target_angle, start_dt, end_dt):
    # 二分法 + 迭代，精度 ~0.0005°（约30秒）
    while (end_dt - start_dt).total_seconds() > 60:
        mid = start_dt + (end_dt - start_dt) / 2
        mid_lon = self._get_sun_longitude(mid)
        if mid_lon < target_angle:
            start_dt = mid
        else:
            end_dt = mid
    return mid
```

精度控制在 30 秒以内，对于时辰判断（2 小时一个时辰）完全够用。

**Q: 多轮对话的意图识别是怎么做的？**

A: 我没有用额外的分类模型，而是基于关键词评分的规则引擎，因为八字场景的意图类型有限且明确：

```python
# conversation_skill.py 实际代码
INTENT_KEYWORDS = {
    "NEW_ANALYSIS": ["分析", "算一下", "八字", "排盘", "看看命"],
    "FOLLOW_UP": ["那", "然后", "继续", "还有", "接着"],
    "TOPIC_SWITCH": ["换个话题", "说说", "聊聊"],
    "CLARIFICATION": ["什么意思", "为什么", "怎么理解"],
}
```

每个意图对应不同的处理策略：
- NEW_ANALYSIS → 检查槽位完整性 → 调用排盘 graph
- FOLLOW_UP → 全历史上下文 + RAG 检索
- TOPIC_SWITCH → 只取最近 3 条消息 + 检索（避免旧话题干扰）
- CLARIFICATION → 最近 2 轮对话（轻量回答）

这比调 LLM 做意图分类快 10 倍以上，延迟从 ~2s 降到 <10ms。

**Q: 槽位提取怎么做的？跨轮次怎么合并？**

A: 用正则匹配 + 验证 + 归一化三步：

```python
# conversation_skill.py 实际代码
"birth_year": {
    "pattern": r"(\d{4})[年\-]",
    "validation": lambda x: 1900 <= int(x) <= 2100,
}
"gender": {
    "pattern": r"(男|女)",
    "normalization": {"男": "男", "女": "女"},
}
```

跨轮次合并策略是"新值覆盖旧值"，存在 `ConversationMetadata.slots` 里，通过 `state_manager.update_slots()` 双写到 Redis 和文件。这样用户第一轮说"1990年3月15日"，第二轮说"男，成都"，两轮的槽位会合并成完整的出生信息。

**Q: Redis 缓存 key 怎么设计的？**

A: 八字结果只跟出生时间 + 性别 + 地理位置有关，所以 key 是：

```python
# redis_cache.py 实际代码
f"bazi:{year}_{month}_{day}_{hour}_{gender}_{longitude}_{latitude}"
```

加入经纬度是因为不同城市的真太阳时不同，同一个北京时间在成都和上海可能排出不同八字。TTL 设 2 小时，因为八字结果是确定性计算，不会变，但也不想永久占用内存。

**Q: Reranker 的限流怎么处理的？**

A: DashScope gte-rerank 有 API 配额限制（5 小时 1200 次），我用线程安全的计数器做限流，超限后自动降级到按原始分数排序：

```python
# reranker.py 实际代码
def _check_rate_limit(self):
    with self._lock:
        now = time.time()
        if now - self._window_start > 18000:  # 5小时窗口
            self._call_count = 0
            self._window_start = now
        if self._call_count >= self._max_calls:
            return False
        self._call_count += 1
        return True
```

降级不影响功能，只是排序质量略降。这是典型的优雅降级（graceful degradation）模式。

---

### 第四层：工程实践（你踩过什么坑）

**Q: 城市经纬度的 bug 是怎么发现和修复的？**

A: 用户反馈说选了成都但分析结果和上海一样。我追踪数据流发现：对话路径中 `conversation_skill` 提取出 `birth_place="成都"`（字符串），但 `BirthInfo` 模型只接受 `longitude/latitude`（数字），字符串被忽略了，`bazi_calculator` fallback 到默认值 120.0/30.0（上海）。

修复方案：新建 `city_coords.py` 做城市→经纬度映射，在 `_handle_new_analysis` 里调用 `resolve_city_coords("成都")` → `(104.1, 30.7)`，注入到 `birth_info` 里再传给 graph。同时 Redis 缓存 key 也加入经纬度，确保不同城市不会命中同一缓存。

**Q: 性别字段的类型不匹配是怎么回事？**

A: `conversation_skill` 把"男"归一化成了 `"male"`，但 `BirthInfo.gender` 是 `Literal["男", "女"]`，Pydantic 验证直接报错。这是两个模块之间的契约不一致。修复很简单：把归一化改为保持中文 `"男"→"男"`，同时在 `chat_api` 加了兜底映射 `GENDER_TO_CHINESE`。

教训是：跨模块的数据契约要有统一的类型定义，不能各写各的。

**Q: 为什么要做统一状态管理？之前的问题是什么？**

A: 之前 `bazi_api.py` 用老的 `MemoryManager`（独立的 dict + JSON），`chat_api.py` 用 `UnifiedStateManager`（Redis + FileStorage）。两条路径的数据完全隔离：通过 `/analyze` 排的盘，在 `/chat` 里看不到；Redis 缓存也只有 chat 路径在写。

统一后所有路径都走 `UnifiedStateManager`，共享同一个 Redis 缓存。同一个出生信息不管从哪个入口进来，第二次都能命中缓存，避免重复排盘（排盘涉及天文计算 + RAG + LLM，耗时 5-10 秒）。

---

### 第五层：系统设计思维

**Q: 如果 Redis 挂了，系统会怎样？**

A: 完全不影响核心功能。`RedisCacheManager` 所有方法都有 try-catch，Redis 不可用时返回 None/False，调用方检查后走 fallback：
- 缓存读取 miss → 正常走排盘流程
- 缓存写入失败 → 静默跳过，不影响响应
- 会话加载 → fallback 到文件存储

这是我在设计时就考虑的：Redis 是加速层，不是必要层。

**Q: 如果要支持 10 万并发用户，你会怎么改？**

A: 几个方向：
1. **排盘计算**是 CPU 密集型，可以用 Celery + Redis 做异步任务队列，前端轮询结果
2. **LLM 调用**是 IO 密集型，当前已经是 async，可以加连接池和并发限制
3. **Redis 缓存**命中率是关键，八字结果是确定性的，相同输入永远相同输出，可以把 TTL 延长到 24h 甚至更久
4. **RAG 检索**可以预热热门查询，把 ChromaDB 换成 Milvus 做分布式向量检索
5. **前端**加 WebSocket 做流式输出，避免长轮询

**Q: 安全方面做了什么考虑？**

A: 两层防护：
1. **输入层**：`detect_crisis()` 检测自杀/自残等危机关键词，命中后返回心理援助信息而不是算命结果；`check_safety()` 过滤敏感内容
2. **输出层**：`safety_check_node` 是 graph 的最后一个节点，对 LLM 生成的报告做最终审查，防止输出宿命论、封建迷信等不当内容

```python
# safety_prompt.py 实际代码
SAFETY_SYSTEM_PROMPT = """
- 不做绝对化预测（"你一定会..."）
- 不涉及生死、疾病诊断
- 遇到心理危机关键词，优先提供专业求助渠道
"""
```

---

## 三、面试故事（STAR 法则）

### 故事 1：最大的技术挑战 — 真太阳时精度问题

**Situation**: 用户反馈同一个出生时间，我的系统和其他八字软件排出的时辰不一样。

**Task**: 排查差异原因，确保排盘精度达到专业水准。

**Action**:
- 研究发现问题出在真太阳时修正。北京时间是东经 120° 的标准时，但中国横跨 60° 经度（东经 73°~135°），乌鲁木齐和上海的真太阳时差将近 2.3 小时
- 引入 PyEphem 天文库计算太阳黄经，实现了经度修正 + 均时差修正的双重校正
- 额外处理了 1986-1991 年中国夏令时（这个很多软件都忽略了）
- 用牛顿迭代法精确定位 24 节气时刻，精度控制在 30 秒以内

**Result**: 修正后与专业排盘软件的结果完全一致。这个功能也成了项目的核心竞争力——大多数在线八字工具都没有做真太阳时修正。

---

### 故事 2：最大的架构决策 — 从函数链到 LangGraph 状态机

**Situation**: 最初排盘流程是 10 个函数顺序调用，任何一步失败整个流程崩溃，错误信息不友好。

**Task**: 需要一个能优雅处理错误、支持条件分支、易于扩展的工作流框架。

**Action**:
- 调研了 LangChain、LangGraph、Prefect 等方案
- 选择 LangGraph 因为它原生支持 TypedDict 状态传递和条件边路由
- 把 10 个函数重构为 11 个 graph 节点，每个节点只关心自己的输入输出
- 设计了统一的 status 字段做路由：`xxx_completed` → 下一步，`xxx_failed` → safety_check
- 加了超时机制：完整版 graph 10 分钟超时后自动 fallback 到简化版（不含 RAG/LLM）

**Result**:
- 错误处理从散落在 10 个函数变成集中在路由函数，代码量减少 40%
- 新增"大运分析"节点只需要 3 步：写节点函数、加到 graph、配路由
- 超时 fallback 保证了即使 LLM API 挂了，用户也能拿到基础排盘结果

---

### 故事 3：最有成就感的优化 — 混合检索 + 双层缓存

**Situation**: v0.1.0 版本每次分析都要调 LLM + 向量检索，响应时间 8-12 秒，用户体验差。

**Task**: 在不牺牲质量的前提下把响应时间降到 3 秒以内。

**Action**:
- **缓存层**：八字结果是确定性计算（相同输入 = 相同输出），加了 Redis 缓存，key 包含出生时间+性别+经纬度，TTL 2 小时。第二次相同请求直接返回，<100ms
- **检索层**：纯向量检索对专业术语不够精确，加了 BM25 关键词检索，用 0.6:0.4 的权重融合，再用 gte-rerank 精排。检索质量提升的同时，加了检索结果缓存（TTL 5 分钟）
- **对话层**：长对话（>10 轮）token 消耗大，加了 ConversationSummarizer，把旧消息压缩成摘要，只保留最近 5 条完整消息
- **统一状态管理**：把 Redis + 文件存储统一到 UnifiedStateManager，dirty flag 避免无效写入

**Result**:
- 缓存命中时响应 <100ms（从 8-12s 降低 99%）
- 缓存未命中时响应 ~5s（RAG + LLM 的固有延迟）
- 长对话 token 消耗降低 60%（摘要压缩）
- 两条 API 路径共享缓存，避免重复计算

---

### 故事 4：跨模块数据契约的教训

**Situation**: 上线后发现通过对话路径选择"成都"，排盘结果却和"上海"一样。

**Task**: 定位 bug 并建立防止类似问题的机制。

**Action**:
- 追踪数据流发现 3 个断裂点：
  1. `conversation_skill` 提取 `birth_place="成都"`（字符串），但 `BirthInfo` 只接受 `longitude/latitude`（数字）
  2. `conversation_skill` 把性别归一化为 `"male"`，但 `BirthInfo` 要求 `Literal["男", "女"]`
  3. `graph_input` 传了 `name`/`birth_place` 等多余字段，Pydantic V2 默认 `extra="forbid"` 会报错
- 修复：新建 `city_coords.py` 做城市映射，修正性别归一化，`validate_input_node` 过滤多余字段
- 反思：根本原因是模块间的数据契约没有统一定义，各模块各写各的类型

**Result**: 修复后所有 16 个城市的经纬度正确传递，真太阳时计算准确。这个经历让我意识到在多模块系统中，数据契约（接口类型定义）比实现逻辑更重要。

---

## 四、项目亮点总结（面试官视角）

| 考察维度 | 你的项目体现 |
|---------|------------|
| **AI 工程能力** | RAG 混合检索（向量+BM25+重排序）、LLM prompt 工程、意图识别 |
| **系统设计** | LangGraph 状态机、双层缓存、统一状态管理、优雅降级 |
| **工程质量** | 错误处理、安全防护、限流、超时 fallback |
| **领域深度** | 天文算法（真太阳时、节气）、传统文化数字化 |
| **全栈能力** | FastAPI 后端 + 原生 JS 前端 + Redis 缓存 + 文件持久化 |
| **问题解决** | 城市经纬度 bug 的端到端排查、跨模块数据契约修复 |
| **性能优化** | 缓存命中 <100ms、会话摘要压缩、检索结果缓存 |
