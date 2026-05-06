# src/middleware/timeout.py
"""
==============================================================================
请求超时中间件
==============================================================================

功能说明：
    本模块实现了请求超时中间件，对每个请求设置最大执行时间。
    超时后返回 504 状态码，防止请求长时间占用系统资源。

超时配置：
    - LLM 类路径：120 秒（REQUEST_TIMEOUT_LLM）
    - 普通路径：30 秒（REQUEST_TIMEOUT_DEFAULT）

==============================================================================
"""

import asyncio
import logging

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


class TimeoutMiddleware(BaseHTTPMiddleware):
    """
    ==============================================================================
    请求超时中间件
    ==============================================================================
    
    功能说明：
        请求超时中间件，对每个请求设置最大执行时间。
        超时后返回 504 状态码，防止请求长时间占用系统资源。
    
    核心方法：
        - dispatch(): 处理请求
    
    使用场景：
        - 防止请求长时间占用系统资源
        - 提高系统稳定性
        - 改善用户体验（明确的超时反馈）
    
    ==============================================================================
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        """
        ==============================================================================
        处理请求
        ==============================================================================
        
        功能说明：
            处理每个 HTTP 请求，设置最大执行时间。
        
        参数说明：
            request (Request): FastAPI 请求对象
            call_next: 下一个中间件或路由处理函数
        
        返回值：
            Response: HTTP 响应对象
        
        处理流程：
            1. 检查请求路径是否在白名单中
            2. 判断是否为 LLM 路径
            3. 获取超时配置
            4. 使用 asyncio.wait_for 设置超时
            5. 如果超时，返回 504 错误
        
        超时响应：
            - 状态码：504 Gateway Timeout
            - 错误码：REQUEST_TIMEOUT
            - 消息：包含超时时间的友好提示
        
        ==============================================================================
        """
        path = request.url.path

        # 检查请求路径是否在白名单中
        if any(path.startswith(p) for p in middleware_config.TIMEOUT_WHITELIST):
            return await call_next(request)

        # 判断是否为 LLM 路径
        is_llm_path = any(path.startswith(p) for p in LLM_PATH_PREFIXES)
        # 获取超时配置
        timeout = (
            middleware_config.REQUEST_TIMEOUT_LLM
            if is_llm_path
            else middleware_config.REQUEST_TIMEOUT_DEFAULT
        )

        try:
            # 使用 asyncio.wait_for 设置超时
            response = await asyncio.wait_for(call_next(request), timeout=timeout)
            return response
        except asyncio.TimeoutError:
            # 记录超时日志
            logger.error(
                f"请求超时: path={path}, timeout={timeout}s, trace_id={get_trace_id()}"
            )
            # 返回 504 错误
            return JSONResponse(
                status_code=504,
                content={
                    "success": False,
                    "message": f"请求处理超时（{timeout}秒），请稍后重试",
                    "error": "REQUEST_TIMEOUT",
                    "trace_id": get_trace_id(),
                },
            )
