# P0：企业级中间件方案 — 限流 / 超时 / 结构化日志 / 健康检查

> 目标：以最小改动量为项目增加 4 个生产级中间件，面试时每个都能展开讲原理和设计取舍。

---

## 一、总体架构

```
请求 → GZipMiddleware
     → RequestContextMiddleware（已有，增强）
     → RateLimitMiddleware（新增）
     → TimeoutMiddleware（新增）
     → 路由处理
     → 结构化日志自动记录
```

新增/修改文件清单：

| 文件 | 动作 | 说明 |
|------|------|------|
| `src/middleware/__init__.py` | 新建 | 中间件包 |
| `src/middleware/rate_limit.py` | 新建 | 滑动窗口限流中间件 |
| `src/middleware/timeout.py` | 新建 | 请求超时中间件 |
| `src/middleware/logging_middleware.py` | 新建 | 结构化日志中间件（替代当前 request_context_middleware） |
| `src/api/health.py` | 新建 | 健康检查端点 |
| `src/core/exceptions.py` | 修改 | 新增 RateLimitError、TimeoutError |
| `src/main.py` | 修改 | 注册新中间件 + 健康检查路由 |
| `src/config/middleware_config.py` | 新建 | 中间件配置集中管理 |

---

## 二、中间件配置中心

### `src/config/middleware_config.py`

集中管理所有中间件参数，方便环境变量覆盖。

```python
# src/config/middleware_config.py
"""中间件配置 — 集中管理，支持环境变量覆盖"""
import os


class MiddlewareConfig:
    """中间件配置"""

    # ---- 限流 ----
    # 每个 IP 每分钟最大请求数
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30"))
    # LLM 类接口（/chat, /followup）更严格的限流
    RATE_LIMIT_LLM_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_LLM_PER_MINUTE", "10"))
    # 限流滑动窗口大小（秒）
    RATE_LIMIT_WINDOW: int = 60
    # 限流白名单路径（不限流）
    RATE_LIMIT_WHITELIST: list = ["/health", "/ready", "/docs", "/openapi.json", "/static"]

    # ---- 超时 ----
    # 默认请求超时（秒）
    REQUEST_TIMEOUT_DEFAULT: float = float(os.getenv("REQUEST_TIMEOUT_DEFAULT", "30"))
    # LLM 类接口超时（秒）— LLM 调用慢，给更长时间
    REQUEST_TIMEOUT_LLM: float = float(os.getenv("REQUEST_TIMEOUT_LLM", "120"))
    # 超时白名单路径
    TIMEOUT_WHITELIST: list = ["/health", "/ready", "/docs", "/openapi.json"]

    # ---- 日志 ----
    # 日志格式：json / text
    LOG_FORMAT: str = os.getenv("LOG_FORMAT", "json")
    # 慢请求阈值（秒），超过此值记录 WARNING
    SLOW_REQUEST_THRESHOLD: float = float(os.getenv("SLOW_REQUEST_THRESHOLD", "5.0"))
    # 不记录日志的路径
    LOG_SKIP_PATHS: list = ["/health", "/ready", "/static"]

    # ---- 健康检查 ----
    # Redis 健康检查超时（秒）
    HEALTH_REDIS_TIMEOUT: float = 2.0
    # LLM 健康检查（仅检查 API Key 是否配置，不实际调用）
    HEALTH_CHECK_LLM_KEY: bool = True


middleware_config = MiddlewareConfig()
```

---

## 三、限流中间件（Rate Limiting）

### 设计要点

- 算法：Redis 滑动窗口（INCR + EXPIRE），Redis 不可用时降级为内存计数器
- 粒度：按 client IP 限流，LLM 类路径更严格
- 响应：超限返回 429 + `Retry-After` header + JSON body
- 面试话术：「LLM 调用成本高（约 ¥0.01/次），必须做请求级限流防止恶意刷接口」

### `src/middleware/rate_limit.py`

```python
# src/middleware/rate_limit.py
"""
滑动窗口限流中间件

算法：Redis INCR + EXPIRE 实现固定窗口计数器
降级：Redis 不可用时使用内存 dict 计数（单进程有效）
粒度：按 client_ip 限流，LLM 路径更严格
"""
import time
import logging
from collections import defaultdict
from typing import Optional, Tuple

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.config.middleware_config import middleware_config
from src.core.request_context import get_trace_id

logger = logging.getLogger(__name__)

# LLM 类路径前缀（需要更严格限流）
LLM_PATH_PREFIXES = ("/api/v1/chat/chat", "/api/v1/chat/followup")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """滑动窗口限流中间件"""

    def __init__(self, app, redis_client=None):
        super().__init__(app)
        self.redis = redis_client
        # 内存降级计数器：{ip: [(timestamp, count)]}
        self._memory_counters: dict = defaultdict(list)

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # 白名单跳过
        if any(path.startswith(p) for p in middleware_config.RATE_LIMIT_WHITELIST):
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        is_llm_path = any(path.startswith(p) for p in LLM_PATH_PREFIXES)
        limit = middleware_config.RATE_LIMIT_LLM_PER_MINUTE if is_llm_path else middleware_config.RATE_LIMIT_PER_MINUTE
        window = middleware_config.RATE_LIMIT_WINDOW

        allowed, current_count, ttl = self._check_rate_limit(client_ip, limit, window, is_llm_path)

        if not allowed:
            logger.warning(
                f"限流触发: ip={client_ip}, path={path}, "
                f"count={current_count}/{limit}, trace_id={get_trace_id()}"
            )
            return JSONResponse(
                status_code=429,
                content={
                    "success": False,
                    "message": "请求过于频繁，请稍后再试",
                    "error": "RATE_LIMIT_EXCEEDED",
                    "trace_id": get_trace_id(),
                    "retry_after": ttl,
                },
                headers={"Retry-After": str(ttl)},
            )

        response = await call_next(request)
        # 注入限流信息到响应头（方便前端/调试）
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, limit - current_count))
        response.headers["X-RateLimit-Reset"] = str(ttl)
        return response

    def _check_rate_limit(
        self, client_ip: str, limit: int, window: int, is_llm: bool
    ) -> Tuple[bool, int, int]:
        """
        检查限流，返回 (是否放行, 当前计数, 剩余TTL秒)
        优先用 Redis，不可用时降级内存
        """
        key_suffix = "llm" if is_llm else "general"
        key = f"ratelimit:{client_ip}:{key_suffix}"

        # 尝试 Redis
        if self.redis:
            try:
                return self._check_redis(key, limit, window)
            except Exception as e:
                logger.warning(f"Redis 限流降级到内存: {e}")

        # 内存降级
        return self._check_memory(key, limit, window)

    def _check_redis(self, key: str, limit: int, window: int) -> Tuple[bool, int, int]:
        """Redis INCR + EXPIRE 固定窗口"""
        pipe = self.redis.pipeline()
        pipe.incr(key)
        pipe.ttl(key)
        results = pipe.execute()

        current_count = results[0]
        ttl = results[1]

        # 首次请求，设置过期时间
        if ttl == -1:
            self.redis.expire(key, window)
            ttl = window

        return (current_count <= limit, current_count, max(ttl, 1))

    def _check_memory(self, key: str, limit: int, window: int) -> Tuple[bool, int, int]:
        """内存计数器降级方案"""
        now = time.time()
        # 清理过期记录
        self._memory_counters[key] = [
            t for t in self._memory_counters[key] if now - t < window
        ]
        current_count = len(self._memory_counters[key])

        if current_count >= limit:
            oldest = self._memory_counters[key][0] if self._memory_counters[key] else now
            ttl = int(window - (now - oldest)) + 1
            return (False, current_count, max(ttl, 1))

        self._memory_counters[key].append(now)
        return (True, current_count + 1, window)

    @staticmethod
    def _get_client_ip(request: Request) -> str:
        """提取客户端 IP（支持反向代理）"""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        return request.client.host if request.client else "unknown"
```

---

## 四、超时中间件（Timeout）

### 设计要点

- 用 `asyncio.wait_for` 包装 `call_next`，超时抛 `asyncio.TimeoutError`
- LLM 路径给 120s，普通路径 30s
- 超时返回 504 Gateway Timeout + JSON body
- 面试话术：「LLM 调用可能 hang 住，没有超时兜底会导致连接池耗尽，拖垮整个服务」

### `src/middleware/timeout.py`

```python
# src/middleware/timeout.py
"""
请求超时中间件

对每个请求设置最大执行时间，超时返回 504。
LLM 类路径给更长超时（120s），普通路径 30s。
"""
import asyncio
import logging

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.config.middleware_config import middleware_config
from src.core.request_context import get_trace_id

logger = logging.getLogger(__name__)

# LLM 类路径前缀
LLM_PATH_PREFIXES = ("/api/v1/chat/chat", "/api/v1/chat/followup")


class TimeoutMiddleware(BaseHTTPMiddleware):
    """请求超时中间件"""

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # 白名单跳过
        if any(path.startswith(p) for p in middleware_config.TIMEOUT_WHITELIST):
            return await call_next(request)

        # 根据路径选择超时时间
        is_llm_path = any(path.startswith(p) for p in LLM_PATH_PREFIXES)
        timeout = (
            middleware_config.REQUEST_TIMEOUT_LLM
            if is_llm_path
            else middleware_config.REQUEST_TIMEOUT_DEFAULT
        )

        try:
            response = await asyncio.wait_for(call_next(request), timeout=timeout)
            return response
        except asyncio.TimeoutError:
            logger.error(
                f"请求超时: path={path}, timeout={timeout}s, trace_id={get_trace_id()}"
            )
            return JSONResponse(
                status_code=504,
                content={
                    "success": False,
                    "message": f"请求处理超时（{timeout}秒），请稍后重试",
                    "error": "REQUEST_TIMEOUT",
                    "trace_id": get_trace_id(),
                },
            )
```

---

## 五、结构化日志中间件

### 设计要点

- 替代当前 `request_context_middleware`，合并 trace_id 生成 + 请求审计
- 每个请求自动记录：method、path、status_code、latency_ms、client_ip、trace_id、user_id
- 输出 JSON 格式，方便 ELK/Loki 聚合
- 慢请求（>5s）自动标记 WARNING
- 面试话术：「生产环境日志必须结构化可检索，纯文本 grep 在百万级日志量下不可行」

### `src/middleware/logging_middleware.py`

```python
# src/middleware/logging_middleware.py
"""
结构化日志中间件

每个请求自动记录：
- method, path, status_code, latency_ms
- client_ip, trace_id, user_id
- 慢请求标记（>5s → WARNING）

输出 JSON 格式，方便 ELK / Loki / CloudWatch 聚合。
"""
import json
import time
import logging
import sys

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.config.middleware_config import middleware_config
from src.core.request_context import new_trace_id, get_trace_id, set_user_id

logger = logging.getLogger("access")


class StructuredJsonFormatter(logging.Formatter):
    """JSON 结构化日志格式器"""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # 合并 extra 字段
        if hasattr(record, "extra_data"):
            log_data.update(record.extra_data)
        return json.dumps(log_data, ensure_ascii=False)


def setup_structured_logging():
    """配置结构化日志（在 main.py 启动时调用一次）"""
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # 清除默认 handler
    root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)

    if middleware_config.LOG_FORMAT == "json":
        handler.setFormatter(StructuredJsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )

    root_logger.addHandler(handler)


class LoggingMiddleware(BaseHTTPMiddleware):
    """结构化请求日志中间件（替代原 request_context_middleware）"""

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # 静态资源 / 健康检查不记录
        if any(path.startswith(p) for p in middleware_config.LOG_SKIP_PATHS):
            trace_id = new_trace_id()
            response = await call_next(request)
            response.headers["X-Trace-Id"] = trace_id
            return response

        # 生成 trace_id
        trace_id = new_trace_id()
        start_time = time.time()

        # 提取 client_ip
        forwarded = request.headers.get("X-Forwarded-For")
        client_ip = (
            forwarded.split(",")[0].strip()
            if forwarded
            else (request.client.host if request.client else "unknown")
        )

        # 执行请求
        response = await call_next(request)

        # 计算耗时
        latency_ms = round((time.time() - start_time) * 1000, 2)
        status_code = response.status_code

        # 注入 trace_id 到响应头
        response.headers["X-Trace-Id"] = trace_id

        # 构建日志数据
        log_data = {
            "trace_id": trace_id,
            "method": request.method,
            "path": path,
            "status_code": status_code,
            "latency_ms": latency_ms,
            "client_ip": client_ip,
        }

        # 选择日志级别
        if status_code >= 500:
            level = logging.ERROR
        elif status_code >= 400:
            level = logging.WARNING
        elif latency_ms > middleware_config.SLOW_REQUEST_THRESHOLD * 1000:
            level = logging.WARNING
            log_data["slow_request"] = True
        else:
            level = logging.INFO

        # 输出日志
        record = logger.makeRecord(
            name="access",
            level=level,
            fn="",
            lno=0,
            msg=f"{request.method} {path} {status_code} {latency_ms}ms",
            args=(),
            exc_info=None,
        )
        record.extra_data = log_data
        logger.handle(record)

        return response
```

---

## 六、健康检查端点

### 设计要点

- `GET /health` — 存活探针（liveness），只要进程活着就返回 200
- `GET /ready` — 就绪探针（readiness），检查 Redis + LLM API Key
- K8s 部署标配，面试必问
- 面试话术：「liveness 失败 K8s 会重启 Pod，readiness 失败会从 Service 摘除流量」

### `src/api/health.py`

```python
# src/api/health.py
"""
健康检查端点

- GET /health  — 存活探针（liveness），进程活着就返回 200
- GET /ready   — 就绪探针（readiness），检查核心依赖
"""
import time
import logging
from typing import Dict, Any

from fastapi import APIRouter

from src.config.middleware_config import middleware_config

logger = logging.getLogger(__name__)

router = APIRouter(tags=["健康检查"])

# 服务启动时间
_start_time = time.time()


def _check_redis() -> Dict[str, Any]:
    """检查 Redis 连通性"""
    try:
        from src.dependencies import redis_cache
        if not redis_cache or not redis_cache.client:
            return {"status": "unavailable", "message": "Redis 未配置或未连接"}
        redis_cache.client.ping()
        return {"status": "healthy"}
    except Exception as e:
        return {"status": "unhealthy", "message": str(e)}


def _check_llm() -> Dict[str, Any]:
    """检查 LLM 可用性（仅检查 API Key，不实际调用）"""
    try:
        from src.dependencies import llm
        if not llm:
            return {"status": "unavailable", "message": "LLM 未初始化"}
        if not llm.api_key:
            return {"status": "degraded", "message": "DASHSCOPE_API_KEY 未配置"}
        return {"status": "healthy"}
    except Exception as e:
        return {"status": "unhealthy", "message": str(e)}


def _check_vector_store() -> Dict[str, Any]:
    """检查向量检索可用性"""
    try:
        from src.dependencies import hybrid_retriever
        if not hybrid_retriever:
            return {"status": "unavailable", "message": "检索器未初始化"}
        return {"status": "healthy"}
    except Exception as e:
        return {"status": "unhealthy", "message": str(e)}


@router.get("/health")
async def liveness():
    """
    存活探针 — 进程活着就返回 200
    K8s livenessProbe 使用
    """
    return {
        "status": "alive",
        "uptime_seconds": round(time.time() - _start_time, 1),
    }


@router.get("/ready")
async def readiness():
    """
    就绪探针 — 检查核心依赖是否就绪
    K8s readinessProbe 使用
    任一核心依赖 unhealthy → 返回 503
    """
    checks = {
        "redis": _check_redis(),
        "llm": _check_llm(),
        "vector_store": _check_vector_store(),
    }

    # 判断整体状态
    all_healthy = all(c["status"] in ("healthy", "degraded") for c in checks.values())
    overall = "ready" if all_healthy else "not_ready"
    status_code = 200 if all_healthy else 503

    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=status_code,
        content={
            "status": overall,
            "checks": checks,
            "uptime_seconds": round(time.time() - _start_time, 1),
        },
    )
```

---

## 七、异常体系扩展

### `src/core/exceptions.py` — 新增两个异常

```python
# 在现有异常类之后追加：

class RateLimitError(BaziAgentError):
    """请求限流"""
    def __init__(self, retry_after: int = 60):
        self.retry_after = retry_after
        super().__init__(
            f"请求过于频繁，请 {retry_after} 秒后重试",
            code="RATE_LIMIT_EXCEEDED",
            status_code=429,
        )


class RequestTimeoutError(BaziAgentError):
    """请求超时"""
    def __init__(self, timeout: float = 30):
        super().__init__(
            f"请求处理超时（{timeout}秒）",
            code="REQUEST_TIMEOUT",
            status_code=504,
        )
```

---

## 八、main.py 集成

### 改动点

```python
# src/main.py 改动摘要

# 1. 新增 import
from fastapi.middleware.gzip import GZipMiddleware
from src.middleware.rate_limit import RateLimitMiddleware
from src.middleware.timeout import TimeoutMiddleware
from src.middleware.logging_middleware import LoggingMiddleware, setup_structured_logging
from src.api.health import router as health_router

# 2. 在 lifespan 中初始化结构化日志
@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_structured_logging()
    logger.info("八字分析 Agent 正在启动...")
    # ... 原有逻辑不变 ...

# 3. 注册中间件（注意顺序：后注册的先执行）
# 执行顺序：GZip → Logging → RateLimit → Timeout → CORS → 路由

app.add_middleware(GZipMiddleware, minimum_size=1000)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 超时中间件
app.add_middleware(TimeoutMiddleware)

# 限流中间件（传入 Redis 客户端）
from src.dependencies import redis_cache
app.add_middleware(
    RateLimitMiddleware,
    redis_client=redis_cache.client if redis_cache else None,
)

# 结构化日志中间件（替代原 request_context_middleware）
app.add_middleware(LoggingMiddleware)

# 4. 删除原有的 request_context_middleware（已被 LoggingMiddleware 替代）

# 5. 注册健康检查路由
app.include_router(health_router)
```

### 中间件执行顺序说明

Starlette 中间件是**洋葱模型**，后注册的先执行（外层）：

```
请求进入 → LoggingMiddleware（记录开始时间）
         → RateLimitMiddleware（检查限流）
         → TimeoutMiddleware（设置超时）
         → CORS
         → GZip
         → 路由处理
         ← GZip（压缩响应）
         ← CORS
         ← TimeoutMiddleware
         ← RateLimitMiddleware（注入限流 header）
         ← LoggingMiddleware（记录耗时、状态码）
```

---

## 九、面试话术要点

### 限流
- 「为什么不用 slowapi？」→ 自己实现更灵活，能区分 LLM 路径和普通路径的限流阈值；Redis 不可用时自动降级内存计数器，保证可用性
- 「为什么用固定窗口而不是令牌桶？」→ 固定窗口实现简单、Redis 操作少（1次 INCR + 1次 EXPIRE），对于 API 限流场景足够；令牌桶更适合流量整形场景

### 超时
- 「为什么不在 LLM 层做超时？」→ 中间件层是兜底，防止任何环节（RAG 检索、数据库、序列化）hang 住；LLM 层可以额外做更细粒度的超时
- 「超时后请求还在执行吗？」→ `asyncio.wait_for` 会取消协程，但 DashScope SDK 的同步调用在线程池中，需要配合 `httpx` 的 timeout 参数才能真正中断

### 结构化日志
- 「为什么不用 structlog？」→ 项目已有 structlog 依赖，但自己实现 JSON Formatter 更轻量，且面试能展示对 logging 模块的理解
- 「日志量大怎么办？」→ 静态资源和健康检查路径跳过日志；生产环境可以调整 LOG_LEVEL 到 WARNING

### 健康检查
- 「liveness 和 readiness 的区别？」→ liveness 失败 K8s 重启 Pod（进程死了）；readiness 失败从 Service 摘除流量（依赖没准备好，但进程还活着）
- 「为什么 LLM 检查只看 API Key？」→ 实际调用 LLM 太慢（2-5s），健康检查要求毫秒级响应；API Key 存在是最基本的前置条件

---

## 十、验证方式

```bash
# 1. 启动服务
python -m src.main

# 2. 健康检查
curl http://localhost:8000/health
curl http://localhost:8000/ready

# 3. 限流测试（快速发 15 次请求）
for i in $(seq 1 15); do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -X POST http://localhost:8000/api/v1/chat/chat \
    -H "Content-Type: application/json" \
    -d '{"query": "你好", "user_id": "test"}'
done
# 预期：前 10 次 200，之后 429

# 4. 超时测试（需要 mock 一个慢接口）
# 观察日志中的 JSON 结构化输出

# 5. 响应头检查
curl -v http://localhost:8000/api/v1/chat/chat \
  -X POST -H "Content-Type: application/json" \
  -d '{"query": "你好", "user_id": "test"}'
# 预期 header 包含：
# X-Trace-Id: xxxxxxxxxxxx
# X-RateLimit-Limit: 10
# X-RateLimit-Remaining: 9
# X-RateLimit-Reset: 60
# Content-Encoding: gzip（如果响应 > 1000 bytes）
```
