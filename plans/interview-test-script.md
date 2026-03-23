# 赛博司命·八字分析 Agent — 面试完整逐字稿

> 版本：v0.2.0 / v0.3.0（进行中）
> 日期：2026-03-22
> 本文档为面试场景下的完整逐字稿，覆盖项目介绍、技术选型、架构设计、LangGraph 工作流、Agent 设计、RAG 检索、高可用、限流、超时、缓存、高容灾、数据一致性、并发控制、测试设计、边界条件、反问环节。

---

# 第一部分：项目介绍与技术选型

## 1.1 开场：自我介绍引出项目

（面试官：请你介绍一下你最近做的项目。）

我在业余时间主导开发了一个叫做"赛博司命"的 AI Agent 项目，核心功能是八字命理的智能分析与多轮对话解读。这个项目从零搭建，经历了从单体脚本到分布式 Agent 架构的完整演化，目前已到 v0.2.0 稳定版，v0.3.0 的标准化重构正在进行中。

选这个业务场景有两个原因：

第一，八字排盘是规则极为复杂、边界条件极多的领域知识计算任务，非常适合检验系统设计能力。比如节气切换的精确判定——立春可能在 2 月 3 日也可能在 2 月 4 日，差一天年柱就完全不同；闰年 2 月 29 日的处理；子时跨日问题——23:00 之后到底算当天还是次日。这些边界条件在测试设计中都有体现。

第二，命理解读需要长上下文的多轮对话，天然考验 Agent 的状态管理、会话隔离和数据一致性设计。用户排完盘之后可能追问十几轮，每一轮都需要引用之前的四柱数据，如果状态管理出问题，LLM 可能会"自行重新排盘"，给出与第一次不一致的结果。这个 bug 我实际遇到过并修复了，后面会详细讲。

从技术角度看，这个项目综合了：领域规则引擎、LangGraph 工作流编排、RAG 知识检索与重排序、Redis 多级缓存、FastAPI 中间件链（限流/超时/日志）、并发控制与会话隔离、统一异常体系与全局错误处理，是一个真实生产级的完整后端系统。

---

## 1.2 技术选型与选型理由

项目整体技术栈：Python 3.11 + FastAPI + LangGraph + ChromaDB + DashScope LLM/Embedding + Redis。

### 1.2.1 FastAPI

选 FastAPI 而不是 Django REST Framework 或 Flask，核心原因是 FastAPI 基于 Starlette，原生支持 async/await。对于 AI 应用，LLM 调用、向量检索、Redis 读写都是 IO 密集型操作，异步能显著提升吞吐量。

具体数据：单次 LLM 调用大约 2-4 秒，如果用同步阻塞模型，10 个并发请求就需要 20-40 秒的总处理时间；用 async/await + asyncio.gather，理论上 10 个并发可以压缩在 4-5 秒完成，吞吐量提升 5-8 倍。

FastAPI 的 Pydantic 集成让我能做严格的数据契约校验。我在 `contracts.py` 中定义了 `UnifiedSession`、`BaziCacheData`、`ApiResponse` 等统一数据模型，所有模块之间的数据传递都经过 Pydantic 校验，这对多模块之间接口稳定性很关键，也让我的边界条件测试能精确验证每个字段的合法范围。

FastAPI 还自动生成 OpenAPI 文档，对于有 10+ 个接口的项目，调试效率很高。我的项目有 `/api/v1/bazi/analyze`、`/api/v1/chat/chat`、`/api/v1/chat/followup`、`/api/v1/chat/export` 等多个端点，Swagger UI 让前端同学可以直接测试。

### 1.2.2 LangGraph

没有选 LangChain 的 AgentExecutor，因为它的控制流不够透明——不知道 Agent 会跑多少步，也很难插入自定义的错误处理和安全检查节点。LangGraph 把工作流建模成有向图（DAG），每个节点是纯函数，边是条件路由，整个执行过程完全可观测、可重放。

对于八字分析这种有明确步骤顺序的任务（输入验证→排盘计算→五行分析→格局判断→用神查找→流年分析→大运分析→RAG 知识检索→LLM 生成→报告组装→安全检查），LangGraph 的 DAG 模型非常合适。每个节点之间有条件路由，任何一步失败都会跳转到 safety_check 节点，不会让错误静默传播。

对于塔罗解读这种需要 LLM 自主决定工具调用顺序的任务，LangGraph 也支持 ReAct 循环——agent_node 和 tool_node 之间形成循环，LLM 自己决定调用哪个工具、调用几次、什么时候结束。两种模式我在同一框架里都实现了，体现了框架选型的前瞻性。

### 1.2.3 ChromaDB

向量数据库选 ChromaDB，原因是可以本地持久化部署，不需要单独的数据库服务器进程，运维成本低。支持 HNSW 索引，在十万量级文档下检索性能足够（P99 < 50ms）。

我为 Retriever 做了抽象层，`KnowledgeRetriever` 封装了 ChromaDB 的连接和查询逻辑，如果未来规模扩大需要迁移到 Qdrant 或 Milvus，只需要替换实现类，上层的 `hybrid_retriever` 和 `reranker` 无需改动。

### 1.2.4 DashScope

LLM 和 Embedding 统一用阿里云 DashScope，好处是在中国大陆网络环境下延迟稳定（P50 约 1.5s，P99 约 4s），text-embedding-v4 对中文命理术语的语义理解比通用英文模型更好。

LLM 层做了 `BaseLLM` 抽象接口，定义了 `call()`、`acall()`、`call_with_tools()`、`acall_with_tools()` 四个方法。`DashScopeLLM` 继承 `BaseLLM` 实现具体调用。如果需要换成 OpenAI 或本地部署的 Ollama，只需要实现对应子类即可，上层业务代码无感知。这是典型的依赖倒置原则（DIP）。

### 1.2.5 Redis

Redis 用于三个场景：

1. **八字计算结果缓存**——同一生日的排盘结果是确定性的（纯函数），计算耗时约 50-100ms，缓存命中后返回 <1ms。以生日+性别为 key，缓存命中率在实际使用中约 15-20%（因为用户生日分布较分散），但对于热门测试日期（如 1990-01-01）命中率接近 100%。

2. **会话状态缓存**——多轮对话的 `UnifiedSession` 对象缓存在 Redis 中，避免每次请求都从文件系统加载。会话 TTL 设为 24 小时，过期后从文件系统重新加载。

3. **限流计数器的分布式存储**——保证多实例部署时限流策略的全局一致性，避免单机内存计数器在横向扩展时失效。使用 Redis INCR + EXPIRE 实现固定窗口计数。

Redis 不可用时系统自动降级到内存计数器和文件存储，不影响核心功能。这是我刻意设计的故障隔离原则：**外部依赖的不可用不能传染到核心业务链路**。

---

## 1.3 常见技术选型追问

**追问：为什么不用 Celery 做异步任务？**

八字分析单次请求耗时约 2-5 秒，主要是 LLM 调用延迟，用户能接受同步等待并在前端显示 loading 状态。引入 Celery 会增加消息队列的运维复杂度（需要部署 Broker 如 RabbitMQ/Redis、Worker 进程、任务状态持久化），以及前端轮询任务状态的额外开发成本。FastAPI 的 async 协程已经足够处理当前的并发量。如果未来需要"后台批量生成报告、邮件通知"这类真正的异步任务，再引入 Celery 不迟，不需要提前过度设计。

**追问：为什么不用 Flask？**

Flask 的异步支持是 2.0 之后补充的，不如 FastAPI 原生。FastAPI 自动生成 OpenAPI 文档，对于多接口项目调试效率高。我这个项目有中间件链（限流→超时→日志）、依赖注入（`get_session_context` 工厂）、多路由模块（bazi_router、chat_router、health_router），FastAPI 的结构更清晰，类型提示也更完整，配合 Pydantic v2 可以做到边界清晰的数据校验。

**追问：为什么用 LangGraph 而不是直接写状态机？**

自己写状态机缺乏标准化的状态传递协议和可视化工具。LangGraph 提供了 TypedDict 状态定义、节点注册、条件路由的完整框架，与 LangSmith 集成后可以追踪每个节点的输入输出，对调试 LLM 应用非常关键——比如我可以看到 `retrieve_knowledge_node` 检索到了哪些文档、`llm_generate_node` 的 prompt 是什么、生成了什么内容。自己写的状态机很容易变成意大利面条代码，在团队协作时更难维护。

**追问：为什么不用 Pinecone / Weaviate？**

Pinecone 是云服务，数据出境有合规风险，且按量计费成本不可控。Weaviate 功能强大但部署复杂，需要单独的 Docker 容器。ChromaDB 嵌入式部署，一行代码初始化，对于当前规模（几千到几万条命理知识文档）完全够用。如果未来需要支持百万级文档或多租户，再迁移到 Milvus 也不难，因为我的 Retriever 层做了抽象。

---

# 第二部分：整体架构与 LangGraph 工作流

## 2.1 系统整体架构

（面试官：请你画一下系统的整体架构，讲讲请求是怎么流转的。）

整个系统是经典的分层架构，从外到内分为四层：

```
客户端请求
    ↓
┌─────────────────────────────────────────────────┐
│  中间件链（洋葱模型）                              │
│  LoggingMiddleware → RateLimitMiddleware          │
│  → TimeoutMiddleware → CORS → GZip               │
├─────────────────────────────────────────────────┤
│  API 路由层                                       │
│  bazi_router (/api/v1/bazi/*)                    │
│  chat_router (/api/v1/chat/*)                    │
│  health_router (/health)                         │
├─────────────────────────────────────────────────┤
│  Agent 路由层                                     │
│  AgentRegistry.detect_agent(query, session)       │
│  ├→ BaziAgent (八字分析)                          │
│  └→ TarotAgent (塔罗占卜)                         │
├─────────────────────────────────────────────────┤
│  工作流引擎层                                     │
│  ├→ bazi_graph (DAG: 11个节点的线性流水线)         │
│  └→ tarot_graph (ReAct: agent↔tool 循环)          │
├─────────────────────────────────────────────────┤
│  基础设施层                                       │
│  ├→ LLM (BaseLLM → DashScopeLLM)                │
│  ├→ RAG (KnowledgeRetriever + Reranker)          │
│  ├→ Cache (RedisCacheManager)                    │
│  ├→ Storage (FileStorage)                        │
│  └→ State (SessionContext / UnifiedSession)       │
└─────────────────────────────────────────────────┘
```

### 中间件链的执行顺序

FastAPI 的中间件是洋葱模型，后注册的先执行。我在 `main.py` 中的注册顺序是：

```python
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(CORSMiddleware, ...)
app.add_middleware(TimeoutMiddleware)
app.add_middleware(RateLimitMiddleware, redis_client=_redis_client)
app.add_middleware(LoggingMiddleware)
```

实际执行顺序是：**Logging → RateLimit → Timeout → CORS → GZip → 路由处理 → GZip → CORS → Timeout → RateLimit → Logging**。

这个顺序是精心设计的：
- **Logging 最外层**：确保每个请求都有 trace_id 和耗时记录，即使被限流拒绝也能看到日志。
- **RateLimit 在 Timeout 之前**：被限流的请求直接返回 429，不会占用超时计时器的资源。
- **Timeout 在路由之前**：确保所有路由处理都受超时保护，LLM 调用不会无限等待。

### 请求完整流转路径

以一个典型的八字分析请求为例：

1. 用户发送 POST `/api/v1/chat/chat`，body 包含 `birth_data: {year: 1990, month: 6, day: 15, hour: 10, gender: "男"}`
2. **LoggingMiddleware**：生成 trace_id（UUID hex[:12]），记录请求开始时间
3. **RateLimitMiddleware**：提取客户端 IP，检查限流计数器（Redis 优先，降级内存）
4. **TimeoutMiddleware**：识别到 `/api/v1/chat` 是 LLM 路径，设置 120s 超时
5. **chat_api.handle_chat()**：
   - 检测到 `birth_data` 非空，走"表单直传"路径，跳过意图识别
   - 调用 `get_session_context()` 创建请求级 `SessionContext`
   - 创建新会话，生成 `conversation_id`
   - 调用 `AgentRegistry.detect_agent()` 路由到 `BaziAgent`
   - `BaziAgent.handle_analysis()` 调用 LangGraph `bazi_graph`
6. **bazi_graph 执行**：validate → calculate → wuxing → geju → yongshen → liunian → dayun → retrieve_knowledge → llm_generate → generate_report → safety_check
7. **结果回收**：`SessionContext.update_state()` 将 LangGraph 输出写入 `UnifiedSession`
8. **持久化**：Redis + 文件双写
9. **响应返回**：经过 Timeout → RateLimit → Logging 的出站处理，Logging 记录耗时和状态码

---

## 2.2 LangGraph 八字分析工作流（DAG 模式）

（面试官：LangGraph 的工作流具体是怎么设计的？节点之间怎么通信？）

八字分析的 LangGraph 工作流定义在 `bazi_graph.py` 中，是一个 11 个节点的有向无环图。

### 节点定义

| 序号 | 节点名 | 函数 | 职责 |
|------|--------|------|------|
| 1 | validate_input | `validate_input_node` | 校验 BirthInfo 字段合法性 |
| 2 | calculate_bazi | `calculate_bazi_node` | 八字排盘（天干地支计算） |
| 3 | analyze_wuxing | `analyze_wuxing_node` | 五行力量分析 |
| 4 | determine_geju | `determine_geju_node` | 格局判断（正官格、食神格等） |
| 5 | find_yongshen | `find_yongshen_node` | 喜用神查找 |
| 6 | check_liunian | `check_liunian_node` | 流年运势分析 |
| 7 | analyze_dayun | `analyze_dayun_node` | 大运分析 |
| 8 | retrieve_knowledge | `retrieve_knowledge_node` | RAG 知识检索 |
| 9 | llm_generate | `llm_generate_node` | LLM 生成解读文本 |
| 10 | generate_report | `generate_report_node` | 报告组装 |
| 11 | safety_check | `safety_check_node` | 安全检查（敏感内容过滤） |

### 条件路由设计

每两个节点之间都有条件路由函数，检查 `state["status"]` 是否以 `_failed` 结尾：

```python
def route_after_validation(state) -> Literal["calculate_bazi", "safety_check"]:
    if state.get("status") == "input_validation_failed":
        return "safety_check"
    return "calculate_bazi"

def route_after_calculation(state) -> Literal["analyze_wuxing", "safety_check"]:
    if state.get("status") == "calculation_failed":
        return "safety_check"
    return "analyze_wuxing"
```

这种设计的好处是：**任何一个节点失败都不会导致整个工作流崩溃**，而是优雅地跳转到 safety_check 节点，生成一个友好的错误提示返回给用户。这是生产系统必须具备的容错能力。

### 节点间通信：TypedDict 状态

所有节点共享一个 `BaziAgentState`（TypedDict），每个节点读取自己需要的字段、写入自己的输出字段：

```python
class BaziAgentState(TypedDict, total=False):
    user_input: Dict[str, Any]          # 节点1读取
    validated_input: Dict[str, Any]     # 节点1写入，节点2读取
    bazi_result: Dict[str, Any]         # 节点2写入，节点3-7读取
    wuxing_analysis: Dict[str, Any]     # 节点3写入
    geju_analysis: Dict[str, Any]       # 节点4写入
    yongshen_analysis: Dict[str, Any]   # 节点5写入
    liunian_analysis: Dict[str, Any]    # 节点6写入
    dayun_analysis: Dict[str, Any]      # 节点7写入
    knowledge_context: str              # 节点8写入，节点9读取
    llm_response: str                   # 节点9写入，节点10读取
    final_report: Dict[str, Any]        # 节点10写入
    safe_output: Dict[str, Any]         # 节点11写入
    error: str                          # 任何节点可写入
    status: str                         # 每个节点更新
```

`total=False` 表示所有字段都是可选的，这很重要——因为工作流是渐进式填充状态的，前面的节点执行时后面的字段还不存在。

### 为什么不用消息队列做节点间通信？

因为八字分析是同步请求-响应模式，用户等待一次完整的分析结果。节点间通信用共享状态（TypedDict）比消息队列更简单、延迟更低。如果未来需要做异步流水线（比如批量分析 1000 个八字），可以在 LangGraph 外层包一层 Celery，但节点间通信仍然用共享状态。

---

## 2.3 LangGraph 塔罗牌工作流（ReAct 模式）

（面试官：你提到塔罗牌用了 ReAct 模式，跟八字的 DAG 有什么区别？）

塔罗牌的工作流定义在 `tarot_graph.py` 中，是一个 ReAct Agent Loop：

```
agent_node ←→ tool_node → safety_node → END
```

### 核心区别

八字分析的 DAG 是**预定义的固定流程**——每次执行都走相同的 11 个节点，顺序不变。这适合规则明确、步骤固定的任务。

塔罗牌的 ReAct 是**LLM 自主决策的动态流程**——LLM 自己决定调用哪个工具、调用几次、什么时候结束。这适合需要灵活推理的任务，比如 LLM 可能先选牌阵，再抽牌，然后逐张解读，最后综合分析，但也可能在解读过程中决定查询知识库补充信息。

### ReAct 循环的实现

```python
def agent_node(state: TarotAgentState) -> dict:
    """LLM 决策下一步动作"""
    messages = state.get("messages", [])
    result = llm.call_with_tools(messages, TAROT_TOOLS)

    if result.has_tool_calls:
        return {
            "pending_tool_calls": result.tool_calls,
            "messages": messages + [{"role": "assistant", "content": result.content,
                                      "tool_calls": result.tool_calls}],
            "iteration": state.get("iteration", 0) + 1
        }
    else:
        return {
            "llm_response": result.content,
            "messages": messages + [{"role": "assistant", "content": result.content}],
            "status": "agent_finished"
        }

def should_continue(state) -> str:
    if state.get("iteration", 0) >= MAX_ITERATIONS:
        return "safety_node"
    if state.get("status") == "agent_finished":
        return "safety_node"
    if state.get("pending_tool_calls"):
        return "tool_node"
    return "safety_node"
```

### 工具定义

`tarot_tools.py` 定义了 5 个工具，采用 OpenAI function calling 格式：

1. **select_spread** — 根据问题类型选择牌阵（单牌、三牌、凯尔特十字等）
2. **draw_cards** — 从 78 张牌中随机抽取指定数量的牌
3. **interpret_single_card** — 获取单张牌的详细信息（正位/逆位含义）
4. **retrieve_knowledge** — 知识检索（占位，后续接入知识图谱）
5. **synthesize_reading** — 组装综合解读报告

### 防止无限循环

ReAct 模式最大的风险是 LLM 陷入无限循环——反复调用同一个工具。我设置了 `MAX_ITERATIONS = 15` 作为硬上限，超过后强制跳转到 safety_node 结束。实际测试中，一次完整的塔罗解读通常需要 5-8 次工具调用。

### 工具执行器的状态管理

`TarotToolExecutor` 维护了执行过程中的中间状态（已选牌阵、已抽牌、已解读的牌），这些状态通过 `executor_state` 字段在 LangGraph 状态中序列化/反序列化：

```python
def tool_node(state: TarotAgentState) -> dict:
    executor = TarotToolExecutor(conversation_id=state.get("conversation_id"))
    # 恢复之前的状态
    if state.get("executor_state"):
        executor.restore_state(state["executor_state"])
    # 执行工具调用
    for tool_call in state.get("pending_tool_calls", []):
        result = executor.execute(tool_call["name"], tool_call["arguments"])
    # 保存状态
    return {"executor_state": executor.save_state(), ...}
```

这种设计保证了 ReAct 循环中每次工具调用都能访问到之前的累积结果，同时状态是可序列化的，理论上可以支持断点续传。

### 随机性的确定性控制

抽牌需要随机性，但为了可重现性（比如用户刷新页面应该看到相同的结果），我用 `conversation_id + 时间戳` 作为随机种子：

```python
seed = hash(f"{conversation_id}_{timestamp}") % (2**32)
random.seed(seed)
```

这样同一次占卜的抽牌结果是确定的，但不同占卜之间是随机的。

---

## 2.4 状态定义的设计哲学

（面试官：为什么用 TypedDict 而不是 Pydantic BaseModel 做 LangGraph 状态？）

这是一个很好的问题。LangGraph 要求状态是 TypedDict，因为它需要对状态做浅合并（shallow merge）——每个节点返回一个 dict，LangGraph 把它合并到全局状态中。如果用 Pydantic BaseModel，合并操作会触发完整的校验，性能开销大，而且 Pydantic 的不可变性（frozen model）与 LangGraph 的可变状态语义冲突。

但 TypedDict 缺乏运行时校验能力，所以我在 `contracts.py` 中用 Pydantic 定义了 `UnifiedSession`，作为持久化和 API 层的数据模型。两者之间通过 `to_graph_state()` 和 `absorb_graph_result()` 方法互转：

```python
class UnifiedSession(BaseModel):
    def to_graph_state(self) -> Dict[str, Any]:
        """Pydantic → TypedDict（进入 LangGraph）"""
        state = {"conversation_id": self.metadata.conversation_id, ...}
        if self.bazi_cache:
            state["bazi_result"] = self.bazi_cache.bazi_data
        return state

    def absorb_graph_result(self, result: Dict[str, Any]):
        """TypedDict → Pydantic（从 LangGraph 回收结果）"""
        if "bazi_result" in result:
            self.bazi_cache = BaziCacheData(bazi_data=result["bazi_result"])
```

这种双模型设计的好处是：LangGraph 内部用轻量的 TypedDict 保证性能，外部用 Pydantic 保证数据完整性和序列化安全性。两者之间的转换是显式的、可测试的。

---

# 第三部分：Agent 设计与 RAG 检索

## 3.1 Agent 抽象体系

（面试官：你的 Agent 是怎么设计的？怎么做到可扩展？）

我设计了一套三层 Agent 抽象体系：**BaseAgent（抽象基类）→ 具体 Agent（BaziAgent / TarotAgent）→ AgentRegistry（注册表 + 路由）**。

### BaseAgent 抽象基类

`BaseAgent` 定义在 `src/agents/base.py`，是所有领域 Agent 的抽象接口：

```python
class BaseAgent(ABC):
    @property
    @abstractmethod
    def agent_id(self) -> str: ...          # 唯一标识："bazi", "tarot"

    @property
    @abstractmethod
    def display_name(self) -> str: ...      # 显示名称

    @property
    @abstractmethod
    def slot_schema(self) -> SlotSchema: ... # 需要的输入槽位

    @property
    @abstractmethod
    def intent_keywords(self) -> Dict[str, List[str]]: ...  # 意图关键词

    @abstractmethod
    async def handle_analysis(self, session, slots, mode) -> Dict[str, Any]: ...

    @abstractmethod
    async def handle_followup(self, session, query) -> str: ...

    def get_domain_constraints(self) -> str:
        """领域特定的 LLM 约束，注入到每个 prompt 中"""
        return ""
```

这个设计有几个关键点：

**第一，SlotSchema 槽位机制。** 每个 Agent 声明自己需要哪些输入参数。BaziAgent 需要 `birth_year/month/day/hour/gender`，TarotAgent 需要 `question_type/specific_question`。SlotSchema 提供 `get_missing()` 方法，可以检查哪些必需槽位还没填充，用于引导用户补充信息。

```python
class SlotSchema:
    def __init__(self, slots: Dict[str, Dict[str, Any]]):
        self.slots = slots

    def get_missing(self, filled: Dict[str, Any]) -> List[str]:
        return [name for name, schema in self.slots.items()
                if schema.get("required") and name not in filled]
```

**第二，domain_constraints 约束注入。** 每个 Agent 可以定义领域特定的 LLM 约束，这些约束会自动拼接到每个 prompt 中。比如 BaziAgent 的约束是"禁止重新排盘，必须使用已有的四柱数据"，TarotAgent 的约束是"必须基于已抽出的牌进行解读，区分正位和逆位"。这解决了一个实际 bug——早期版本中，用户追问时 LLM 会自行重新排盘，给出与第一次不一致的四柱结果。加了约束后，LLM 被强制使用缓存的四柱数据。

**第三，统一的 handle_analysis / handle_followup 接口。** 不管是八字还是塔罗，上层 API 都通过相同的接口调用，实现了开闭原则——新增一个 Agent（比如健康分析、事业分析）只需要继承 BaseAgent 并注册，不需要修改 API 层代码。

### AgentRegistry 注册表与路由

`AgentRegistry` 是一个类级别的注册表（class-level dict），在应用启动时注册所有 Agent：

```python
class AgentRegistry:
    _agents: Dict[str, BaseAgent] = {}

    @classmethod
    def register(cls, agent: BaseAgent) -> None:
        cls._agents[agent.agent_id] = agent

    @classmethod
    def detect_agent(cls, query: str, session=None) -> BaseAgent:
        # 1. 优先用 session 绑定的 agent_id（保持对话一致性）
        if session and session.metadata.agent_id:
            agent = cls._agents.get(session.metadata.agent_id)
            if agent:
                return agent

        # 2. 关键词路由
        tarot_keywords = ["塔罗", "占卜", "抽牌", "牌阵", "塔罗牌"]
        if any(kw in query for kw in tarot_keywords):
            agent = cls._agents.get("tarot")
            if agent:
                return agent

        # 3. 默认 bazi
        return cls.get_or_default("bazi")
```

路由策略有三层优先级：

1. **会话绑定优先**——如果用户已经在一个塔罗会话中，即使下一条消息不包含塔罗关键词，也继续路由到 TarotAgent。这保证了多轮对话的一致性。
2. **关键词匹配**——新会话时，根据用户输入中的关键词判断应该路由到哪个 Agent。
3. **默认兜底**——如果都匹配不上，默认路由到 BaziAgent。

在 `main.py` 的 lifespan 中注册：

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    AgentRegistry.register(BaziAgent())
    AgentRegistry.register(TarotAgent())
    yield
```

### 追问：为什么用类级别 dict 而不是依赖注入？

类级别 dict 是最简单的注册表实现，对于当前 2-3 个 Agent 的规模完全够用。如果 Agent 数量增长到 10+，或者需要动态加载/卸载 Agent，可以改用 FastAPI 的依赖注入 + 工厂模式。但当前阶段，简单就是最好的设计。过早引入复杂的 DI 框架（如 dependency-injector）会增加理解成本，对于一个人维护的项目得不偿失。

### 追问：如果要新增一个"健康分析 Agent"，需要改哪些代码？

只需要三步：
1. 创建 `src/agents/health_agent.py`，继承 `BaseAgent`，实现 `handle_analysis` 和 `handle_followup`
2. 在 `main.py` 的 lifespan 中添加 `AgentRegistry.register(HealthAgent())`
3. 在 `AgentRegistry.detect_agent()` 中添加健康相关的关键词

不需要修改 `chat_api.py`、不需要修改前端、不需要修改中间件。这就是开闭原则的价值。

---

## 3.2 意图识别系统

（面试官：多轮对话中，你怎么判断用户是在追问还是想开始新的分析？）

意图识别是多轮对话系统的核心难题。我实现了一个基于关键词评分的无状态意图检测器，定义在 `src/core/intent.py`：

```python
def detect_intent(query, keywords, has_prior_analysis, re_analyze_keywords=None):
    """
    纯函数，无实例变量，线程安全
    输入：query、关键词映射、是否已有分析结果
    输出：{intent, confidence, all_scores, has_prior}
    """
```

### 五种意图类型

| 意图 | 含义 | 触发条件 |
|------|------|----------|
| NEW_ANALYSIS | 新分析请求 | "帮我算一下"、"排个盘"、包含出生日期 |
| FOLLOW_UP | 追问 | "那我的事业呢"、"感情方面呢" |
| TOPIC_SWITCH | 话题切换 | "换个话题"、"不聊这个了" |
| CLARIFICATION | 澄清请求 | "什么意思"、"能详细说说吗" |
| GENERAL_QUERY | 通用查询 | 以上都不匹配时的兜底 |

### 关键设计：意图降级

当用户已经有分析结果（`has_prior_analysis=True`）时，即使用户说"帮我算一下"，也会降级为 FOLLOW_UP 而不是 NEW_ANALYSIS。这是因为在多轮对话中，用户可能只是想追问某个方面，而不是真的要重新排盘。

这个降级逻辑解决了一个实际问题：早期版本中，用户说"帮我看看事业"会被识别为 NEW_ANALYSIS，导致系统要求用户重新输入出生日期，体验很差。加了降级后，系统会基于已有的八字数据直接回答事业方面的问题。

### 追问：为什么不用 LLM 做意图识别？

两个原因：
1. **延迟**——LLM 调用需要 1-3 秒，意图识别是每个请求的第一步，如果这一步就要等 3 秒，用户体验会很差。关键词匹配是 O(n) 的字符串操作，耗时 <1ms。
2. **确定性**——意图识别需要 100% 确定性，不能有"有时候识别对、有时候识别错"的情况。LLM 的输出是概率性的，可能因为 prompt 微调就改变行为。关键词匹配的行为是完全可预测的。

如果未来需要更精细的意图识别（比如区分"帮我看看事业"和"帮我看看今年的事业运势"），可以在关键词匹配之后加一层轻量级的分类模型（如 BERT-tiny），但不会用大模型。

---

## 3.3 RAG 知识检索与重排序

（面试官：你的 RAG 是怎么实现的？检索效果怎么优化？）

RAG 管线分为三层：**Embedding 向量化 → 混合检索（Vector + BM25）→ 重排序（Reranker）**。

### 向量检索

`KnowledgeRetriever` 封装了 ChromaDB 的向量检索：

```python
class KnowledgeRetriever:
    def __init__(self, chroma_path="D:/bazi-agent/chroma_db"):
        self.client = chromadb.PersistentClient(path=chroma_path)
        self.collection = self.client.get_collection(name="bazi_knowledge")

    def get_embedding(self, text: str) -> List[float]:
        response = TextEmbedding.call(model="text-embedding-v4", input=[text])
        return response.output['embeddings'][0]['embedding']

    def search(self, query: str, top_k: int = 5) -> List[Dict]:
        query_embedding = self.get_embedding(query)
        results = self.collection.query(query_embeddings=[query_embedding], n_results=top_k)
        return results
```

### 混合检索

单纯的向量检索对命理术语的召回率不够高。比如用户问"甲木生于寅月"，向量检索可能返回语义相近但不精确的文档。BM25 基于关键词匹配，对精确术语的召回率更高。

我实现了混合检索策略，支持四种模式：

```python
class RetrievalMode(str, Enum):
    VECTOR_ONLY = "vector_only"       # 仅向量检索
    BM25_ONLY = "bm25_only"           # 仅 BM25 检索
    HYBRID = "hybrid"                 # 混合检索（分数加权合并）
    HYBRID_RERANK = "hybrid_rerank"   # 混合检索 + 重排序
```

默认使用 `HYBRID_RERANK`，先用向量检索和 BM25 各取 top-10，合并去重后送入 Reranker 重排序，最终取 top-5。

### 重排序器

`Reranker` 使用 DashScope 的 TextReRank API，对候选文档按与 query 的相关性重新排序：

```python
class Reranker:
    def rerank(self, query: str, documents: List[Dict], top_k: int = 5):
        # 调用 DashScope TextReRank API
        # 返回按相关性排序的文档
```

重排序器有几个关键的容错设计：

1. **调用频率限制**——DashScope API 有 QPS 限制，我用 `threading.Lock` + 滑动窗口计数器控制调用频率，5 小时内最多调用 N 次。
2. **自动降级**——如果 API Key 未配置、调用超限、或 API 返回错误，自动降级为按原始分数排序（`_fallback_sort`），不影响整体流程。
3. **线程安全**——调用计数器用 `threading.Lock` 保护，避免并发请求下计数不准。

### 追问：BM25 的分词怎么做的？

用 jieba 分词。命理术语很多是专有名词（如"偏财格"、"食神生财"），jieba 的默认词典不包含这些。我通过 `jieba.load_userdict()` 加载了自定义的命理术语词典，提高分词准确率。BM25 索引在首次构建后会通过 `FileStorage.save_bm25_index()` 持久化到文件，避免每次启动都重新构建。

### 追问：向量检索和 BM25 的分数怎么合并？

两种检索的分数量纲不同（向量检索是余弦相似度 0-1，BM25 是 TF-IDF 分数），不能直接相加。我用的是 Reciprocal Rank Fusion（RRF）：

```
RRF_score = Σ 1 / (k + rank_i)
```

其中 k 是常数（通常取 60），rank_i 是文档在第 i 个检索结果中的排名。RRF 的好处是只依赖排名而不依赖分数的绝对值，天然解决了量纲不一致的问题。

### 追问：RAG 的知识库是怎么构建的？

知识库的构建是一个离线流程：
1. 收集命理经典文献（如《子平真诠》、《滴天髓》等）的电子版
2. 按章节/段落切分成 chunk（每个 chunk 约 500-1000 字）
3. 用 DashScope text-embedding-v4 生成向量
4. 存入 ChromaDB，同时保存原文和元数据（来源、章节、主题标签）

切分策略很重要——如果 chunk 太大，检索精度下降；如果太小，上下文不完整。我用的是基于段落的切分，遇到标题或空行时切分，保证每个 chunk 是一个完整的论述单元。

---

## 3.4 Prompt 管理：PromptRegistry

（面试官：你的 prompt 是怎么管理的？）

早期版本的 prompt 散落在各个文件中（`chat_prompt.py` 有 10 个模板），维护困难。v0.3.0 引入了 `PromptRegistry` 集中管理：

```python
class PromptTemplate:
    def __init__(self, template: str, constraints: str = ""):
        self.template = template
        self.constraints = constraints

    def render(self, **kwargs) -> str:
        prompt = self.template.format(**kwargs)
        if self.constraints:
            prompt = f"{self.constraints}\n\n{prompt}"
        return prompt

class PromptRegistry:
    _templates: Dict[str, PromptTemplate] = {}

    @classmethod
    def register(cls, name: str, template: PromptTemplate):
        cls._templates[name] = template

    @classmethod
    def render(cls, name: str, **kwargs) -> str:
        return cls._templates[name].render(**kwargs)
```

### 约束自动拼接

每个领域有全局约束，会自动拼接到该领域的所有 prompt 前面：

```python
BAZI_CONSTRAINTS = """
【重要约束】
1. 你必须使用以下已排好的四柱数据，禁止自行重新排盘
2. 所有分析必须基于提供的五行、格局、用神数据
3. 不得编造不存在的命理术语
"""

TAROT_CONSTRAINTS = """
【重要约束】
1. 必须基于已抽出的牌进行解读
2. 严格区分正位和逆位的含义
3. 综合解读必须关联用户的具体问题
"""
```

这解决了一个关键的一致性问题：无论用户追问多少轮，LLM 都被强制使用第一次排盘的数据，不会"自行发挥"给出不一致的结果。

### 预注册模板

系统启动时预注册了 8 个模板：

- 八字：`follow_up`、`topic_switch`、`clarification`、`general_query`
- 塔罗：`tarot_card_interpret`、`tarot_synthesis`、`tarot_follow_up`、`tarot_general`

每个模板对应一种意图类型，意图识别的结果直接映射到模板名，实现了意图→prompt 的自动路由。

---

# 第四部分：高可用、限流、超时与缓存

## 4.1 中间件体系总览

（面试官：你的系统怎么保证高可用？限流、超时这些是怎么做的？）

我设计了三层中间件，按照 FastAPI 洋葱模型从外到内依次是：**LoggingMiddleware → RateLimitMiddleware → TimeoutMiddleware**。每一层都有明确的职责边界，互不耦合，任何一层出问题都不会影响其他层。

所有中间件的配置集中在 `src/config/middleware_config.py` 的 `MiddlewareConfig` 类中，支持环境变量覆盖：

```python
class MiddlewareConfig:
    # 限流
    RATE_LIMIT_PER_MINUTE = 30          # 普通接口：30次/分钟
    RATE_LIMIT_LLM_PER_MINUTE = 10      # LLM接口：10次/分钟
    RATE_LIMIT_WINDOW = 60              # 窗口大小：60秒

    # 超时
    REQUEST_TIMEOUT_DEFAULT = 30        # 普通接口：30秒
    REQUEST_TIMEOUT_LLM = 120           # LLM接口：120秒

    # 日志
    LOG_FORMAT = "json"                 # JSON格式，方便ELK聚合
    SLOW_REQUEST_THRESHOLD = 5.0        # 慢请求阈值：5秒

    # 白名单
    RATE_LIMIT_WHITELIST = ["/health", "/docs", "/openapi.json"]
    TIMEOUT_WHITELIST = ["/health", "/docs"]
    LOG_SKIP_PATHS = ["/health"]
```

配置集中管理的好处是：运维人员可以通过环境变量调整限流阈值，不需要改代码、不需要重新部署。比如大促期间可以临时放宽限流：`RATE_LIMIT_PER_MINUTE=100`。

---

## 4.2 限流中间件（RateLimitMiddleware）

### 设计目标

1. 防止单个 IP 的恶意刷接口
2. LLM 接口比普通接口更严格（因为 LLM 调用成本高）
3. Redis 不可用时自动降级到内存计数器
4. 返回标准的 429 状态码和 Retry-After 头

### 实现细节

```python
class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, redis_client=None):
        super().__init__(app)
        self.redis_client = redis_client
        self._memory_counters = defaultdict(list)  # 内存降级方案

    async def dispatch(self, request, call_next):
        # 1. 白名单路径直接放行
        if request.url.path in middleware_config.RATE_LIMIT_WHITELIST:
            return await call_next(request)

        # 2. 提取客户端 IP
        client_ip = self._get_client_ip(request)

        # 3. 判断是否是 LLM 路径（更严格的限流）
        is_llm_path = "/chat" in request.url.path or "/analyze" in request.url.path
        limit = middleware_config.RATE_LIMIT_LLM_PER_MINUTE if is_llm_path \
                else middleware_config.RATE_LIMIT_PER_MINUTE

        # 4. 检查限流
        allowed = await self._check_rate_limit(client_ip, limit, is_llm_path)
        if not allowed:
            return JSONResponse(status_code=429, content={...},
                                headers={"Retry-After": str(middleware_config.RATE_LIMIT_WINDOW)})

        return await call_next(request)
```

### 双层限流策略

**Redis 层（分布式）：** 使用 INCR + EXPIRE 实现固定窗口计数器。

```python
async def _check_redis(self, key, limit, window):
    pipe = self.redis_client.pipeline()
    pipe.incr(key)
    pipe.ttl(key)
    count, ttl = pipe.execute()
    if ttl == -1:  # 新 key，设置过期时间
        self.redis_client.expire(key, window)
    return count <= limit
```

为什么用 Pipeline？因为 INCR 和 TTL 需要原子执行。如果分两次调用，可能出现 INCR 成功但 EXPIRE 失败的情况，导致 key 永不过期，计数器永远递增，最终所有请求都被拒绝。Pipeline 保证两个命令在同一个 RTT 内执行。

**内存层（单机降级）：** 当 Redis 不可用时，使用内存 dict + 时间戳列表实现滑动窗口：

```python
async def _check_memory(self, key, limit, window):
    now = time.time()
    # 清理过期的时间戳
    self._memory_counters[key] = [
        ts for ts in self._memory_counters[key] if now - ts < window
    ]
    if len(self._memory_counters[key]) >= limit:
        return False
    self._memory_counters[key].append(now)
    return True
```

内存计数器的缺点是：多实例部署时每个实例独立计数，实际限流阈值是 `limit × 实例数`。但这是可接受的降级——Redis 不可用是异常情况，此时放宽限流比完全不限流好。

### IP 提取的安全性

```python
def _get_client_ip(self, request):
    # 优先从反向代理头提取
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    # 兜底：直连 IP
    return request.client.host if request.client else "unknown"
```

支持三种 IP 来源：`X-Forwarded-For`（Nginx/ALB）、`X-Real-IP`（Nginx）、`request.client.host`（直连）。在生产环境中，通常部署在 Nginx 后面，所以 `X-Forwarded-For` 是最常用的。

### 追问：固定窗口 vs 滑动窗口 vs 令牌桶，你怎么选的？

我用的是固定窗口（Redis INCR + EXPIRE），原因是实现最简单、Redis 操作最少（2 个命令）。固定窗口的缺点是窗口边界处可能出现突发——比如窗口最后 1 秒和下一个窗口第 1 秒各来 30 个请求，实际 2 秒内有 60 个请求。

对于我的场景，这个突发是可接受的，因为：
1. 八字分析不是高频接口，QPS 通常 <10
2. LLM 调用本身有延迟，天然限制了并发
3. 如果需要更精确的限流，可以升级为滑动窗口日志（sorted set）或令牌桶，但复杂度和 Redis 操作数都会增加

如果面试官追问令牌桶的实现，我可以讲：令牌桶用 Redis 的 Lua 脚本实现，一个 key 存储令牌数和上次填充时间，每次请求先计算应该填充多少令牌，再扣减一个。好处是可以平滑突发流量，但 Lua 脚本的调试和维护成本更高。

### 追问：如果有人伪造 X-Forwarded-For 怎么办？

这是一个真实的安全问题。如果直接信任 `X-Forwarded-For`，攻击者可以伪造任意 IP 绕过限流。解决方案是：

1. **在 Nginx 层覆盖 X-Forwarded-For**：`proxy_set_header X-Forwarded-For $remote_addr;`，这样应用层拿到的一定是 Nginx 看到的真实 IP。
2. **只取最后一个 IP**：如果经过多层代理，取 `X-Forwarded-For` 的最后一个值（最近的代理添加的），而不是第一个值（可能被伪造）。
3. **在应用层做白名单**：只信任来自已知代理 IP 的 `X-Forwarded-For` 头。

我当前的实现取的是第一个值（`split(",")[0]`），适用于单层 Nginx 代理的场景。如果部署在多层代理后面，需要调整为取倒数第 N 个值。

---

## 4.3 超时中间件（TimeoutMiddleware）

### 设计目标

1. 防止 LLM 调用无限等待（DashScope 偶尔会超时）
2. 不同路径使用不同的超时时间
3. 超时后返回标准的 504 状态码

### 实现细节

```python
class TimeoutMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # 白名单路径不设超时
        if request.url.path in middleware_config.TIMEOUT_WHITELIST:
            return await call_next(request)

        # LLM 路径用更长的超时
        is_llm_path = any(p in request.url.path for p in ["/chat", "/analyze", "/followup"])
        timeout = middleware_config.REQUEST_TIMEOUT_LLM if is_llm_path \
                  else middleware_config.REQUEST_TIMEOUT_DEFAULT

        try:
            return await asyncio.wait_for(call_next(request), timeout=timeout)
        except asyncio.TimeoutError:
            return JSONResponse(status_code=504, content={
                "success": False,
                "message": f"请求超时（{timeout}秒）",
                "trace_id": get_trace_id()
            })
```

### 差异化超时策略

| 路径类型 | 超时时间 | 原因 |
|----------|----------|------|
| `/health` | 无超时 | 健康检查必须快速返回 |
| `/api/v1/chat/*` | 120s | LLM 调用 + RAG 检索，耗时较长 |
| `/api/v1/bazi/analyze` | 120s | LangGraph 完整流水线 |
| 其他 | 30s | 普通接口 |

120 秒看起来很长，但八字分析的完整流程包括：排盘计算（~100ms）+ RAG 检索（~500ms）+ LLM 生成（~3s）+ 可能的智能续写（~3s），正常情况下 5-8 秒完成。120 秒是为了应对 DashScope API 偶尔的高延迟（P99.9 可能到 30s+）。

### 追问：asyncio.wait_for 超时后，底层的 LLM 调用会被取消吗？

好问题。`asyncio.wait_for` 超时后会取消（cancel）被包装的协程，但这只是 Python 层面的取消——底层的 HTTP 连接（到 DashScope）不会立即断开。DashScope 那边的请求可能还在处理中，会消耗 API 配额。

要真正取消底层请求，需要在 HTTP 客户端层面设置超时（如 `httpx.AsyncClient(timeout=30)`）。我在 `DashScopeLLM` 中通过 `LLMConfig.timeout` 设置了客户端级别的超时，作为第二道防线。

---

## 4.4 结构化日志中间件（LoggingMiddleware）

### 设计目标

1. 每个请求自动记录：method、path、status_code、latency_ms、client_ip、trace_id
2. 慢请求自动标记为 WARNING
3. JSON 格式输出，方便 ELK / Loki / CloudWatch 聚合

### 实现细节

```python
class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        trace_id = new_trace_id()  # 生成 UUID hex[:12]
        set_trace_id(trace_id)     # 存入 ContextVar

        start_time = time.time()
        response = await call_next(request)
        latency_ms = (time.time() - start_time) * 1000

        log_data = {
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "latency_ms": round(latency_ms, 2),
            "client_ip": self._get_client_ip(request),
            "trace_id": trace_id,
        }

        if latency_ms > middleware_config.SLOW_REQUEST_THRESHOLD * 1000:
            logger.warning("慢请求", extra={"extra_data": log_data})
        else:
            logger.info("请求完成", extra={"extra_data": log_data})

        return response
```

### trace_id 的传播机制

`trace_id` 基于 Python 的 `contextvars.ContextVar`，在请求入口生成后，自动传播到所有异步调用链中：

```python
# src/core/request_context.py
_trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")

def new_trace_id() -> str:
    tid = uuid.uuid4().hex[:12]
    _trace_id_var.set(tid)
    return tid

def get_trace_id() -> str:
    return _trace_id_var.get()
```

这意味着在 LangGraph 节点、LLM 调用、RAG 检索中，都可以通过 `get_trace_id()` 获取当前请求的 trace_id，实现全链路追踪。如果某个请求超时了，运维人员可以用 trace_id 在日志中搜索，看到这个请求经过了哪些节点、每个节点耗时多少。

### JSON 格式化器

```python
class StructuredJsonFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "extra_data"):
            log_data.update(record.extra_data)
        return json.dumps(log_data, ensure_ascii=False)
```

输出示例：
```json
{
    "timestamp": "2026-03-22 14:30:00",
    "level": "INFO",
    "logger": "access",
    "message": "请求完成",
    "method": "POST",
    "path": "/api/v1/chat/chat",
    "status_code": 200,
    "latency_ms": 4523.45,
    "client_ip": "192.168.1.100",
    "trace_id": "a1b2c3d4e5f6"
}
```

### 追问：为什么不用 OpenTelemetry？

OpenTelemetry 是更完整的可观测性方案（Traces + Metrics + Logs），但引入成本高——需要部署 Collector、配置 Exporter、集成 Jaeger/Zipkin。对于当前单实例部署的项目，结构化 JSON 日志 + trace_id 已经足够。如果未来需要微服务化，再引入 OpenTelemetry 不迟。

---

## 4.5 缓存策略（RedisCacheManager）

（面试官：你的缓存是怎么设计的？缓存一致性怎么保证？）

### 多级缓存架构

```
请求 → Redis 缓存（L1，毫秒级）→ 文件存储（L2，十毫秒级）→ 计算/LLM调用（秒级）
```

`RedisCacheManager` 定义在 `src/cache/redis_cache.py`，提供三类缓存：

| 缓存类型 | Key 格式 | TTL | 用途 |
|----------|----------|-----|------|
| 八字结果 | `bazi:{year}:{month}:{day}:{hour}:{gender}` | 24h | 排盘结果（确定性计算） |
| 会话状态 | `session:{conversation_id}` | 24h | 多轮对话上下文 |
| 检索结果 | `retrieval:{query_hash}` | 1h | RAG 检索结果 |

### 懒连接设计

```python
class RedisCacheManager:
    def __init__(self, host, port, db, password=None, enabled=True):
        self._client = None
        self._enabled = enabled
        self._config = {"host": host, "port": port, "db": db, "password": password}

    @property
    def client(self):
        if not self._enabled:
            return None
        if self._client is None:
            try:
                self._client = redis.Redis(**self._config)
                self._client.ping()
            except Exception:
                self._client = None
        return self._client
```

懒连接的好处是：应用启动时不需要 Redis 可用，只有第一次实际使用缓存时才尝试连接。如果连接失败，`client` 返回 `None`，所有缓存操作自动降级。

### 缓存穿透防护

```python
def get_or_set(self, key, factory, ttl=3600):
    """缓存穿透防护：先查缓存，miss 则调用 factory 生成并缓存"""
    cached = self.get(key)
    if cached is not None:
        return cached
    value = factory()
    self.set(key, value, ttl=ttl)
    return value
```

`get_or_set` 是经典的 Cache-Aside 模式。对于八字计算，`factory` 就是排盘计算函数。同一个生日的排盘结果是确定性的，所以缓存不存在一致性问题——计算结果永远不变。

### 缓存装饰器

```python
def cached(ttl=3600, key_prefix=""):
    """同步缓存装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache_key = f"{key_prefix}:{func.__name__}:{hash(str(args) + str(kwargs))}"
            result = redis_cache.get(cache_key)
            if result is not None:
                return result
            result = func(*args, **kwargs)
            redis_cache.set(cache_key, result, ttl=ttl)
            return result
        return wrapper
    return decorator
```

### 追问：缓存雪崩怎么防？

缓存雪崩是指大量 key 同时过期，导致请求全部打到后端。我的防护措施：

1. **TTL 随机化**——在基础 TTL 上加一个随机偏移（±10%），避免同时过期。
2. **八字缓存的特殊性**——八字计算是 CPU 密集型（~100ms），不是 IO 密集型，即使缓存全部失效，后端也能承受。真正的瓶颈是 LLM 调用，而 LLM 的结果不适合长期缓存（因为每次生成的文本不同）。
3. **降级策略**——Redis 完全不可用时，系统仍然可以正常工作，只是每次都要重新计算，延迟增加约 100ms。

### 追问：缓存击穿怎么防？

缓存击穿是指热点 key 过期瞬间，大量并发请求同时查询后端。对于八字计算场景，击穿的影响很小（计算只需 100ms）。如果是 LLM 调用场景，可以用分布式锁（Redis SETNX）保证只有一个请求去调用 LLM，其他请求等待结果。但当前没有实现，因为 LLM 的结果每次不同，缓存意义不大。

### 追问：缓存和数据库的一致性怎么保证？

我的系统没有传统数据库，持久化层是 Redis + 文件存储。一致性策略是**双写**：

```python
async def save(self):
    if not self._dirty:
        return True
    success = True
    success &= await self._persist_redis()
    success &= await self._persist_file()
    if success:
        self._dirty = False
    return success
```

Redis 和文件都写成功才标记为"干净"。如果 Redis 写失败但文件写成功，下次加载时会从文件恢复。如果文件写失败但 Redis 写成功，Redis 过期后数据丢失——但这种情况极少发生（文件系统写入失败通常意味着磁盘满了）。

严格来说，这不是强一致性，而是最终一致性。对于命理分析这个业务场景，最终一致性是可接受的——丢失一次对话历史不会造成严重后果。

---

# 第五部分：高容灾、数据一致性与并发控制

## 5.1 故障隔离与降级策略

（面试官：如果 Redis 挂了，系统会怎样？如果 LLM 服务不可用呢？）

我的系统设计了一个核心原则：**任何外部依赖的不可用都不能导致核心业务链路崩溃**。每个外部依赖都有对应的降级方案：

### 降级矩阵

| 组件 | 正常模式 | 降级模式 | 影响 |
|------|----------|----------|------|
| Redis | 缓存读写 + 分布式限流 | 内存计数器 + 文件存储 | 限流精度下降，延迟增加 ~100ms |
| DashScope LLM | 正常生成解读 | 返回提示文本"LLM 服务暂时不可用" | 无法生成自然语言解读，但排盘数据仍可返回 |
| DashScope Embedding | 向量检索 | 跳过 RAG，使用默认 prompt | 解读质量下降，但不影响功能 |
| ChromaDB | 向量存储 + 检索 | 跳过 RAG | 同上 |
| Reranker API | 重排序优化 | 按原始分数排序（fallback_sort） | 检索精度略降 |
| 文件系统 | 会话持久化 | 仅 Redis 缓存（TTL 内有效） | 超过 TTL 后会话丢失 |

### 降级实现模式

每个组件的降级都遵循相同的模式：**try-except + 日志 + 返回安全默认值**。

```python
# Redis 降级示例（RedisCacheManager）
def get(self, key):
    if not self.client:  # Redis 不可用
        return None      # 返回 None，调用方当作 cache miss 处理
    try:
        data = self.client.get(key)
        return json.loads(data) if data else None
    except Exception as e:
        logger.warning(f"Redis get 失败: {e}")
        return None  # 异常也返回 None

# LLM 降级示例（DashScopeLLM）
def call(self, messages, **kwargs):
    if not self.api_key:
        return "抱歉，AI 分析服务暂时不可用，请稍后再试。"
    try:
        response = Generation.call(model=self.model_name, messages=messages)
        return response.output.text
    except Exception as e:
        logger.error(f"LLM 调用失败: {e}")
        return "抱歉，AI 分析服务暂时不可用，请稍后再试。"

# Reranker 降级示例
def rerank(self, query, documents, top_k=5):
    if not self.api_key or not self._check_rate_limit():
        return self._fallback_sort(documents, top_k)  # 按原始分数排序
    try:
        result = TextReRank.call(...)
        return result
    except Exception:
        return self._fallback_sort(documents, top_k)
```

### LangGraph 节点级容错

在 LangGraph 工作流中，每个节点都有独立的 try-except，失败后通过条件路由跳转到 safety_check 节点：

```python
def retrieve_knowledge_node(state):
    try:
        docs = retriever.search(query, top_k=5)
        return {"knowledge_context": docs, "status": "retrieval_completed"}
    except Exception as e:
        logger.warning(f"知识检索失败: {e}")
        return {"knowledge_context": "", "status": "retrieval_skipped"}
        # 注意：不是 retrieval_failed，而是 retrieval_skipped
        # 检索失败不应阻断整个流程，LLM 可以在没有 RAG 上下文的情况下生成回复
```

这里有一个细微但重要的设计决策：知识检索失败时状态是 `retrieval_skipped` 而不是 `retrieval_failed`。`_failed` 后缀会触发条件路由跳转到 safety_check，直接结束流程。而 `_skipped` 允许流程继续到 `llm_generate` 节点——LLM 在没有 RAG 上下文的情况下仍然可以基于 prompt 模板生成回复，只是质量可能略低。

### 追问：如果多个组件同时故障怎么办？

最坏情况是 Redis + LLM + Embedding 同时不可用。此时系统的行为是：
1. 排盘计算正常（纯本地计算，不依赖外部服务）
2. 缓存全部 miss，每次都重新计算（延迟增加 ~100ms）
3. RAG 检索跳过
4. LLM 生成返回降级文本
5. 用户能看到排盘结果（四柱、五行、格局），但看不到自然语言解读

这个降级结果是可接受的——用户至少能拿到核心的排盘数据。我在全局异常处理器中也做了兜底：

```python
@app.exception_handler(BaziAgentError)
async def bazi_error_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content=ApiResponse(
            success=False,
            message=exc.message,
            error=exc.code,
            trace_id=get_trace_id(),
        ).model_dump(),
    )
```

即使出现未预期的异常，用户也能收到结构化的错误响应（包含 trace_id），而不是 500 Internal Server Error 的裸页面。

---

## 5.2 统一异常体系

（面试官：你的错误处理是怎么设计的？）

我设计了分层异常体系，定义在 `src/core/exceptions.py`：

```python
class BaziAgentError(Exception):
    """基础异常"""
    def __init__(self, message, code="UNKNOWN_ERROR", status_code=500):
        self.message = message
        self.code = code
        self.status_code = status_code

class ValidationError(BaziAgentError):        # 400
class SessionNotFoundError(BaziAgentError):    # 404
class ComponentNotInitializedError(BaziAgentError):  # 500
class LLMError(BaziAgentError):                # 502
class SafetyError(BaziAgentError):             # 400
class RateLimitError(BaziAgentError):          # 429
class RequestTimeoutError(BaziAgentError):     # 504
```

### 设计原则

1. **每个异常自带 HTTP status_code**——异常被抛出后，全局异常处理器直接用 `exc.status_code` 返回响应，不需要在每个 catch 块中硬编码状态码。
2. **每个异常自带 error code**——如 `VALIDATION_ERROR`、`SESSION_NOT_FOUND`、`LLM_ERROR`，前端可以根据 code 做差异化处理（比如 `SESSION_NOT_FOUND` 时自动创建新会话）。
3. **统一响应格式**——所有错误响应都通过 `ApiResponse` 封装，包含 `success`、`message`、`error`、`trace_id` 四个字段，前端只需要一套解析逻辑。

### 追问：为什么不直接用 FastAPI 的 HTTPException？

`HTTPException` 只有 `status_code` 和 `detail` 两个字段，缺少 `error_code` 和 `trace_id`。而且 `HTTPException` 是 FastAPI 框架的异常，如果业务逻辑层直接抛 `HTTPException`，就把 HTTP 协议的概念泄漏到了业务层，违反了分层原则。

我的 `BaziAgentError` 是纯业务异常，可以在任何层抛出（Agent 层、LLM 层、存储层），最终由 `main.py` 的全局异常处理器统一转换为 HTTP 响应。这样业务代码不需要知道自己运行在 HTTP 环境中。

---

## 5.3 会话状态管理与数据一致性

（面试官：多轮对话的状态是怎么管理的？怎么保证数据一致性？）

### SessionContext：请求级会话管理

`SessionContext` 是 v0.3.0 引入的核心组件，替代了之前的全局单例 `UnifiedStateManager`。每个 API 请求创建一个独立的 `SessionContext` 实例：

```python
# src/dependencies.py
def get_session_context() -> SessionContext:
    """请求级工厂函数"""
    return SessionContext(redis_cache=redis_cache, file_storage=file_storage)
```

### 为什么要从全局单例改为请求级实例？

全局单例 `UnifiedStateManager` 有一个严重的并发问题：多个请求同时操作同一个会话时，状态会互相覆盖。

场景：用户 A 和用户 B 同时发送请求，都操作 `conversation_id=abc123`。

```
时间线：
T1: 请求A load_session("abc123") → 内存中有 session_A
T2: 请求B load_session("abc123") → 内存中覆盖为 session_B
T3: 请求A update_state({"bazi_result": ...}) → 写入 session_B（错误！）
T4: 请求B save() → 保存了请求A的数据（数据交叉！）
```

`SessionContext` 解决了这个问题：每个请求有自己的实例，实例内部维护自己的 `_session` 对象，互不干扰。

### 脏标记优化

```python
class SessionContext:
    def __init__(self, redis_cache, file_storage):
        self._session: Optional[UnifiedSession] = None
        self._dirty = False

    def update_state(self, updates: dict):
        if not self._session:
            return
        # 更新 session 内部状态
        if "bazi_result" in updates:
            self._session.bazi_cache = BaziCacheData(bazi_data=updates["bazi_result"])
        self._dirty = True

    async def save(self):
        if not self._dirty:
            return True  # 没有修改，跳过持久化
        success = await self._persist()
        if success:
            self._dirty = False
        return success
```

脏标记避免了不必要的持久化操作。如果一个请求只是读取会话（比如查看历史消息），不会触发任何写操作。

### 双写持久化

```python
async def _persist(self):
    success = True
    # 1. 写 Redis（快，但可能失败）
    success &= await self._persist_redis()
    # 2. 写文件（慢，但可靠）
    success &= await self._persist_file()
    return success
```

Redis 是热存储（读写快，但可能丢失），文件是冷存储（读写慢，但持久可靠）。双写保证了：
- 正常情况下，读取走 Redis（<1ms）
- Redis 不可用时，从文件恢复（~10ms）
- Redis 数据丢失后（如重启），从文件重建

### 会话加载的优先级

```python
async def load_session(self, conversation_id):
    # 1. 先查 Redis
    session_data = await self._load_from_redis(conversation_id)
    if session_data:
        self._session = UnifiedSession(**session_data)
        return self._session

    # 2. Redis miss，查文件
    session_data = await self._load_from_file(conversation_id)
    if session_data:
        self._session = UnifiedSession(**session_data)
        # 回填 Redis
        await self._persist_redis()
        return self._session

    return None  # 会话不存在
```

注意第 2 步的"回填 Redis"——从文件加载后自动写入 Redis，下次就能从 Redis 直接读取。这是经典的 Cache-Aside + Read-Through 混合模式。

### 追问：双写会不会出现不一致？

会。考虑这个场景：

```
T1: persist_redis() 成功
T2: persist_file() 失败（磁盘满）
T3: Redis 中有新数据，文件中是旧数据
T4: Redis 重启，数据丢失
T5: 从文件加载 → 拿到旧数据（不一致！）
```

这是一个已知的权衡。严格的一致性需要分布式事务（如 2PC），但对于命理分析这个场景，偶尔丢失一轮对话历史是可接受的。如果要提升一致性，可以：

1. **Write-Ahead Log**——先写 WAL，再写 Redis 和文件，任何一步失败都可以从 WAL 恢复。
2. **Redis Persistence**——开启 Redis 的 AOF 持久化，减少数据丢失的窗口。
3. **版本号乐观锁**——每次写入时检查版本号，如果版本不匹配说明有并发写入，拒绝本次写入。

当前我选择了最简单的方案（双写 + 最终一致），因为业务场景不需要强一致性。

### 追问：如果两个请求同时修改同一个会话怎么办？

这是经典的并发写入问题。我的解决方案是**请求级隔离 + 最后写入胜出（Last Write Wins）**：

1. 每个请求有自己的 `SessionContext` 实例
2. 请求开始时 `load_session()` 加载最新状态
3. 请求过程中在内存中修改
4. 请求结束时 `save()` 写回

如果两个请求同时修改同一个会话，后保存的会覆盖先保存的。这在实际场景中很少发生——同一个用户不太可能同时发两个请求修改同一个会话。如果确实需要防止并发写入，可以用 Redis 分布式锁：

```python
async def save_with_lock(self):
    lock_key = f"lock:session:{self._session.metadata.conversation_id}"
    lock = self.redis_cache.client.lock(lock_key, timeout=5)
    if lock.acquire(blocking=True, blocking_timeout=3):
        try:
            await self._persist()
        finally:
            lock.release()
```

但当前没有实现，因为实际场景中不需要。

---

## 5.4 并发控制与会话隔离

（面试官：你怎么保证多个并发请求之间的数据隔离？）

### asyncio 协程模型下的并发

Python 的 asyncio 是单线程协程模型，不存在真正的并行执行（除非用 `asyncio.to_thread` 或多进程）。但协程之间仍然存在交错执行的问题——在每个 `await` 点，事件循环可能切换到另一个协程。

```python
async def handle_chat(request):
    ctx = SessionContext(...)       # 每个请求独立实例
    ctx.load_session(conv_id)       # await 点：可能切换协程
    ctx.update_state({"bazi_result": ...})
    await ctx.save()                # await 点：可能切换协程
```

关键保证是：**每个请求的 `SessionContext` 是独立实例**，即使协程交错执行，也不会互相影响。这是通过 `get_session_context()` 工厂函数保证的——每次调用都返回新实例。

### conversation_id 唯一性

`conversation_id` 使用 UUID v4 生成，碰撞概率极低（2^122 分之一）。我在并发测试中验证了 100 个协程同时创建会话，conversation_id 全部唯一：

```python
async def test_concurrent_session_create_unique_ids(self):
    async def create_one(i):
        ctx = SessionContext(redis_cache=None, file_storage=None)
        state = ctx.create_session(user_id=f"user_{i}")
        return state["conversation_id"]

    ids = await asyncio.gather(*[create_one(i) for i in range(100)])
    assert len(set(ids)) == 100, "conversation_id 存在重复"
```

### 消息计数隔离

每个会话独立维护消息计数，并发会话之间不会互相干扰：

```python
async def test_concurrent_add_messages_no_cross_contamination(self):
    async def session_with_n_messages(n):
        ctx = SessionContext(redis_cache=None, file_storage=None)
        ctx.create_session(user_id="u")
        for j in range(n):
            ctx.add_message("user", f"msg_{j}")
            await asyncio.sleep(0)  # 让出事件循环
        return ctx.get_session().metadata.message_count

    tasks = [session_with_n_messages(n) for n in range(1, 11)]
    counts = await asyncio.gather(*tasks)
    for expected, actual in enumerate(counts, start=1):
        assert actual == expected
```

`await asyncio.sleep(0)` 是关键——它强制让出事件循环，模拟真实场景中的协程切换。如果会话隔离有问题，消息计数就会出错。

### 限流计数器的并发安全

内存限流计数器使用 Python dict，在 asyncio 单线程模型下是安全的（没有真正的并行写入）。但如果未来改用多线程（如 `uvicorn --workers 4`），就需要加锁或改用 `multiprocessing.Manager`。

Redis 限流计数器天然是并发安全的——INCR 是原子操作，Pipeline 保证多个命令的原子执行。

### Reranker 的线程安全

`Reranker` 的调用计数器使用 `threading.Lock` 保护：

```python
class Reranker:
    def __init__(self):
        self._call_count = 0
        self._lock = threading.Lock()

    def _check_rate_limit(self):
        with self._lock:
            if self._call_count >= self.max_calls:
                return False
            self._call_count += 1
            return True
```

为什么用 `threading.Lock` 而不是 `asyncio.Lock`？因为 `Reranker` 可能在同步上下文中被调用（如 LangGraph 节点），`asyncio.Lock` 只能在异步上下文中使用。`threading.Lock` 在单线程 asyncio 中也能正常工作（虽然不会真正阻塞），保证了兼容性。

### 追问：如果用 Gunicorn + Uvicorn 多 Worker 部署，会有什么问题？

多 Worker 部署时，每个 Worker 是独立进程，内存不共享。影响：

1. **内存限流计数器失效**——每个 Worker 独立计数，实际限流阈值变为 `limit × worker_count`。解决方案：使用 Redis 限流（已实现）。
2. **AgentRegistry 每个 Worker 独立注册**——不影响功能，因为注册是在 lifespan 中完成的，每个 Worker 启动时都会注册。
3. **SessionContext 内存状态不共享**——不影响功能，因为持久化走 Redis/文件，每个请求都会从 Redis 加载最新状态。
4. **Reranker 调用计数器不共享**——每个 Worker 独立计数，实际调用次数可能超限。解决方案：改用 Redis 计数器（未实现，因为当前单 Worker 部署）。

总结：多 Worker 部署时，所有需要跨进程共享的状态都应该放在 Redis 中。我的设计已经为此做了准备——Redis 是主存储，内存只是降级方案。

---

## 5.5 数据契约与向后兼容

（面试官：你提到了 v0.2.0 到 v0.3.0 的重构，怎么保证向后兼容？）

### 统一数据契约

v0.3.0 引入了 `contracts.py` 作为唯一的数据模型定义，替代了之前 `storage/models.py` 和 `graph/state.py` 的双重表示。核心模型是 `UnifiedSession`：

```python
class UnifiedSession(BaseModel):
    messages: List[ChatMessage] = []
    metadata: SessionMetadata
    bazi_cache: Optional[BaziCacheData] = None
    tarot_cache: Optional[TarotCacheData] = None
```

### 旧数据迁移

`SessionContext` 内置了旧数据格式的自动迁移：

```python
def _migrate_old_session(self, old_data: dict) -> UnifiedSession:
    """从旧 SessionData 格式迁移到 UnifiedSession"""
    # 旧格式的消息是 List[Dict]，新格式是 List[ChatMessage]
    messages = [ChatMessage(**msg) for msg in old_data.get("messages", [])]
    # 旧格式的 bazi_cache 是 Dict，新格式是 BaziCacheData
    bazi_cache = BaziCacheData(**old_data["bazi_cache"]) if old_data.get("bazi_cache") else None
    return UnifiedSession(messages=messages, metadata=..., bazi_cache=bazi_cache)
```

这样旧版本创建的会话数据可以被新版本无缝加载，用户不会感知到升级。

### UnifiedStateManager 向后兼容层

`state_manager.py` 中的 `UnifiedStateManager` 保留为向后兼容别名，内部委托给 `SessionContext`：

```python
# src/dependencies.py
state_manager = UnifiedStateManager(redis_cache=redis_cache, file_storage=file_storage)
```

旧代码中使用 `state_manager.load_session()` 的地方不需要修改，新代码使用 `SessionContext`。两者最终操作的是同一套 Redis/文件存储，数据格式统一。

---

# 第六部分：测试设计、边界条件与反问环节

## 6.1 测试体系总览

（面试官：你的项目有测试吗？测试覆盖了哪些方面？）

我设计了两套测试：**边界条件测试（test_boundary.py）** 和 **并发控制测试（test_concurrency.py）**，共 84 个测试用例，全部通过，耗时 3 秒。

### 测试分类

| 测试文件 | 用例数 | 覆盖范围 |
|----------|--------|----------|
| test_boundary.py | 66 | 输入校验边界、会话上下文边界、缓存降级、限流边界、安全检查、意图识别 |
| test_concurrency.py | 18 | 会话隔离、ID 唯一性、限流并发、Redis Pipeline 原子性、超时行为、并发聊天 |

### 测试策略

1. **不依赖外部服务**——所有测试用 Mock 替代 Redis、LLM、DashScope API，可以在无网络环境下运行。
2. **关注边界而非正常路径**——正常路径的测试价值低（"输入正确数据得到正确结果"），边界条件才是 bug 的高发区。
3. **并发测试用 asyncio.gather**——模拟多个协程同时操作，验证数据隔离。

---

## 6.2 边界条件测试详解

### 6.2.1 BirthInfo 字段边界

八字排盘的输入是出生日期时间，每个字段都有合法范围：

```python
class TestBirthInfoBoundary:
    def _make_birth_info(self, **kwargs):
        from src.core.models.bazi_models import BirthInfo
        defaults = dict(year=1990, month=1, day=1, hour=0, minute=0, gender="男")
        defaults.update(kwargs)
        return BirthInfo(**defaults)
```

| 测试用例 | 输入 | 期望行为 | 测试意图 |
|----------|------|----------|----------|
| test_year_min_valid | year=1900 | 正常创建 | 最小有效年份 |
| test_year_max_valid | year=2100 | 正常创建 | 最大有效年份 |
| test_year_zero_raises | year=0 | 抛出异常 | 零值边界 |
| test_year_negative_raises | year=-1 | 抛出异常 | 负值边界 |
| test_month_zero_raises | month=0 | 抛出异常 | 月份下界 |
| test_month_13_raises | month=13 | 抛出异常 | 月份上界 |
| test_day_zero_raises | day=0 | 抛出异常 | 日期下界 |
| test_day_32_raises | day=32 | 抛出异常 | 日期上界 |
| test_hour_midnight | hour=0 | 正常创建 | 子时（午夜） |
| test_hour_23 | hour=23 | 正常创建 | 亥时（最后一个时辰） |
| test_hour_negative_raises | hour=-1 | 抛出异常 | 时辰下界 |
| test_hour_24_raises | hour=24 | 抛出异常 | 时辰上界 |
| test_leap_year_feb29 | 2000-02-29 | 正常创建 | 闰年 2 月 29 日 |

这些测试验证了 Pydantic 模型的 validator 是否正确拦截了非法输入。如果 validator 缺失，非法输入会进入排盘计算，可能导致数组越界或计算错误。

### 6.2.2 BaziCalculator 边界

排盘计算有几个特殊的边界条件：

```python
class TestBaziCalculatorBoundary:
    def test_midnight_birth(self):
        """午夜出生：子时跨日问题"""
        # 23:00-01:00 是子时，但 23:00 属于当天还是次日？
        result = calculator.calculate(BirthInfo(year=1990, month=1, day=1, hour=0, ...))
        assert result.four_pillars is not None

    def test_solar_term_boundary_lichun(self):
        """立春边界：年柱切换点"""
        # 立春前后一天，年柱可能不同
        result = calculator.calculate(BirthInfo(year=2024, month=2, day=4, hour=10, ...))
        assert result.four_pillars is not None

    def test_century_year(self):
        """世纪年：2000年是闰年，1900年不是"""
        result = calculator.calculate(BirthInfo(year=2000, month=2, day=29, hour=12, ...))
        assert result.four_pillars is not None

    def test_far_future_year(self):
        """远未来年份：2050年"""
        result = calculator.calculate(BirthInfo(year=2050, month=6, day=15, hour=8, ...))
        assert result.four_pillars is not None
```

**立春边界**是最容易出 bug 的地方。中国传统历法以立春为年的分界点，而不是公历 1 月 1 日。2024 年的立春是 2 月 4 日 16:27，在这个时刻之前出生的人年柱是癸卯（2023），之后是甲辰（2024）。如果排盘引擎没有精确到小时的节气判定，就会算错年柱。

### 6.2.3 ChatInput 边界

多轮对话的输入也有边界条件：

```python
class TestChatInputBoundary:
    def test_empty_query_accepted_by_model(self):
        """空 query 应该被模型接受（不在输入层拒绝）"""
        input_data = ChatInput(query="", user_id="test")
        assert input_data.query == ""

    def test_very_long_query(self):
        """超长 query（10000 字符）"""
        input_data = ChatInput(query="测" * 10000, user_id="test")
        assert len(input_data.query) == 10000

    def test_query_with_special_chars(self):
        """特殊字符：SQL 注入、XSS 尝试"""
        input_data = ChatInput(query="'; DROP TABLE users; --", user_id="test")
        assert input_data.query == "'; DROP TABLE users; --"
        # 注意：输入层不做过滤，安全检查在 safety_check 节点

    def test_query_with_unicode(self):
        """Unicode 字符：emoji、日文、韩文"""
        input_data = ChatInput(query="🔮 占い 점술", user_id="test")
        assert "🔮" in input_data.query

    def test_analysis_mode_valid_values(self):
        """分析模式：full / simple"""
        for mode in ["full", "simple"]:
            input_data = ChatInput(query="test", analysis_mode=mode)
            assert input_data.analysis_mode == mode

    def test_agent_type_valid_values(self):
        """Agent 类型：bazi / tarot"""
        for agent in ["bazi", "tarot"]:
            input_data = ChatInput(query="test", agent_type=agent)
            assert input_data.agent_type == agent
```

**空 query 的处理**是一个设计决策：我选择在输入层接受空 query，而不是拒绝。原因是空 query 可能是前端 bug 导致的，在输入层拒绝会返回 400 错误，用户看到的是"请求格式错误"，不友好。让空 query 进入意图识别，会被识别为 GENERAL_QUERY，返回一个引导性的回复（"请问您想了解什么？"），体验更好。

### 6.2.4 SessionContext 边界

会话上下文在各种异常状态下的行为：

```python
class TestSessionContextBoundary:
    def test_create_without_redis_or_storage(self):
        """无 Redis、无 FileStorage 时仍能创建会话"""
        ctx = SessionContext(redis_cache=None, file_storage=None)
        state = ctx.create_session(user_id="test")
        assert state["conversation_id"] is not None

    def test_load_nonexistent_session_returns_none(self):
        """加载不存在的会话返回 None"""
        ctx = SessionContext(redis_cache=None, file_storage=None)
        result = ctx.load_session("nonexistent_id")
        assert result is None

    def test_add_message_before_create_is_noop(self):
        """创建会话前添加消息是空操作（不报错）"""
        ctx = SessionContext(redis_cache=None, file_storage=None)
        ctx.add_message("user", "hello")  # 不应抛异常

    def test_save_without_session_returns_false(self):
        """无会话时保存返回 False"""
        ctx = SessionContext(redis_cache=None, file_storage=None)
        result = ctx.save()
        assert result == False

    def test_conversation_id_uniqueness(self):
        """连续创建 100 个会话，ID 全部唯一"""
        ids = set()
        for _ in range(100):
            ctx = SessionContext(redis_cache=None, file_storage=None)
            state = ctx.create_session(user_id="test")
            ids.add(state["conversation_id"])
        assert len(ids) == 100

    def test_clear_session_resets_messages(self):
        """清空会话后消息列表为空"""
        ctx = SessionContext(redis_cache=None, file_storage=None)
        ctx.create_session(user_id="test")
        ctx.add_message("user", "hello")
        ctx.clear_session()
        assert ctx.get_session().messages == []
```

这些测试验证了 SessionContext 的**防御性编程**——在各种"不应该发生但可能发生"的状态下，系统不会崩溃，而是返回安全的默认值。

### 6.2.5 Redis 缓存边界

```python
class TestRedisCacheManagerBoundary:
    def test_get_returns_none_when_redis_unavailable(self):
        """Redis 不可用时 get 返回 None"""
        cache = RedisCacheManager(host="invalid", port=0, enabled=True)
        assert cache.get("any_key") is None

    def test_set_returns_false_when_redis_unavailable(self):
        """Redis 不可用时 set 返回 False"""
        cache = RedisCacheManager(host="invalid", port=0, enabled=True)
        assert cache.set("key", "value") == False

    def test_cache_disabled_get_returns_none(self):
        """缓存禁用时 get 返回 None"""
        cache = RedisCacheManager(host="localhost", port=6379, enabled=False)
        assert cache.get("any_key") is None

    def test_mock_redis_set_and_get(self):
        """Mock Redis 的正常读写"""
        cache = RedisCacheManager(host="localhost", port=6379, enabled=True)
        cache._client = MagicMock()
        cache._client.get.return_value = json.dumps({"key": "value"}).encode()
        result = cache.get("test_key")
        assert result == {"key": "value"}
```

### 6.2.6 限流边界

```python
class TestRateLimitBoundary:
    def test_memory_counter_allows_within_limit(self):
        """限流阈值内的请求全部放行"""
        # 发送 limit 次请求，全部应该被放行

    def test_memory_counter_blocks_at_limit(self):
        """达到限流阈值后拒绝"""
        # 第 limit+1 次请求应该被拒绝

    def test_memory_counter_resets_after_window(self):
        """窗口过期后计数器重置"""
        # 等待 window 秒后，计数器应该清零

    def test_llm_path_uses_stricter_limit(self):
        """LLM 路径使用更严格的限流阈值"""
        # /chat 路径的 limit 应该是 RATE_LIMIT_LLM_PER_MINUTE

    def test_get_client_ip_from_x_forwarded_for(self):
        """从 X-Forwarded-For 提取 IP"""
        # 模拟 Nginx 代理场景

    def test_get_client_ip_from_x_real_ip(self):
        """从 X-Real-IP 提取 IP"""

    def test_get_client_ip_fallback_to_client_host(self):
        """无代理头时使用直连 IP"""
```

### 6.2.7 安全检查边界

```python
class TestSafetyCheckBoundary:
    def test_empty_string_is_safe(self):
        """空字符串应该通过安全检查"""

    def test_normal_bazi_query_is_safe(self):
        """正常的八字查询应该通过"""

    def test_crisis_detection_on_explicit_phrase(self):
        """包含危机关键词的输入应该被标记"""

    def test_very_long_input_does_not_crash_safety_check(self):
        """超长输入不应导致安全检查崩溃"""
```

### 6.2.8 意图识别边界

```python
class TestIntentDetectionBoundary:
    def test_empty_query_returns_valid_intent(self):
        """空 query 应该返回有效的意图（GENERAL_QUERY）"""

    def test_whitespace_only_query(self):
        """纯空白 query"""

    def test_unknown_intent_falls_back_to_general_query(self):
        """无法识别的意图降级为 GENERAL_QUERY"""
```

---

## 6.3 并发控制测试详解

### 6.3.1 会话隔离测试

```python
class TestSessionContextConcurrency:
    async def test_concurrent_session_create_unique_ids(self):
        """100 个协程并发创建会话，ID 全部唯一"""
        ids = await asyncio.gather(*[create_one(i) for i in range(100)])
        assert len(set(ids)) == 100

    async def test_concurrent_sessions_data_isolation(self):
        """50 个并发会话各自写入不同数据，读取时不交叉"""
        results = await asyncio.gather(*[write_and_read(i) for i in range(50)])
        for i, owner in enumerate(results):
            assert owner == i  # 每个会话只能读到自己写入的数据

    async def test_concurrent_add_messages_no_cross_contamination(self):
        """并发会话各自累积消息，计数互不干扰"""
        # 会话1写1条，会话2写2条，...，会话10写10条
        # 验证每个会话的消息计数正确
```

这三个测试是并发安全的核心验证。`test_concurrent_sessions_data_isolation` 是最关键的——它验证了 50 个协程同时读写不同会话时，数据不会交叉污染。如果 SessionContext 内部有共享状态（比如类变量），这个测试就会失败。

### 6.3.2 限流并发测试

```python
class TestRateLimitConcurrency:
    async def test_memory_counter_concurrent_does_not_exceed_limit(self):
        """50 个协程同时请求，放行总数不超过 limit"""
        # 验证计数器在并发下的正确性

    async def test_different_ips_have_independent_counters(self):
        """不同 IP 的计数器互相独立"""

    async def test_llm_and_general_paths_independent_counters(self):
        """LLM 路径和普通路径的计数器互相独立"""
```

### 6.3.3 Redis Pipeline 原子性测试

```python
class TestRedisPipelineConcurrency:
    def test_redis_pipeline_incr_sets_expire_on_first_call(self):
        """Pipeline: INCR + EXPIRE 在首次调用时设置过期"""

    def test_redis_pipeline_no_expire_on_existing_key(self):
        """Pipeline: 已存在的 key 不重复设置过期"""

    def test_redis_pipeline_blocks_over_limit(self):
        """Pipeline: 超过限流阈值后拒绝"""

    def test_redis_error_falls_back_to_memory(self):
        """Redis 异常时降级到内存计数器"""
```

### 6.3.4 超时中间件测试

```python
class TestTimeoutMiddlewareConcurrency:
    async def test_fast_response_passes_through(self):
        """快速响应正常通过"""

    async def test_slow_response_returns_504(self):
        """慢响应返回 504"""

    async def test_whitelisted_path_skips_timeout(self):
        """白名单路径不受超时限制"""
```

### 6.3.5 端到端并发测试

```python
class TestHandleChatConcurrency:
    async def test_concurrent_chat_requests_independent_sessions(self):
        """并发聊天请求各自创建独立会话"""
        # 模拟 10 个用户同时发起聊天
        # 验证每个用户的会话独立

class TestCacheConcurrency:
    async def test_concurrent_cache_read_write_no_exception(self):
        """并发缓存读写不抛异常"""

    async def test_concurrent_mock_redis_pipeline(self):
        """并发 Redis Pipeline 操作"""
```

---

## 6.4 测试运行结果

```
============================== test session starts ==============================
collected 84 items

tests/test_boundary.py    66 passed
tests/test_concurrency.py 18 passed

============================== 84 passed in 3.00s ===============================
```

全部 84 个用例通过，耗时 3 秒。没有依赖外部服务（Redis、DashScope），可以在 CI/CD 中无条件运行。

---

## 6.5 面试反问环节

（面试官：你有什么想问我的吗？）

### 反问 1：团队的 AI 应用架构

"我注意到贵公司在做 AI 相关的产品，想了解一下团队目前的 AI 应用架构是怎样的？是用 LangChain/LangGraph 这类框架，还是自研的 Agent 框架？LLM 调用是直接调 API 还是有自己的推理服务？"

这个问题展示了你对 AI 工程的理解深度，同时也能了解团队的技术栈是否与你的经验匹配。

### 反问 2：可观测性和监控

"团队目前的可观测性方案是什么？用 OpenTelemetry 还是自研的 tracing？对于 LLM 调用的监控（延迟、token 消耗、错误率）有什么实践？"

这个问题展示了你对生产系统运维的关注，不只是写代码，还关心代码上线后的运行状态。

### 反问 3：测试策略

"团队对 AI 应用的测试策略是什么？LLM 的输出是非确定性的，怎么做回归测试？有没有用 eval framework（如 LangSmith Evaluation）？"

这个问题展示了你对 AI 应用测试的独特挑战的理解。

---

# 附录：高频面试问题速查表

## A. 系统设计类

| 问题 | 回答要点 | 对应章节 |
|------|----------|----------|
| 画一下系统架构 | 四层架构：中间件→API→Agent→基础设施 | 2.1 |
| 请求怎么流转的 | 8 步完整链路 | 2.1 |
| 为什么用 LangGraph | DAG + ReAct 双模式，可观测可重放 | 1.2.2 |
| 节点间怎么通信 | TypedDict 共享状态 | 2.2 |
| 怎么做到可扩展 | BaseAgent + AgentRegistry + 开闭原则 | 3.1 |

## B. 高可用类

| 问题 | 回答要点 | 对应章节 |
|------|----------|----------|
| Redis 挂了怎么办 | 内存降级，文件兜底 | 5.1 |
| LLM 超时怎么办 | TimeoutMiddleware + 客户端超时双保险 | 4.3 |
| 限流怎么做的 | Redis INCR + 内存降级，双路径差异化 | 4.2 |
| 缓存雪崩怎么防 | TTL 随机化 + 计算成本低 | 4.5 |
| 缓存击穿怎么防 | 分布式锁（可选），当前场景不需要 | 4.5 |

## C. 一致性类

| 问题 | 回答要点 | 对应章节 |
|------|----------|----------|
| 多轮对话一致性 | BAZI_CONSTRAINTS 约束 + bazi_cache | 3.4 |
| 缓存和存储一致性 | 双写 + 最终一致 + 业务可接受 | 4.5 |
| 并发写入怎么办 | 请求级隔离 + Last Write Wins | 5.3 |
| 会话隔离怎么保证 | SessionContext 独立实例 + 并发测试验证 | 5.4 |

## D. 测试类

| 问题 | 回答要点 | 对应章节 |
|------|----------|----------|
| 测试覆盖了什么 | 84 用例：边界 66 + 并发 18 | 6.1 |
| 怎么测并发 | asyncio.gather + sleep(0) 强制切换 | 6.3 |
| 怎么 Mock 外部服务 | unittest.mock + AsyncMock | 6.2 |
| 边界条件怎么选的 | 等价类划分 + 边界值分析 | 6.2 |

## E. 实际 Bug 类

| 问题 | 回答要点 | 对应章节 |
|------|----------|----------|
| 遇到过什么印象深刻的 bug | LLM 自行重新排盘导致四柱不一致 | 3.4 |
| 怎么发现的 | 用户反馈追问时数据变了 | 3.4 |
| 怎么修的 | BAZI_CONSTRAINTS + bazi_cache 强制引用 | 3.4 |
| 怎么防止再犯 | 约束自动拼接到所有 prompt | 3.4 |

---

# 附录 B：项目关键文件索引

| 文件 | 用途 |
|------|------|
| src/main.py | 应用入口，中间件注册，全局异常处理 |
| src/api/chat_api.py | 多轮对话 API，意图路由 |
| src/api/bazi_api.py | 八字分析 API |
| src/agents/base.py | Agent 抽象基类 |
| src/agents/registry.py | Agent 注册表与路由 |
| src/agents/bazi_agent.py | 八字 Agent 实现 |
| src/agents/tarot_agent.py | 塔罗 Agent 实现 |
| src/agents/tarot_tools.py | 塔罗工具集 |
| src/graph/bazi_graph.py | 八字 LangGraph DAG |
| src/graph/tarot_graph.py | 塔罗 ReAct Loop |
| src/graph/state.py | LangGraph 状态定义 |
| src/graph/nodes.py | LangGraph 节点实现 |
| src/core/contracts.py | 统一数据契约 |
| src/core/session_context.py | 请求级会话管理 |
| src/core/exceptions.py | 统一异常体系 |
| src/core/intent.py | 意图识别 |
| src/core/request_context.py | 请求上下文（trace_id） |
| src/middleware/rate_limit.py | 限流中间件 |
| src/middleware/timeout.py | 超时中间件 |
| src/middleware/logging_middleware.py | 结构化日志中间件 |
| src/cache/redis_cache.py | Redis 缓存管理 |
| src/llm/base.py | LLM 抽象接口 |
| src/llm/dashscope_llm.py | DashScope LLM 实现 |
| src/rag/retriever.py | 知识检索器 |
| src/rag/reranker.py | 重排序器 |
| src/prompts/registry.py | Prompt 模板注册表 |
| src/dependencies.py | 共享依赖与工厂函数 |
| src/config/middleware_config.py | 中间件配置 |
| tests/test_boundary.py | 边界条件测试（66 用例） |
| tests/test_concurrency.py | 并发控制测试（18 用例） |

---

> 全文完。本逐字稿覆盖了项目的所有生产级设计，可根据面试官的提问方向灵活跳转到对应章节。建议重点准备第四部分（高可用）和第五部分（一致性），这是后端面试的高频考点。
