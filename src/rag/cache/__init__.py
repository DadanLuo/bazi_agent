"""
==============================================================================
缓存模块
==============================================================================

功能说明：
    本模块提供了缓存功能，包括查询缓存、结果缓存和上下文缓存，用于提高
    系统性能和减少重复检索。

缓存类型：
    - QueryCache: 查询缓存
    - ResultCache: 结果缓存
    - ContextCache: 上下文缓存

==============================================================================
"""

import logging
import time
import hashlib
from typing import Dict, Any, Optional, List
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime

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


class ContextCache:
    """
    ==============================================================================
    上下文缓存
    ==============================================================================
    
    功能说明：
        缓存知识上下文，避免重复整合相同的检索结果。
    
    缓存键：
        查询文本 + 检索结果的哈希值
    
    TTL：
        会话期间（无固定 TTL）
    
    ==============================================================================
    """

    def __init__(self, max_size: int = 1000):
        """
        ==============================================================================
        初始化上下文缓存
        ==============================================================================
        
        参数说明：
            max_size: 最大缓存大小
        
        ==============================================================================
        """
        self.max_size = max_size
        self.cache: OrderedDict[str, CacheEntry] = OrderedDict()
        logger.info(f"ContextCache 初始化完成，最大大小: {max_size}")

    def _generate_key(
        self,
        query: str,
        docs: List[Dict[str, Any]]
    ) -> str:
        """生成缓存键"""
        doc_ids = [doc.get("id", "") for doc in docs]
        key_str = f"{query}:{doc_ids}"
        return hashlib.md5(key_str.encode()).hexdigest()

    def get(
        self,
        query: str,
        docs: List[Dict[str, Any]]
    ) -> Optional[str]:
        """
        ==============================================================================
        获取缓存
        ==============================================================================
        
        功能说明：
            从缓存中获取知识上下文。
        
        参数说明：
            query: 用户查询文本
            docs: 检索到的文档列表
        
        返回值：
            Optional[str]: 缓存的上下文，如果不存在或过期则返回 None
        
        ==============================================================================
        """
        key = self._generate_key(query, docs)
        
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
        docs: List[Dict[str, Any]],
        value: str,
        ttl: int = None  # 会话期间，无固定 TTL
    ):
        """
        ==============================================================================
        设置缓存
        ==============================================================================
        
        功能说明：
            将知识上下文存入缓存。
        
        参数说明：
            query: 用户查询文本
            docs: 检索到的文档列表
            value: 知识上下文
            ttl: 生存时间（秒），None 表示会话期间
        
        ==============================================================================
        """
        key = self._generate_key(query, docs)
        
        if key in self.cache:
            del self.cache[key]
        
        while len(self.cache) >= self.max_size:
            self.cache.popitem(last=False)
        
        # 会话期间的 TTL 设置为 1 小时
        actual_ttl = ttl if ttl else 3600
        
        self.cache[key] = CacheEntry(
            value=value,
            timestamp=time.time(),
            ttl=actual_ttl
        )

    def clear(self):
        """清除所有缓存"""
        self.cache.clear()
        logger.info("上下文缓存已清除")
