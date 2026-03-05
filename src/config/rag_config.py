# src/config/rag_config.py
"""RAG检索配置模块"""
from typing import Dict, Any

# RAG检索配置
RAG_CONFIG: Dict[str, Any] = {
    # 检索模式：vector_only, bm25_only, hybrid, hybrid_rerank
    "retrieval_mode": "hybrid_rerank",
    
    # 向量检索配置
    "vector": {
        "embedding_model": "text-embedding-v4",  # DashScope embedding 模型
        "top_k": 10,  # 初始召回数量
        "distance_metric": "cosine",  # 距离度量
        "collection_name": "bazi_knowledge"  # ChromaDB 集合名
    },
    
    # BM25关键词检索配置
    "bm25": {
        "k1": 1.5,  # BM25 参数：词频饱和度
        "b": 0.75,  # BM25 参数：文档长度归一化
        "top_k": 10,  # 初始召回数量
        "index_path": "data/bm25_index",  # 索引存储路径
        "index_file": "bm25_index.json"  # 索引文件名
    },
    
    # 混合检索配置
    "hybrid": {
        "vector_weight": 0.6,  # 向量检索权重
        "bm25_weight": 0.4,  # BM25权重
        "candidate_multiplier": 4,  # 候选集放大倍数
        "rerank_top_k": 5  # 重排序后保留数量
    },
    
    # 重排序配置
    "rerank": {
        "model": "bge-reranker-v2-m3",  # 重排序模型
        "top_k": 5,  # 重排序数量
        "api_limit": {
            "calls_per_5_hours": 1200,  # 调用限制
            "cooldown_seconds": 15  # 冷却时间（秒）
        }
    },
    
    # 检索结果处理配置
    "post_processing": {
        "max_context_length": 2000,  # 最大上下文长度（字符）
        "min_relevance_score": 0.3,  # 最小相关性分数
        "deduplicate": True  # 是否去重
    }
}

# RAG检索模式枚举
RETRIEVAL_MODES = {
    "vector_only": "仅向量检索",
    "bm25_only": "仅BM25检索",
    "hybrid": "混合检索（无重排序）",
    "hybrid_rerank": "混合检索+重排序"
}


class RAGConfigManager:
    """RAG配置管理器"""
    
    @staticmethod
    def get_retrieval_mode() -> str:
        """获取当前检索模式"""
        return RAG_CONFIG["retrieval_mode"]
    
    @staticmethod
    def is_rerank_enabled() -> bool:
        """检查是否启用重排序"""
        return "rerank" in RAG_CONFIG["retrieval_mode"]
    
    @staticmethod
    def get_vector_config() -> Dict[str, Any]:
        """获取向量检索配置"""
        return RAG_CONFIG["vector"]
    
    @staticmethod
    def get_bm25_config() -> Dict[str, Any]:
        """获取BM25检索配置"""
        return RAG_CONFIG["bm25"]
    
    @staticmethod
    def get_hybrid_config() -> Dict[str, Any]:
        """获取混合检索配置"""
        return RAG_CONFIG["hybrid"]
    
    @staticmethod
    def get_rerank_config() -> Dict[str, Any]:
        """获取重排序配置"""
        return RAG_CONFIG["rerank"]
    
    @staticmethod
    def get_post_processing_config() -> Dict[str, Any]:
        """获取后处理配置"""
        return RAG_CONFIG["post_processing"]
    
    @staticmethod
    def update_config(key: str, value: Any) -> None:
        """更新配置项"""
        if key in RAG_CONFIG:
            RAG_CONFIG[key] = value
        else:
            raise ValueError(f"Unknown config key: {key}")