"""
==============================================================================
结果缓存
==============================================================================

功能说明：
    本模块提供了结果缓存功能，用于缓存检索结果，避免重复检索相同的查询。

==============================================================================
"""

import logging
import time
import hashlib
from typing import Dict, Any, Optional, List
from collections import OrderedDict
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """
    ==============================================================================
    缓存条目
    ==============================================================================
    
    功能说明：
        表示缓存中的一个条目。
    
    属性：
        value: 缓存值
        timestamp: 创建时间
        ttl: 生存时间（秒）
    
    ==============================================================================
    """
    value: Any
    timestamp: float
    ttl: int = 86400  # 默认 24 小时
    
    @property
    def is_expired(self) -> bool:
        """检查是否过期"""
        return time.time() > self.timestamp + self.ttl


class ResultCache:
    """
    ==============================================================================
    结果缓存
    ==============================================================================
    
    功能说明：
        缓存检索结果，避免重复检索相同的查询。
    
    缓存键：
        查询文本 + 检索参数的哈希值
    
    TTL：
        24 小时
    
    ==============================================================================
    """

    def __init__(self, max_size: int = 5000):
        """
        ==============================================================================
        初始化结果缓存
        ==============================================================================
        
        参数说明：
            max_size: 最大缓存大小
        
        ==============================================================================
        """
        self.max_size = max_size
        self.cache: OrderedDict[str, CacheEntry] = OrderedDict()
        logger.info(f"ResultCache 初始化完成，最大大小: {max_size}")

    def _generate_key(
        self,
        query: str,
        params: Dict[str, Any]
    ) -> str:
        """生成缓存键"""
        key_str = f"{query}:{params}"
        return hashlib.md5(key_str.encode()).hexdigest()

    def get(
        self,
        query: str,
        params: Dict[str, Any]
    ) -> Optional[List[Dict[str, Any]]]:
        """
        ==============================================================================
        获取缓存
        ==============================================================================
        
        功能说明：
            从缓存中获取检索结果。
        
        参数说明：
            query: 用户查询文本
            params: 检索参数
        
        返回值：
            Optional[List[Dict[str, Any]]]: 缓存的检索结果，如果不存在或过期则返回 None
        
        ==============================================================================
        """
        key = self._generate_key(query, params)
        
        if key in self.cache:
            entry = self.cache[key]
            if entry.is_expired:
                del self.cache[key]
                return None
            
            return entry.value
        
        return None

    def set(
        self,
        query: str,
        params: Dict[str, Any],
        value: List[Dict[str, Any]],
        ttl: int = 86400
    ):
        """
        ==============================================================================
        设置缓存
        ==============================================================================
        
        功能说明：
            将检索结果存入缓存。
        
        参数说明：
            query: 用户查询文本
            params: 检索参数
            value: 检索结果
            ttl: 生存时间（秒）
        
        ==============================================================================
        """
        key = self._generate_key(query, params)
        
        if key in self.cache:
            del self.cache[key]
        
        while len(self.cache) >= self.max_size:
            self.cache.popitem(last=False)
        
        self.cache[key] = CacheEntry(
            value=value,
            timestamp=time.time(),
            ttl=ttl
        )

    def clear(self):
        """清除所有缓存"""
        self.cache.clear()
        logger.info("结果缓存已清除")
