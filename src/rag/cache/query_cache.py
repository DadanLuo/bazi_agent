"""
==============================================================================
查询缓存
==============================================================================

功能说明：
    本模块提供了查询缓存功能，用于缓存查询分析结果，避免重复分析相同的
    查询。

==============================================================================
"""

import logging
import time
import hashlib
from typing import Dict, Any, Optional
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
    ttl: int = 3600  # 默认 1 小时
    
    @property
    def is_expired(self) -> bool:
        """检查是否过期"""
        return time.time() > self.timestamp + self.ttl


class QueryCache:
    """
    ==============================================================================
    查询缓存
    ==============================================================================
    
    功能说明：
        缓存查询分析结果，避免重复分析相同的查询。
    
    缓存键：
        查询文本的哈希值
    
    TTL：
        1 小时
    
    ==============================================================================
    """

    def __init__(self, max_size: int = 1000):
        """
        ==============================================================================
        初始化查询缓存
        ==============================================================================
        
        参数说明：
            max_size: 最大缓存大小
        
        ==============================================================================
        """
        self.max_size = max_size
        self.cache: OrderedDict[str, CacheEntry] = OrderedDict()
        logger.info(f"QueryCache 初始化完成，最大大小: {max_size}")

    def _generate_key(self, query: str) -> str:
        """生成缓存键"""
        return hashlib.md5(query.encode()).hexdigest()

    def get(self, query: str) -> Optional[Dict[str, Any]]:
        """
        ==============================================================================
        获取缓存
        ==============================================================================
        
        功能说明：
            从缓存中获取查询分析结果。
        
        参数说明：
            query: 用户查询文本
        
        返回值：
            Optional[Dict[str, Any]]: 缓存的分析结果，如果不存在或过期则返回 None
        
        ==============================================================================
        """
        key = self._generate_key(query)
        
        if key in self.cache:
            entry = self.cache[key]
            if entry.is_expired:
                del self.cache[key]
                logger.info(f"查询缓存过期: {query[:20]}...")
                return None
            
            logger.info(f"查询缓存命中: {query[:20]}...")
            return entry.value
        
        return None

    def set(self, query: str, value: Dict[str, Any], ttl: int = 3600):
        """
        ==============================================================================
        设置缓存
        ==============================================================================
        
        功能说明：
            将查询分析结果存入缓存。
        
        参数说明：
            query: 用户查询文本
            value: 分析结果
            ttl: 生存时间（秒）
        
        ==============================================================================
        """
        key = self._generate_key(query)
        
        # 如果键已存在，删除它
        if key in self.cache:
            del self.cache[key]
        
        # 如果缓存已满，删除最旧的条目
        while len(self.cache) >= self.max_size:
            self.cache.popitem(last=False)
        
        self.cache[key] = CacheEntry(
            value=value,
            timestamp=time.time(),
            ttl=ttl
        )
        
        logger.info(f"查询缓存设置: {query[:20]}...")

    def clear(self):
        """清除所有缓存"""
        self.cache.clear()
        logger.info("查询缓存已清除")

    def clear_expired(self):
        """清除过期缓存"""
        expired_keys = [
            key for key, entry in self.cache.items()
            if entry.is_expired
        ]
        for key in expired_keys:
            del self.cache[key]
        
        if expired_keys:
            logger.info(f"清除 {len(expired_keys)} 个过期查询缓存")
