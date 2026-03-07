"""
缓存模块
"""
from .redis_cache import cache_manager, RedisCacheManager, cached, async_cached

__all__ = ["cache_manager", "RedisCacheManager", "cached", "async_cached"]
