# src/core/request_context.py
"""
请求上下文追踪 — 基于 contextvars，每个请求自动生成 trace_id
"""
import uuid
from contextvars import ContextVar

_trace_id: ContextVar[str] = ContextVar("trace_id", default="")
_user_id: ContextVar[str] = ContextVar("user_id", default="default")
_agent_id: ContextVar[str] = ContextVar("agent_id", default="bazi")


def get_trace_id() -> str:
    return _trace_id.get()


def set_trace_id(trace_id: str) -> None:
    _trace_id.set(trace_id)


def get_user_id() -> str:
    return _user_id.get()


def set_user_id(user_id: str) -> None:
    _user_id.set(user_id)


def get_agent_id() -> str:
    return _agent_id.get()


def set_agent_id(agent_id: str) -> None:
    _agent_id.set(agent_id)


def new_trace_id() -> str:
    """生成并设置新的 trace_id"""
    tid = uuid.uuid4().hex[:12]
    _trace_id.set(tid)
    return tid
