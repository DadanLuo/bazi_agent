# 面试逐字稿 · 第三部分：Agent 设计 & RAG 检索

---

## 一、Agent 架构设计

### 1.1 为什么要做 Agent 抽象层？

"在 v0.1.0 的时候，八字分析的逻辑全都写在 `chat_api.py` 里，一个函数几百行，里面混着意图识别、槽位提取、排盘调用、追问处理。这就是典型的'大泥球'问题——扩展性极差。

如果我要加一个塔罗占卜功能，我不能直接复用任何代码，因为业务逻辑和框架胶水代码完全耦合在一起。

所以在 v0.2.0 我引入了 **BaseAgent 抽象层**，把每个功能域封装成独立的 Agent，它们共享相同的接口契约：

```python
class BaseAgent(ABC):
    @property
    @abstractmethod
    def agent_id(self) -> str: ...

    @property
    @abstractmethod
    def slot_schema(self) -> SlotSchema: ...

    @property
    @abstractmethod
    def intent_keywords(self) -> Dict[str, List[str]]: ...

    @abstractmethod
    async def handle_analysis(self, session, slots, mode) -> Dict: ...

    @abstractmethod
    async def handle_followup(self, session, query) -> str: ...
```

现在加一个新的 Agent（比如 HealthAgent），只需要：
1. 继承 BaseAgent
2. 定义自己的槽位 schema
3. 实现 handle_analysis 和 handle_followup
4. 向 AgentRegistry 注册

框架代码不需要改动。"

---

### 1.2 AgentRegistry（插件式注册）

"AgentRegistry 是一个简单的字典注册表：

```python
class AgentRegistry:
    _registry: Dict[str, BaseAgent] = {}

    @classmethod
    def register(cls, agent: BaseAgent):
        cls._registry[agent.agent_id] = agent

    @classmethod
    def get(cls, agent_id: str) -> Optional[BaseAgent]:
        return cls._registry.get(agent_id)
```

在应用启动时（lifespan 函数里）注册所有 Agent：

```python
AgentRegistry.register(BaziAgent())
AgentRegistry.register(TarotAgent())
```

路由层通过 agent_id 获取对应的 Agent 实例：

```python
agent = AgentRegistry.get("tarot")
result = await agent.handle_analysis(session, slots)
```

这是**插件模式**的经典实现，注册表解耦了路由层和具体 Agent 实现。"

---

### 1.3 BaziAgent 的槽位系统

"BaziAgent 定义了精细的槽位 schema：

```python
SlotSchema({
    'birth_year':  {'required': True,  'pattern': r'(\d{4})[年\-]',          'keywords': ['出生', '年']},
    'birth_month': {'required': True,  'pattern': r'(\d{1,2})[月]',           'keywords': ['月']},
    'birth_day':   {'required': True,  'pattern': r'(\d{1,2})[日号]',         'keywords': ['日', '号']},
    'gender':      {'required': True,  'pattern': r'(男|女)',                  'keywords': ['性别', '男', '女']},
    'birth_hour':  {'required': False, 'pattern': r'(\d{1,2})(?:点|时)',       'keywords': ['点', '时']},
    'birth_place': {'required': False, 'pattern': r'(?:出生地|在)([\u4e00-\u9fa5]{2,})', 'keywords': ['出生地']},
})
```

每个槽位有三个属性：
- `required`：是否必填
- `pattern`：正则提取规则
- `keywords`：语义关键词（用于意图检测）

槽位提取使用正则扫描用户输入，命中的值存入会话状态。多轮对话中，槽位是**累积填充**的——用户第一轮说了年份，第二轮说了月日，第三轮才给性别，系统会合并所有轮次的槽位，不会重置。

这比每次重新解析用户的完整输入更鲁棒，也避免了'用户第二轮没提年份就认为没有年份信息'的错误。"

---

### 1.4 UnifiedSession 数据契约

"Agent 的方法都接收一个 `UnifiedSession` 对象，这是整个会话的统一数据视图。

```python
class UnifiedSession(BaseModel):
    metadata: SessionMetadata      # 会话元数据
    messages: List[ChatMessage]    # 消息历史
    bazi_cache: Optional[BaziCacheData]   # 八字分析缓存
    tarot_cache: Optional[TarotCacheData] # 塔罗分析缓存
    analysis_state: Dict[str, Any]         # LangGraph 分析状态
```

它能做两件事：

**第一，生成 LangGraph 的 state dict**：

```python
def to_graph_state(self) -> Dict[str, Any]:
    return {
        "conversation_id": self.metadata.conversation_id,
        "messages": self.get_openai_format(),
        "context_strategy": self.metadata.context_strategy,
        ...
    }
```

**第二，从 LangGraph 结果回填**：

```python
def absorb_graph_result(self, graph_output: Dict[str, Any]) -> None:
    for key in ANALYSIS_STATE_KEYS:
        if key in graph_output:
            self.analysis_state[key] = graph_output[key]
    if graph_output.get('bazi_result'):
        self.bazi_cache = BaziCacheData(
            bazi_data=graph_output['bazi_result'],
            analysis_result=graph_output.get('final_report', {}),
        )
```

这解决了一个经典问题：**LangGraph 的 TypedDict state 和持久化用的 Pydantic model 是两套不同的数据结构**，互相转换很容易出 bug。UnifiedSession 作为桥梁，把两套系统的数据转换封装在内部，外部调用方不需要关心这个细节。"

---

## 二、RAG 检索系统详解

### 2.1 知识库构建

"知识库来自《渊海子平》《三命通会》《神峰通考》等传统命理古籍，经过以下处理：

1. **文本提取**：从原始文档中提取章节文本
2. **分块（Chunking）**：按段落切分，每块约 200-500 字，保证语义完整性
3. **向量化**：用 DashScope text-embedding-v4 生成 1024 维向量
4. **存入 ChromaDB**：向量 + 原文 + 元数据（书名、章节）一起存入
5. **BM25 索引构建**：用 jieba 分词后建立 BM25 倒排索引

分块策略的关键是**不要在句子中间切**，要在段落边界切。我们用正则识别段落边界，保证每个 chunk 是一个完整的语义单元，既不太短（太短会丢失上下文），也不太长（太长会稀释相关性）。"

---

### 2.2 向量检索（ChromaDB）

"向量检索的流程：

**检索阶段**：
```python
results = collection.query(
    query_embeddings=[query_embedding],
    n_results=top_k * candidate_multiplier,  # 召回候选集（放大4倍）
    include=["documents", "metadatas", "distances"]
)
```

为什么要 `* candidate_multiplier`？因为后续还有 Rerank 步骤，我们需要足够多的候选集让 Rerank 有材料选择。如果直接 top_k=5，Rerank 只能在 5 个里选，效果不如先召回 20 个再 Rerank。

**HNSW 索引**：ChromaDB 默认用 HNSW（Hierarchical Navigable Small World）索引做近似最近邻搜索。HNSW 的核心思想是建立多层导航图，高层图节点稀疏（用于快速导航），低层图节点密集（用于精确搜索）。查询时从高层图入口节点出发，逐层下沉找到近邻，时间复杂度是 O(log n)。

v0.2.0 中我们调整了 HNSW 的参数：
- `M=16`：每个节点的最大连接数，越大准确性越高，内存越多
- `ef_construction=100`：构建时搜索深度
- `ef_search=50`：查询时搜索深度

这些参数让检索速度提升了约 30%，同时保持了 95% 以上的 recall@10。"

---

### 2.3 BM25 检索

"BM25 是基于词频（TF）和逆文档频率（IDF）的关键词检索算法，公式是：

```
BM25(q, d) = Σ IDF(qi) * (TF(qi, d) * (k1 + 1)) / (TF(qi, d) + k1 * (1 - b + b * |d| / avgdl))
```

我们使用的参数：
- `k1 = 1.5`：词频饱和系数，控制词频对分数的边际效益
- `b = 0.75`：长度归一化系数，控制文档长度对分数的影响

在命理古籍检索场景：
- k1 取 1.5 是标准值，适合大多数场景
- b 取 0.75 意味着文档长度对分数有较大影响，长文档的词频分数会被惩罚

BM25 检索前需要对查询和文档做 jieba 分词，命理术语（比如'甲子年'、'正印格'）是复合词，jieba 的专有词典可以保证它们不被拆散。"

---

### 2.4 混合检索融合算法

"混合检索的核心是分数融合，步骤：

**第一步，各自归一化**：

```python
def _normalize_scores(self, scores: List[float]) -> List[float]:
    min_score = min(scores)
    max_score = max(scores)
    if max_score == min_score:
        return [1.0] * len(scores)
    return [(s - min_score) / (max_score - min_score) for s in scores]
```

向量相似度和 BM25 分数的量纲不同（向量是 0-1 的余弦相似度，BM25 是无界正数），直接加权会导致一方主导另一方，所以先各自归一化到 [0, 1]。

**第二步，建立文档 ID 映射**：

```python
vector_docs = {r['id']: r for r in vector_results}
bm25_docs = {r['id']: r for r in bm25_results}
all_ids = set(vector_docs.keys()) | set(bm25_docs.keys())
```

用文档 ID 作为合并键，对于只在一个检索器中出现的文档，另一个检索器的分数为 0。

**第三步，加权融合**：

```python
fused_score = (
    self.vector_weight * vector_norm +  # 0.6
    self.bm25_weight * bm25_norm        # 0.4
)
```

向量检索权重 0.6 > BM25 权重 0.4，这是根据古籍检索场景调优的结果。古籍语言风格固定，语义相似性比关键词匹配更重要，所以向量权重更高。

**第四步，排序取 top 候选**：

```python
fused_results.sort(key=lambda x: x['fused_score'], reverse=True)
return fused_results[:top_k * candidate_multiplier]  # 给 Rerank 的候选集
```"

---

### 2.5 Rerank 重排序（限流设计）

"重排序是 RAG 二阶段架构的第二阶段，调用 DashScope gte-rerank 模型对候选文档重新精排。

**为什么要 Rerank**？向量检索的余弦相似度和 BM25 分数都是一维打分，缺乏 query-document 的交叉注意力。Rerank 模型会把 query 和每个 document 一起输入，做 cross-encoder 计算，能捕捉更细粒度的相关性。代价是计算量大，不适合作为召回阶段。

**限流实现**：

Rerank API 有调用次数限制（1200次/5小时），我们用滑动窗口计数器控制：

```python
def _check_rate_limit(self) -> bool:
    with self._lock:
        current_time = time.time()
        # 5小时窗口滚动
        if current_time - self._window_start_time > 5 * 3600:
            self._window_start_time = current_time
            self._call_count = 0
        if self._call_count >= self.calls_per_5_hours:
            return False
        self._call_count += 1
        return True
```

注意这里用 `threading.Lock()` 保护计数器，因为这是进程级共享资源，多个并发请求可能同时读写 `_call_count`。

**降级策略**：超限时降级到 `_fallback_sort`，按融合分数直接排序，不调用 Rerank API：

```python
if not self.api_key or not self._check_rate_limit():
    return self._fallback_sort(documents, top_k)
```

降级对用户无感知，只是 Rerank 精度略降，而不是报错。"

---

### 2.6 四种检索模式

"我们支持 4 种检索模式，通过配置切换：

```python
class RetrievalMode(str, Enum):
    VECTOR_ONLY = "vector_only"     # 仅向量，快但不精准
    BM25_ONLY = "bm25_only"         # 仅BM25，关键词精准
    HYBRID = "hybrid"               # 混合无Rerank，平衡
    HYBRID_RERANK = "hybrid_rerank" # 混合+Rerank，最精准（默认）
```

为什么要支持多种模式？

- **测试环境**：没有 DashScope API Key 时，用 `bm25_only` 可以跑通流程
- **性能优化**：Rerank 每次调用约需要 1-2 秒，如果响应时间要求很严格，可以降级到 `hybrid`
- **成本控制**：Rerank API 按调用收费，有配额限制，高峰期可以临时切到 `hybrid`

自动策略选择逻辑：

```python
retrieval_mode = RAGConfigManager.get_retrieval_mode()
```

读取配置文件的 `retrieval_mode` 字段，不需要改代码，改配置文件重启即生效。"

---

### 2.7 Prompt 工程

"Prompt 管理用了 PromptRegistry 模式，把所有 prompt 模板统一注册：

```python
class PromptRegistry:
    _templates: Dict[str, str] = {}

    @classmethod
    def render(cls, name: str, **kwargs) -> str:
        template = cls._templates.get(name, "")
        return template.format(**kwargs)
```

为什么不直接把 prompt 写在代码里？

**第一，可迭代**。Prompt 调优是高频操作，放在模板文件里改模板不需要改代码、不需要走测试流程。

**第二，可版本化**。模板文件在 git 里，每次 prompt 变更都有提交记录，方便回滚。

**第三，解耦 Agent 逻辑和语言表达**。BaziAgent 调用 `PromptRegistry.render("follow_up", context=..., query=...)`，不需要知道 prompt 的具体内容。

我们有几类模板：
- `system_prompts/`：系统提示词，定义角色和约束
- `task_prompts/`：任务提示词，定义具体任务格式
- `few_shot_examples/`：少样本示例，提升输出质量

BAZI_CONSTRAINTS 是注入每个 prompt 的约束字符串，确保 LLM 不会给出不当的建议（比如关于健康、投资的笃定性预测）。"

---

## 三、安全设计

### 3.1 内容安全

"我们实现了两层内容安全检查：

**危机检测**（在安全检查之前）：

```python
crisis_check = detect_crisis(input_data.query)
if crisis_check.get('needs_intervention'):
    return ChatResponse(
        data={
            "response": "我注意到您可能正在经历一些困难...",
            "crisis_intervention": True
        }
    )
```

检测自杀、自残相关的关键词，触发后立即返回心理援助信息，不继续走分析流程。这是产品层面的伦理要求，命理类应用的用户可能处于情绪低谷。

**敏感内容过滤**：

```python
safety_check = check_safety(input_data.query)
if not safety_check.get('is_safe'):
    return ChatResponse(success=False, message="输入包含敏感内容，无法处理")
```

过滤辱骂、政治敏感等内容，在路由层面就拦截，不进入 Agent 处理流程。

**LLM 约束（BAZI_CONSTRAINTS）**：在注入给 LLM 的 prompt 里加上行为约束，防止 LLM 生成确定性的投资建议、医疗建议等可能造成伤害的内容。这是最后一道防线。"

---

## 四、RAG 常见追问与应答

**Q: Embedding 向量的维度是多少？为什么选这个维度？**

"DashScope text-embedding-v4 默认输出 1024 维向量。维度选择是 accuracy vs. memory 的 trade-off：
- 维度太低（如 128 维），语义信息损失，相似度计算不准确
- 维度太高（如 3072 维），内存占用大，计算慢，而且有'维度灾难'问题

1024 维是目前主流 embedding 模型的标准配置，在中文语义任务上效果较好。ChromaDB 存储 1 万个 1024 维向量大约需要 40MB 内存，完全可接受。"

**Q: RAG 检索的 precision 和 recall 你怎么评估？**

"我们用人工构建的测试集评估，从古籍中选取典型段落，构造相应的查询，计算 top-5 的命中率。

精确匹配（exact match）不适合用于评估，因为古籍语言灵活，'甲木日主'和'甲日主'在语义上等价。我们用'语义相关'作为判断标准——面试前测试时，混合检索+Rerank 的 recall@5 大约在 85% 左右，比纯向量检索（约 72%）有明显提升。

这个评估不是严格的 benchmark，但能说明混合检索的效果优于单一检索。"

**Q: 如果知识库很大（比如 100 万个 chunk），ChromaDB 还够用吗？**

"ChromaDB 在百万量级会有明显的检索延迟，因为它是单机的。如果要做到这个规模，需要换成分布式向量数据库，比如 Milvus 或者 Qdrant。

但对我们当前的场景（古籍语料库，几万个 chunk），ChromaDB 完全够用，而且零运维成本。这是一个典型的'根据规模选工具'的决策，不是技术问题，是 engineering judgment 问题。"

**Q: BM25 索引存在哪里？重启会丢失吗？**

"BM25 索引持久化在 `data/bm25_index/` 目录，JSON 格式序列化存储。启动时会检查是否有已有索引，有就直接加载，没有才重新构建。构建一次（几万条文档）大约需要 10-20 秒，之后每次启动加载只需要几百毫秒。"

**Q: 检索结果怎么注入 prompt，有什么格式要求？**

"检索结果通过 `retriever.format_context(docs, max_length=2000)` 格式化成结构化文本块，大致格式是：

```
【古籍参考】
来源：《渊海子平》第三章
内容：甲木生于寅月，得地得令，根深叶茂...

来源：《三命通会》
内容：正印格者，月令正印透干...
```

放入 prompt 的 `知识背景` 部分，LLM 在生成解读时会优先参考这些古籍原文，而不是凭'想象'生成。max_length=2000 是经验值，保证知识上下文不超过总 prompt token 预算的 30%。"
