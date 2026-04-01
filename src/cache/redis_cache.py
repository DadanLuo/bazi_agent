# src/cache/redis_cache.py
"""
Redis 缓存管理器 - 用于会话和八字结果缓存
"""

import json
import logging
from typing import Optional, Dict, Any, Union
from datetime import datetime
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None

logger = logging.getLogger(__name__)


class RedisCacheManager:
    """
    Redis 缓存管理器
    用于缓存八字分析结果和会话数据
    """

    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0, password: str = None):
        if REDIS_AVAILABLE:
            try:
                self.client = redis.Redis(host=host, port=port, db=db, password=password, decode_responses=True)
                # 测试连接
                self.client.ping()
                logger.info("Redis 连接成功")
            except Exception as e:
                logger.error(f"Redis 连接失败: {e}")
                self.client = None
        else:
            logger.warning("Redis 模块未安装，缓存功能将不可用")
            self.client = None

    def get(self, key: str) -> Optional[Union[Dict, str, int, float]]:
        """
        获取缓存值
        
        Args:
            key: 缓存键
            
        Returns:
            缓存值，如果不存在则返回 None
        """
        if not self.client:
            return None
        
        try:
            value = self.client.get(key)
            if value is not None:
                # 尝试解析为 JSON
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return value
            return None
        except Exception as e:
            logger.error(f"获取缓存失败 {key}: {e}")
            return None

    def set(self, key: str, value: Union[Dict, str, int, float], ttl: int = 3600) -> bool:
        """
        设置缓存值
        
        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间（秒）
            
        Returns:
            是否设置成功
        """
        if not self.client:
            return False
        
        try:
            # 如果是字典，序列化为 JSON
            if isinstance(value, dict):
                value = json.dumps(value, ensure_ascii=False)
            else:
                value = str(value)
            
            result = self.client.setex(key, ttl, value)
            return result
        except Exception as e:
            logger.error(f"设置缓存失败 {key}: {e}")
            return False

    def delete(self, key: str) -> bool:
        """
        删除缓存
        
        Args:
            key: 缓存键
            
        Returns:
            是否删除成功
        """
        if not self.client:
            return False
        
        try:
            result = self.client.delete(key)
            return result > 0
        except Exception as e:
            logger.error(f"删除缓存失败 {key}: {e}")
            return False

    def exists(self, key: str) -> bool:
        """
        检查缓存是否存在
        
        Args:
            key: 缓存键
            
        Returns:
            是否存在
        """
        if not self.client:
            return False
        
        try:
            return self.client.exists(key) > 0
        except Exception as e:
            logger.error(f"检查缓存失败 {key}: {e}")
            return False

    def get_bazi_result(self, birth_info) -> Optional[Dict[str, Any]]:
        """
        获取八字分析结果缓存
        
        Args:
            birth_info: 出生信息
            
        Returns:
            缓存的八字分析结果
        """
        if not self.client:
            return None
        
        # 生成缓存键
        cache_key = self._generate_bazi_cache_key(birth_info)
        return self.get(cache_key)

    def cache_bazi_result(self, birth_info, result: Dict[str, Any], ttl: int = 7200) -> bool:
        """
        缓存八字分析结果
        
        Args:
            birth_info: 出生信息
            result: 分析结果
            ttl: 过期时间
            
        Returns:
            是否缓存成功
        """
        if not self.client:
            return False
        
        cache_key = self._generate_bazi_cache_key(birth_info)
        
        # 添加时间戳
        cached_data = {
            "result": result,
            "timestamp": datetime.now().isoformat(),
            "ttl": ttl
        }
        
        return self.set(cache_key, cached_data, ttl)

    def _generate_bazi_cache_key(self, birth_info) -> str:
        """
        生成八字缓存键
        
        Args:
            birth_info: 出生信息
            
        Returns:
            缓存键字符串
        """
        # 基于出生信息生成唯一键
        key_parts = [
            str(birth_info.year),
            str(birth_info.month), 
            str(birth_info.day),
            str(birth_info.hour),
            str(birth_info.minute),
            birth_info.gender,
            str(getattr(birth_info, 'longitude', 0)),
            str(getattr(birth_info, 'latitude', 0))
        ]
        key_str = ":".join(key_parts)
        return f"bazi:result:{key_str}"

    def get_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """
        获取会话缓存
        
        Args:
            conversation_id: 会话ID
            
        Returns:
            会话数据
        """
        if not self.client:
            return None
        
        key = f"conversation:{conversation_id}"
        return self.get(key)

    def cache_conversation(self, conversation_id: str, data: Dict[str, Any], ttl: int = 86400) -> bool:
        """
        缓存会话数据
        
        Args:
            conversation_id: 会话ID
            data: 会话数据
            ttl: 过期时间
            
        Returns:
            是否缓存成功
        """
        if not self.client:
            return False
        
        key = f"conversation:{conversation_id}"
        return self.set(key, data, ttl)


__all__ = ["RedisCacheManager"]