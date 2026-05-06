# src/middleware/rate_limit.py
"""
==============================================================================
滑动窗口限流中间件
==============================================================================

功能说明：
    本模块实现了基于 Redis 的滑动窗口限流中间件，用于保护系统免受
    过多请求的冲击。支持按客户端 IP 限流，LLM 路径采用更严格的限制。

算法说明：
    - Redis INCR + EXPIRE 固定窗口计数器
    - 降级方案：Redis 不可用时使用内存 dict 计数（单进程有效）

限流粒度：
    - 按 client_ip 限流
    - LLM 路径更严格（ RATE_LIMIT_LLM_PER_MINUTE ）
    - 普通路径较宽松（ RATE_LIMIT_PER_MINUTE ）

==============================================================================
"""

import time
import logging
from collections import defaultdict
from typing import Tuple, Optional, Sequence

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.config.middleware_config import middleware_config
from src.core.request_context import get_trace_id

logger = logging.getLogger(__name__)

# LLM 路径前缀
LLM_PATH_PREFIXES = (
    "/api/v1/chat/chat",
    "/api/v1/chat/followup",
    "/api/v1/bazi/analyze",
    "/api/v1/bazi/followup",
    "/api/v1/tarot/analyze",
    "/api/v1/tarot/followup",
)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    ==============================================================================
    滑动窗口限流中间件
    ==============================================================================
    
    功能说明：
        基于 Redis 的滑动窗口限流中间件，用于保护系统免受过多请求的冲击。
        支持按客户端 IP 限流，LLM 路径采用更严格的限制。
    
    核心方法：
        - dispatch(): 处理请求
        - _check_rate_limit(): 检查限流
        - _check_redis(): Redis 限流检查
        - _check_memory(): 内存限流检查（降级方案）
        - _get_client_ip(): 提取客户端 IP
    
    使用场景：
        - 防止 API 滥用
        - 保护后端服务
        - 控制 LLM 调用频率
    
    ==============================================================================
    """

    def __init__(
        self,
        app,
        requests_per_minute: Optional[int] = None,
        llm_requests_per_minute: Optional[int] = None,
        whitelist: Optional[Sequence[str]] = None,
        redis_client=None,
    ):
        """
        ==============================================================================
        初始化限流中间件
        ==============================================================================
        
        功能说明：
            初始化限流中间件，配置 Redis 客户端和内存计数器。
        
        参数说明：
            app: FastAPI 应用实例
            redis_client: Redis 客户端（可选）
        
        ==============================================================================
        """
        super().__init__(app)
        self.redis = redis_client
        self._memory_counters: dict = defaultdict(list)
        self.requests_per_minute = (
            requests_per_minute
            if requests_per_minute is not None
            else middleware_config.RATE_LIMIT_PER_MINUTE
        )
        self.llm_requests_per_minute = (
            llm_requests_per_minute
            if llm_requests_per_minute is not None
            else middleware_config.RATE_LIMIT_LLM_PER_MINUTE
        )
        self.whitelist = tuple(whitelist or middleware_config.RATE_LIMIT_WHITELIST)
        self.window = middleware_config.RATE_LIMIT_WINDOW

    async def dispatch(self, request: Request, call_next) -> Response:
        """
        ==============================================================================
        处理请求
        ==============================================================================
        
        功能说明：
            处理每个 HTTP 请求，检查是否超过限流限制。
        
        参数说明：
            request (Request): FastAPI 请求对象
            call_next: 下一个中间件或路由处理函数
        
        返回值：
            Response: HTTP 响应对象
        
        处理流程：
            1. 检查请求路径是否在白名单中
            2. 提取客户端 IP
            3. 判断是否为 LLM 路径
            4. 检查限流
            5. 如果超过限制，返回 429 错误
            6. 否则，继续处理请求
        
        限流响应头：
            - X-RateLimit-Limit: 限流上限
            - X-RateLimit-Remaining: 剩余请求数
            - X-RateLimit-Reset: 重置时间（秒）
        
        ==============================================================================
        """
        path = request.url.path

        # 检查请求路径是否在白名单中
        if any(path.startswith(p) for p in self.whitelist):
            return await call_next(request)

        # 提取客户端 IP
        client_ip = self._get_client_ip(request)
        # 判断是否为 LLM 路径
        is_llm_path = any(path.startswith(p) for p in LLM_PATH_PREFIXES)
        # 获取限流配置
        limit = (
            self.llm_requests_per_minute
            if is_llm_path
            else self.requests_per_minute
        )
        window = self.window

        # 检查限流
        allowed, current_count, ttl = self._check_rate_limit(
            client_ip, limit, window, is_llm_path
        )

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

        # 继续处理请求
        response = await call_next(request)
        # 添加限流响应头
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, limit - current_count))
        response.headers["X-RateLimit-Reset"] = str(ttl)
        return response

    def _check_rate_limit(
        self, client_ip: str, limit: int, window: int, is_llm: bool
    ) -> Tuple[bool, int, int]:
        """
        ==============================================================================
        检查限流，返回 (是否放行, 当前计数, 剩余TTL秒)
        ==============================================================================
        
        功能说明：
            检查客户端 IP 的请求频率是否超过限制。
        
        参数说明：
            client_ip (str): 客户端 IP
            limit (int): 限流上限
            window (int): 时间窗口（秒）
            is_llm (bool): 是否为 LLM 路径
        
        返回值：
            Tuple[bool, int, int]: (是否放行, 当前计数, 剩余TTL秒)
        
        ==============================================================================
        """
        key_suffix = "llm" if is_llm else "general"
        key = f"ratelimit:{client_ip}:{key_suffix}"

        if self.redis:
            try:
                return self._check_redis(key, limit, window)
            except Exception as e:
                logger.warning(f"Redis 限流降级到内存: {e}")

        return self._check_memory(key, limit, window)

    def _check_redis(self, key: str, limit: int, window: int) -> Tuple[bool, int, int]:
        """
        ==============================================================================
        Redis INCR + EXPIRE 固定窗口
        ==============================================================================
        
        功能说明：
            使用 Redis 的 INCR 和 EXPIRE 命令实现固定窗口计数器。
        
        参数说明：
            key (str): Redis 键
            limit (int): 限流上限
            window (int): 时间窗口（秒）
        
        返回值：
            Tuple[bool, int, int]: (是否放行, 当前计数, 剩余TTL秒)
        
        算法说明：
            1. 使用 INCR 命令增加计数
            2. 使用 TTL 命令获取剩余生存时间
            3. 如果 TTL 为 -1（未设置过期时间），设置过期时间
            4. 检查计数是否超过限制
        
        ==============================================================================
        """
        pipe = self.redis.pipeline()
        pipe.incr(key)
        pipe.ttl(key)
        results = pipe.execute()

        current_count = results[0]
        ttl = results[1]

        if ttl == -1:
            self.redis.expire(key, window)
            ttl = window

        return (current_count <= limit, current_count, max(ttl, 1))

    def _check_memory(self, key: str, limit: int, window: int) -> Tuple[bool, int, int]:
        """
        ==============================================================================
        内存计数器降级方案
        ==============================================================================
        
        功能说明：
            当 Redis 不可用时，使用内存字典实现计数器。
            注意：此方案仅在单进程环境下有效。
        
        参数说明：
            key (str): 计数器键
            limit (int): 限流上限
            window (int): 时间窗口（秒）
        
        返回值：
            Tuple[bool, int, int]: (是否放行, 当前计数, 剩余TTL秒)
        
        算法说明：
            1. 清理过期的时间戳
            2. 计算当前请求数
            3. 如果超过限制，计算剩余时间
            4. 否则，记录当前请求时间
        
        ==============================================================================
        """
        now = time.time()
        # 清理过期的时间戳
        self._memory_counters[key] = [
            t for t in self._memory_counters[key] if now - t < window
        ]
        current_count = len(self._memory_counters[key])

        if current_count >= limit:
            # 超过限制，计算剩余时间
            oldest = self._memory_counters[key][0] if self._memory_counters[key] else now
            ttl = int(window - (now - oldest)) + 1
            return (False, current_count, max(ttl, 1))

        # 记录当前请求时间
        self._memory_counters[key].append(now)
        return (True, current_count + 1, window)

    @staticmethod
    def _get_client_ip(request: Request) -> str:
        """
        ==============================================================================
        提取客户端 IP（支持反向代理）
        ==============================================================================
        
        功能说明：
            从请求头中提取客户端 IP，支持反向代理环境。
        
        参数说明：
            request (Request): FastAPI 请求对象
        
        返回值：
            str: 客户端 IP
        
        提取顺序：
            1. X-Forwarded-For 头（取第一个 IP）
            2. X-Real-IP 头
            3. request.client.host
        
        ==============================================================================
        """
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        return request.client.host if request.client else "unknown"
