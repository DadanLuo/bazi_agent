# src/middleware/logging_middleware.py
"""
==============================================================================
结构化日志中间件
==============================================================================

功能说明：
    本模块实现了结构化日志中间件，自动记录每个请求的详细信息。
    输出 JSON 格式，方便 ELK / Loki / CloudWatch 等日志系统聚合。

记录内容：
    - method: HTTP 方法
    - path: 请求路径
    - status_code: 状态码
    - latency_ms: 响应时间（毫秒）
    - client_ip: 客户端 IP
    - trace_id: 请求追踪 ID

日志级别：
    - ERROR: 状态码 >= 500
    - WARNING: 状态码 >= 400 或响应时间 > 5s
    - INFO: 其他情况

==============================================================================
"""

import json
import time
import logging
import sys
from typing import Optional, Sequence

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.config.middleware_config import middleware_config
from src.core.request_context import new_trace_id

logger = logging.getLogger("access")


class StructuredJsonFormatter(logging.Formatter):
    """
    ==============================================================================
    JSON 结构化日志格式器
    ==============================================================================
    
    功能说明：
        将日志记录格式化为 JSON 格式，方便日志系统聚合和分析。
    
    JSON 格式：
        {
            "timestamp": "2024-01-01 00:00:00,000",
            "level": "INFO",
            "logger": "access",
            "message": "GET /api/v1/chat/chat 200 123.45ms",
            "trace_id": "xxx",
            "method": "GET",
            "path": "/api/v1/chat/chat",
            "status_code": 200,
            "latency_ms": 123.45,
            "client_ip": "127.0.0.1"
        }
    
    ==============================================================================
    """

    def format(self, record: logging.LogRecord) -> str:
        """
        ==============================================================================
        格式化日志记录
        ==============================================================================
        
        功能说明：
            将日志记录格式化为 JSON 字符串。
        
        参数说明：
            record (logging.LogRecord): 日志记录对象
        
        返回值：
            str: JSON 格式的日志字符串
        
        ==============================================================================
        """
        log_data = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "extra_data"):
            log_data.update(record.extra_data)
        return json.dumps(log_data, ensure_ascii=False)


def setup_structured_logging():
    """
    ==============================================================================
    配置结构化日志（在 main.py 启动时调用一次）
    ==============================================================================
    
    功能说明：
        配置全局日志系统，使用结构化 JSON 格式输出日志。
    
    配置内容：
        1. 设置根日志级别为 INFO
        2. 清除现有处理器
        3. 添加控制台输出处理器
        4. 根据配置选择日志格式器
    
    ==============================================================================
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

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
    """
    ==============================================================================
    结构化请求日志中间件（替代原 request_context_middleware）
    ==============================================================================
    
    功能说明：
        结构化请求日志中间件，自动记录每个请求的详细信息。
        输出 JSON 格式，方便日志系统聚合和分析。
    
    核心方法：
        - dispatch(): 处理请求
    
    使用场景：
        - 请求追踪
        - 性能监控
        - 错误分析
        - 用户行为分析
    
    ==============================================================================
    """

    def __init__(
        self,
        app,
        slow_request_threshold: Optional[float] = None,
        skip_paths: Optional[Sequence[str]] = None,
    ):
        super().__init__(app)
        self.slow_request_threshold = (
            slow_request_threshold
            if slow_request_threshold is not None
            else middleware_config.SLOW_REQUEST_THRESHOLD
        )
        self.skip_paths = tuple(skip_paths or middleware_config.LOG_SKIP_PATHS)

    async def dispatch(self, request: Request, call_next) -> Response:
        """
        ==============================================================================
        处理请求
        ==============================================================================
        
        功能说明：
            处理每个 HTTP 请求，记录详细的请求信息。
        
        参数说明：
            request (Request): FastAPI 请求对象
            call_next: 下一个中间件或路由处理函数
        
        返回值：
            Response: HTTP 响应对象
        
        处理流程：
            1. 检查请求路径是否需要跳过记录
            2. 生成 trace_id
            3. 记录请求开始时间
            4. 处理请求
            5. 计算响应时间
            6. 记录日志
        
        日志记录：
            - trace_id: 请求追踪 ID
            - method: HTTP 方法
            - path: 请求路径
            - status_code: 状态码
            - latency_ms: 响应时间（毫秒）
            - client_ip: 客户端 IP
        
        慢请求标记：
            - 响应时间 > 5s 标记为慢请求
        
        ==============================================================================
        """
        path = request.url.path

        # 静态资源 / 健康检查不记录详细日志
        if any(path.startswith(p) for p in self.skip_paths):
            trace_id = new_trace_id()
            response = await call_next(request)
            response.headers["X-Trace-Id"] = trace_id
            return response

        # 生成 trace_id
        trace_id = new_trace_id()
        start_time = time.time()

        # 提取客户端 IP
        forwarded = request.headers.get("X-Forwarded-For")
        client_ip = (
            forwarded.split(",")[0].strip()
            if forwarded
            else (request.client.host if request.client else "unknown")
        )

        # 处理请求
        response = await call_next(request)

        # 计算响应时间
        latency_ms = round((time.time() - start_time) * 1000, 2)
        status_code = response.status_code

        # 添加 trace_id 到响应头
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

        # 确定日志级别
        if status_code >= 500:
            level = logging.ERROR
        elif status_code >= 400:
            level = logging.WARNING
        elif latency_ms > self.slow_request_threshold * 1000:
            level = logging.WARNING
            log_data["slow_request"] = True
        else:
            level = logging.INFO

        # 创建日志记录
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
