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

LLM_PATH_PREFIXES = ("/api/v1/chat/chat", "/api/v1/chat/followup")


class TimeoutMiddleware(BaseHTTPMiddleware):
    """请求超时中间件"""

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        if any(path.startswith(p) for p in middleware_config.TIMEOUT_WHITELIST):
            return await call_next(request)

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
