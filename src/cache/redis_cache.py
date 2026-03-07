"""
Redis 缓存管理器
提供高性能的缓存服务，支持八字分析结果缓存和会话缓存
"""
import json
import logging
from typing import Any, Optional, Dict
from datetime import timedelta
from functools import wraps

try:
    import redis
    from redis.exceptions import RedisError
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None
    RedisError = Exception

logger = logging.getLogger(__name__)


class RedisCacheManager:
    """
    Redis 缓存管理器
    
    提供以下功能：
    - 八字分析结果缓存
    - 会话数据缓存
    - 检索结果缓存
    """
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
        decode_responses: bool = True,
        default_ttl: int = 3600,  # 默认1小时
        enable_cache: bool = True
    ):
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.decode_responses = decode_responses
        self.default_ttl = default_ttl
        self.enable_cache = enable_cache
        self._client: Optional[redis.Redis] = None
        
    @property
    def client(self) -> Optional[redis.Redis]:
        """获取Redis客户端连接"""
        if not REDIS_AVAILABLE:
            logger.warning("Redis 未安装，请运行: pip install redis")
            return None
            
        if not self.enable_cache:
            return None
            
        if self._client is None:
            try:
                self._client = redis.Redis(
                    host=self.host,
                    port=self.port,
                    db=self.db,
                    password=self.password,
                    decode_responses=self.decode_responses,
                    socket_timeout=5,
                    socket_connect_timeout=5,
                    retry_on_timeout=True
                )
                # 测试连接
                self._client.ping()
                logger.info("✅ Redis 连接成功")
            except RedisError as e:
                logger.error(f"❌ Redis 连接失败: {e}")
                self._client = None
                
        return self._client
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存数据"""
        if not self.client:
            return None
            
        try:
            value = self.client.get(key)
            if value:
                logger.debug(f"缓存命中: {key}")
                return json.loads(value)
            return None
        except RedisError as e:
            logger.error(f"缓存读取失败: {e}")
            return None
    
    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> bool:
        """设置缓存数据"""
        if not self.client:
            return False
            
        ttl = ttl or self.default_ttl
        
        try:
            self.client.setex(
                key,
                timedelta(seconds=ttl),
                json.dumps(value, ensure_ascii=False)
            )
            logger.debug(f"缓存已设置: {key}, TTL: {ttl}s")
            return True
        except RedisError as e:
            logger.error(f"缓存设置失败: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """删除缓存数据"""
        if not self.client:
            return False
            
        try:
            self.client.delete(key)
            return True
        except RedisError as e:
            logger.error(f"缓存删除失败: {e}")
            return False
    
    def exists(self, key: str) -> bool:
        """检查缓存是否存在"""
        if not self.client:
            return False
            
        try:
            return self.client.exists(key) > 0
        except RedisError as e:
            logger.error(f"缓存检查失败: {e}")
            return False
    
    def get_or_set(
        self,
        key: str,
        factory: callable,
        ttl: Optional[int] = None
    ) -> Any:
        """获取缓存，如果不存在则调用factory生成并缓存"""
        value = self.get(key)
        if value is not None:
            return value
            
        value = factory()
        self.set(key, value, ttl)
        return value
    
    # 八字分析缓存相关方法
    def cache_bazi_result(
        self,
        birth_info: Dict[str, Any],
        result: Dict[str, Any],
        ttl: int = 7200  # 默认2小时
    ) -> bool:
        """缓存八字分析结果"""
        key = self._build_bazi_cache_key(birth_info)
        return self.set(key, result, ttl)
    
    def get_bazi_result(
        self,
        birth_info: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """获取缓存的八字分析结果"""
        key = self._build_bazi_cache_key(birth_info)
        return self.get(key)
    
    def _build_bazi_cache_key(self, birth_info: Dict[str, Any]) -> str:
        """构建八字缓存键"""
        # 提取关键信息生成唯一键
        year = birth_info.get("year", 0)
        month = birth_info.get("month", 0)
        day = birth_info.get("day", 0)
        hour = birth_info.get("hour", 0)
        gender = birth_info.get("gender", "unknown")
        
        # 简单的键格式：bazi:year_month_day_hour_gender
        return f"bazi:{year}_{month}_{day}_{hour}_{gender}"
    
    # 会话缓存相关方法
    def cache_conversation(
        self,
        conversation_id: str,
        messages: list,
        ttl: int = 86400  # 默认24小时
    ) -> bool:
        """缓存会话消息"""
        key = f"conversation:{conversation_id}"
        return self.set(key, {"messages": messages}, ttl)
    
    def get_conversation(
        self,
        conversation_id: str
    ) -> Optional[Dict[str, Any]]:
        """获取会话消息"""
        key = f"conversation:{conversation_id}"
        data = self.get(key)
        return data.get("messages") if data else None
    
    # 检索结果缓存
    def cache_retrieval(
        self,
        query: str,
        results: list,
        ttl: int = 300  # 默认5分钟
    ) -> bool:
        """缓存检索结果"""
        key = f"retrieval:{self._hash_query(query)}"
        return self.set(key, {"results": results}, ttl)
    
    def get_retrieval(
        self,
        query: str
    ) -> Optional[Dict[str, Any]]:
        """获取缓存的检索结果"""
        key = f"retrieval:{self._hash_query(query)}"
        data = self.get(key)
        return data.get("results") if data else None
    
    def _hash_query(self, query: str) -> str:
        """对查询进行哈希处理"""
        import hashlib
        return hashlib.md5(query.encode()).hexdigest()[:16]
    
    # 批量操作
    def clear_by_pattern(self, pattern: str) -> int:
        """清除匹配模式的所有缓存"""
        if not self.client:
            return 0
            
        try:
            keys = self.client.keys(pattern)
            if keys:
                count = self.client.delete(*keys)
                logger.info(f"清除缓存: {len(keys)} 个键, 删除 {count} 个")
                return count
            return 0
        except RedisError as e:
            logger.error(f"批量清除缓存失败: {e}")
            return 0
    
    # 统计信息
    def get_stats(self) -> Dict[str, Any]:
        """获取Redis统计信息"""
        if not self.client:
            return {"status": "disabled"}
            
        try:
            info = self.client.info("memory")
            return {
                "status": "connected",
                "used_memory_human": info.get("used_memory_human", "N/A"),
                "connected_clients": info.get("connected_clients", 0),
                "db_keys": self.client.dbsize()
            }
        except RedisError as e:
            return {"status": "error", "error": str(e)}


# 全局缓存管理器实例
cache_manager = RedisCacheManager()


def cached(ttl: Optional[int] = None, key_prefix: str = ""):
    """
    缓存装饰器
    
    使用示例:
    @cached(ttl=3600, key_prefix="bazi")
    def analyze_bazi(birth_info):
        ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not cache_manager.client:
                return func(*args, **kwargs)
                
            # 构建缓存键
            cache_key = f"{key_prefix}:{func.__name__}:{str(args)}:{str(sorted(kwargs.items()))}"
            
            # 尝试从缓存获取
            cached_value = cache_manager.get(cache_key)
            if cached_value is not None:
                return cached_value
                
            # 执行函数并缓存结果
            result = func(*args, **kwargs)
            cache_manager.set(cache_key, result, ttl)
            return result
            
        return wrapper
    return decorator


def async_cached(ttl: Optional[int] = None, key_prefix: str = ""):
    """
    异步缓存装饰器
    
    使用示例:
    @async_cached(ttl=3600, key_prefix="bazi")
    async def analyze_bazi(birth_info):
        ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if not cache_manager.client:
                return await func(*args, **kwargs)
                
            # 构建缓存键
            cache_key = f"{key_prefix}:{func.__name__}:{str(args)}:{str(sorted(kwargs.items()))}"
            
            # 尝试从缓存获取
            cached_value = cache_manager.get(cache_key)
            if cached_value is not None:
                return cached_value
                
            # 执行函数并缓存结果
            result = await func(*args, **kwargs)
            cache_manager.set(cache_key, result, ttl)
            return result
            
        return wrapper
    return decorator
