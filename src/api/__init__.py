# src/api/__init__.py
"""API模块"""
from .bazi_api import router as bazi_router
from .chat_api import router as chat_router

__all__ = [
    "bazi_router",
    "chat_router"
]
