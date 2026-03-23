# src/core/exceptions.py
"""统一异常体系 — 替代各处 HTTPException 的散乱使用"""


class BaziAgentError(Exception):
    """基础异常"""
    def __init__(self, message: str, code: str = "INTERNAL_ERROR", status_code: int = 500):
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(message)


class ValidationError(BaziAgentError):
    """输入验证错误"""
    def __init__(self, message: str):
        super().__init__(message, code="VALIDATION_ERROR", status_code=400)


class SessionNotFoundError(BaziAgentError):
    """会话不存在"""
    def __init__(self, conversation_id: str):
        super().__init__(f"会话不存在: {conversation_id}", code="SESSION_NOT_FOUND", status_code=404)


class ComponentNotInitializedError(BaziAgentError):
    """系统组件未初始化"""
    def __init__(self, component: str = "系统组件"):
        super().__init__(f"{component}未初始化", code="COMPONENT_NOT_INITIALIZED", status_code=500)


class LLMError(BaziAgentError):
    """LLM 调用错误"""
    def __init__(self, message: str):
        super().__init__(message, code="LLM_ERROR", status_code=502)


class SafetyError(BaziAgentError):
    """安全检查不通过"""
    def __init__(self, message: str = "输入包含敏感内容，无法处理"):
        super().__init__(message, code="SAFETY_CHECK_FAILED", status_code=400)


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
