# src/middleware/rate_limit.py
"""
滑动窗口限流中间件

算法：Redis INCR + EXPIRE 固定窗口计数器
降级：Redis 不可用时使用内存 dict 计数（单进程有效）
粒度：按 client_ip 限流，LLM 路径更严格
"""
import time
import logging
from collections import defaultdict
from typing import Tuple, Optional

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.config.middleware_config import middleware_config
from src.core.request_context import get_trace_id

logger = logging.getLogger(__name__)

LLM_PATH_PREFIXES = ("/api/v1/chat/chat", "/api/v1/chat/followup")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """滑动窗口限流中间件"""

    def __init__(self, app, redis_client=None):
        super().__init__(app)
        self.redis = redis_client
        self._memory_counters: dict = defaultdict(list)

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        if any(path.startswith(p) for p in middleware_config.RATE_LIMIT_WHITELIST):
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        is_llm_path = any(path.startswith(p) for p in LLM_PATH_PREFIXES)
        limit = (
            middleware_config.RATE_LIMIT_LLM_PER_MINUTE
            if is_llm_path
            else middleware_config.RATE_LIMIT_PER_MINUTE
        )
        window = middleware_config.RATE_LIMIT_WINDOW

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

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, limit - current_count))
        response.headers["X-RateLimit-Reset"] = str(ttl)
        return response

    def _check_rate_limit(
        self, client_ip: str, limit: int, window: int, is_llm: bool
    ) -> Tuple[bool, int, int]:
        """检查限流，返回 (是否放行, 当前计数, 剩余TTL秒)"""
        key_suffix = "llm" if is_llm else "general"
        key = f"ratelimit:{client_ip}:{key_suffix}"

        if self.redis:
            try:
                return self._check_redis(key, limit, window)
            except Exception as e:
                logger.warning(f"Redis 限流降级到内存: {e}")

        return self._check_memory(key, limit, window)

    def _check_redis(self, key: str, limit: int, window: int) -> Tuple[bool, int, int]:
        """Redis INCR + EXPIRE 固定窗口"""
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
        """内存计数器降级方案"""
        now = time.time()
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
