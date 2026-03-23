# src/middleware/logging_middleware.py
"""
结构化日志中间件

每个请求自动记录：
- method, path, status_code, latency_ms
- client_ip, trace_id
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
from src.core.request_context import new_trace_id

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
        if hasattr(record, "extra_data"):
            log_data.update(record.extra_data)
        return json.dumps(log_data, ensure_ascii=False)


def setup_structured_logging():
    """配置结构化日志（在 main.py 启动时调用一次）"""
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
    """结构化请求日志中间件（替代原 request_context_middleware）"""

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # 静态资源 / 健康检查不记录详细日志
        if any(path.startswith(p) for p in middleware_config.LOG_SKIP_PATHS):
            trace_id = new_trace_id()
            response = await call_next(request)
            response.headers["X-Trace-Id"] = trace_id
            return response

        trace_id = new_trace_id()
        start_time = time.time()

        forwarded = request.headers.get("X-Forwarded-For")
        client_ip = (
            forwarded.split(",")[0].strip()
            if forwarded
            else (request.client.host if request.client else "unknown")
        )

        response = await call_next(request)

        latency_ms = round((time.time() - start_time) * 1000, 2)
        status_code = response.status_code

        response.headers["X-Trace-Id"] = trace_id

        log_data = {
            "trace_id": trace_id,
            "method": request.method,
            "path": path,
            "status_code": status_code,
            "latency_ms": latency_ms,
            "client_ip": client_ip,
        }

        if status_code >= 500:
            level = logging.ERROR
        elif status_code >= 400:
            level = logging.WARNING
        elif latency_ms > middleware_config.SLOW_REQUEST_THRESHOLD * 1000:
            level = logging.WARNING
            log_data["slow_request"] = True
        else:
            level = logging.INFO

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
