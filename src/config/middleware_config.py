# src/config/middleware_config.py
"""中间件配置 — 集中管理，支持环境变量覆盖"""
import os


class MiddlewareConfig:
    """中间件配置"""

    # ---- 限流 ----
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30"))
    RATE_LIMIT_LLM_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_LLM_PER_MINUTE", "10"))
    RATE_LIMIT_WINDOW: int = 60
    RATE_LIMIT_WHITELIST: list = ["/health", "/ready", "/docs", "/openapi.json", "/static"]

    # ---- 超时 ----
    REQUEST_TIMEOUT_DEFAULT: float = float(os.getenv("REQUEST_TIMEOUT_DEFAULT", "30"))
    REQUEST_TIMEOUT_LLM: float = float(os.getenv("REQUEST_TIMEOUT_LLM", "120"))
    TIMEOUT_WHITELIST: list = ["/health", "/ready", "/docs", "/openapi.json"]

    # ---- 日志 ----
    LOG_FORMAT: str = os.getenv("LOG_FORMAT", "json")
    SLOW_REQUEST_THRESHOLD: float = float(os.getenv("SLOW_REQUEST_THRESHOLD", "5.0"))
    LOG_SKIP_PATHS: list = ["/health", "/ready", "/static"]

    # ---- 健康检查 ----
    HEALTH_REDIS_TIMEOUT: float = 2.0
    HEALTH_CHECK_LLM_KEY: bool = True


middleware_config = MiddlewareConfig()
