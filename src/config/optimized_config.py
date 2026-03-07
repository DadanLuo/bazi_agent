"""
优化配置管理
整合所有优化功能的配置
"""
from typing import Dict, Any, Optional

from src.cache.redis_cache import RedisCacheManager
from src.rag.vector_store import VectorStore, HNSWIndexConfig
from src.config.model_config import ContextStrategySelector
from src.memory.summarizer import ConversationSummarizer


class OptimizedConfig:
    """
    优化配置管理器
    
    整合所有优化功能的配置：
    - Redis 缓存
    - HNSW 索引
    - 自动策略选择
    - 会话摘要
    """
    
    def __init__(
        self,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_db: int = 0,
        redis_password: Optional[str] = None,
        hnsw_preset: str = "balanced",
        enable_cache: bool = True,
        enable_summarization: bool = True,
        summarization_threshold: int = 10
    ):
        """
        初始化优化配置
        
        Args:
            redis_host: Redis 主机地址
            redis_port: Redis 端口
            redis_db: Redis 数据库编号
            redis_password: Redis 密码
            hnsw_preset: HNSW 索引预设配置
            enable_cache: 是否启用缓存
            enable_summarization: 是否启用摘要
            summarization_threshold: 摘要阈值
        """
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.redis_db = redis_db
        self.redis_password = redis_password
        self.hnsw_preset = hnsw_preset
        self.enable_cache = enable_cache
        self.enable_summarization = enable_summarization
        self.summarization_threshold = summarization_threshold
        
        # 初始化各模块
        self._cache_manager: Optional[RedisCacheManager] = None
        self._vector_store: Optional[VectorStore] = None
        self._summarizer: Optional[ConversationSummarizer] = None
    
    @property
    def cache_manager(self) -> Optional[RedisCacheManager]:
        """获取缓存管理器"""
        if self._cache_manager is None and self.enable_cache:
            self._cache_manager = RedisCacheManager(
                host=self.redis_host,
                port=self.redis_port,
                db=self.redis_db,
                password=self.redis_password,
                enable_cache=True
            )
        return self._cache_manager
    
    @property
    def vector_store(self) -> Optional[VectorStore]:
        """获取向量存储（带 HNSW 索引）"""
        if self._vector_store is None:
            self._vector_store = HNSWIndexConfig.create_vector_store(
                persist_directory="chroma_db",
                preset=self.hnsw_preset
            )
        return self._vector_store
    
    @property
    def summarizer(self) -> Optional[ConversationSummarizer]:
        """获取摘要器"""
        if self._summarizer is None and self.enable_summarization:
            try:
                from src.llm.dashscope_llm import DashScopeLLM
                self._summarizer = ConversationSummarizer(DashScopeLLM())
            except Exception as e:
                logger.warning(f"摘要器初始化失败: {e}")
                self._summarizer = ConversationSummarizer(None)
        return self._summarizer
    
    def get_strategy_selector(self) -> ContextStrategySelector:
        """获取策略选择器"""
        return ContextStrategySelector()
    
    def get_config_summary(self) -> Dict[str, Any]:
        """获取配置摘要"""
        return {
            "redis": {
                "enabled": self.enable_cache,
                "host": self.redis_host,
                "port": self.redis_port,
                "db": self.redis_db
            },
            "hnsw": {
                "preset": self.hnsw_preset,
                "space": "cosine"
            },
            "summarization": {
                "enabled": self.enable_summarization,
                "threshold": self.summarization_threshold
            }
        }


# 全局优化配置实例
optimized_config = OptimizedConfig()


def get_optimized_config() -> OptimizedConfig:
    """
    获取全局优化配置实例
    
    Returns:
        OptimizedConfig 实例
    """
    return optimized_config
