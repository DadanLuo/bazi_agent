# src/rag/vector_store.py
"""
向量存储模块
支持 HNSW 索引加速向量检索
"""
import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
import chromadb
from chromadb.config import Settings
import logging

logger = logging.getLogger(__name__)


class VectorStore:
    """
    向量存储管理器
    
    支持 HNSW 索引配置，提供高效的向量检索：
    - L2 (Euclidean) 距离
    - Cosine 相似度
    - IP (Inner Product) 内积
    """
    
    # HNSW 索引参数
    HNSW_DEFAULT_CONFIG = {
        "hnsw:space": "cosine",      # 距离度量: l2, cosine, ip
        "hnsw:construction_ef": 128,  # 构建时的搜索参数，越大越精确但越慢
        "hnsw:M": 16,                 # 每个节点的最大边数，越大越精确但内存越高
        "hnsw:search_ef": 64,         # 搜索时的搜索参数，越大越精确但越慢
        "hnsw:num_threads": 8,        # 并行线程数
    }
    
    def __init__(
        self,
        persist_directory: str = "chroma_db",
        collection_name: str = "bazi_knowledge",
        hnsw_config: Optional[Dict[str, Any]] = None
    ):
        """
        初始化向量存储
        
        Args:
            persist_directory: 持久化目录路径
            collection_name: 集合名称
            hnsw_config: HNSW 索引配置，如果为 None 使用默认配置
        """
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        self.hnsw_config = hnsw_config or self.HNSW_DEFAULT_CONFIG
        
        # 确保目录存在
        Path(persist_directory).mkdir(parents=True, exist_ok=True)
        
        # 初始化 ChromaDB 客户端
        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        
        # 创建或获取集合
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata=self.hnsw_config
        )
        
        logger.info(f"✅ 向量存储初始化完成: {collection_name}")
        logger.info(f"📊 HNSW 配置: {self.hnsw_config}")
    
    def build_from_processed_file(
        self,
        processed_file: str = "knowledge_base/processed/all_chunks.json",
        batch_size: int = 5000
    ) -> int:
        """
        从预处理的 JSON 文件构建向量库
        
        Args:
            processed_file: 预处理文件路径
            batch_size: 批次大小（ChromaDB 推荐不超过 5461）
            
        Returns:
            int: 添加的记录数量
        """
        processed_path = Path(processed_file).resolve()
        logger.info(f"解析后的文件路径: {processed_path}")

        if not processed_path.exists():
            raise FileNotFoundError(f"预处理文件不存在: {processed_path}")

        with open(processed_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not data:
            raise ValueError("预处理数据为空")

        ids = [item["id"] for item in data]
        documents = [item["content"] for item in data]
        embeddings = [item["embedding"] for item in data]
        metadatas = [item["metadata"] for item in data]

        total_count = len(ids)
        logger.info(f"📊 总数据量: {total_count} 条")

        # 分批添加数据
        total_batches = (total_count + batch_size - 1) // batch_size

        for i in range(0, total_count, batch_size):
            end_idx = min(i + batch_size, total_count)
            batch_num = i // batch_size + 1

            logger.info(f"⚡ 正在添加批次 [{batch_num}/{total_batches}] (记录 {i + 1}-{end_idx})")

            try:
                self.collection.add(
                    ids=ids[i:end_idx],
                    documents=documents[i:end_idx],
                    embeddings=embeddings[i:end_idx],
                    metadatas=metadatas[i:end_idx]
                )
            except Exception as e:
                logger.error(f"❌ 批次 {batch_num} 添加失败: {e}")
                raise

        logger.info(f"✅ 向量库构建完成，共 {total_count} 条记录")
        logger.info(f"✅ 持久化路径: {self.persist_directory}")
        
        return total_count
    
    def query(
        self,
        query_embedding: List[float],
        n_results: int = 3,
        filter: Optional[Dict[str, Any]] = None,
        include: List[str] = None
    ) -> Dict[str, Any]:
        """
        执行向量检索
        
        Args:
            query_embedding: 查询向量
            n_results: 返回结果数量
            filter: 元数据过滤条件
            include: 返回内容选项: ["documents", "metadatas", "distances", "embeddings"]
            
        Returns:
            检索结果字典
        """
        if include is None:
            include = ["documents", "metadatas", "distances"]
            
        return self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=filter,
            include=include
        )
    
    def get_collection_count(self) -> int:
        """获取集合中的记录数量"""
        return self.collection.count()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取向量库统计信息"""
        return {
            "collection_name": self.collection_name,
            "total_documents": self.collection.count(),
            "hnsw_config": self.hnsw_config,
            "persist_directory": self.persist_directory
        }
    
    def reset(self) -> bool:
        """重置向量库（删除所有数据）"""
        try:
            self.client.delete_collection(self.collection_name)
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata=self.hnsw_config
            )
            logger.info("✅ 向量库已重置")
            return True
        except Exception as e:
            logger.error(f"❌ 重置向量库失败: {e}")
            return False


class HNSWIndexConfig:
    """
    HNSW 索引配置管理器
    
    提供预定义的配置模板：
    - fast_search: 快速搜索模式（低精度，高效率）
    - balanced: 平衡模式（中等精度，中等效率）
    - accurate: 高精度模式（高精度，低效率）
    """
    
    # 预定义配置模板
    PRESETS = {
        "fast_search": {
            "hnsw:space": "cosine",
            "hnsw:construction_ef": 64,
            "hnsw:M": 8,
            "hnsw:search_ef": 32,
            "hnsw:num_threads": 4,
        },
        "balanced": {
            "hnsw:space": "cosine",
            "hnsw:construction_ef": 128,
            "hnsw:M": 16,
            "hnsw:search_ef": 64,
            "hnsw:num_threads": 8,
        },
        "accurate": {
            "hnsw:space": "cosine",
            "hnsw:construction_ef": 256,
            "hnsw:M": 32,
            "hnsw:search_ef": 128,
            "hnsw:num_threads": 16,
        }
    }
    
    @classmethod
    def get_config(cls, preset: str = "balanced") -> Dict[str, Any]:
        """
        获取预定义的 HNSW 配置
        
        Args:
            preset: 配置模板名称
            
        Returns:
            HNSW 配置字典
        """
        return cls.PRESETS.get(preset, cls.PRESETS["balanced"])
    
    @classmethod
    def create_vector_store(
        cls,
        persist_directory: str,
        collection_name: str = "bazi_knowledge",
        preset: str = "balanced"
    ) -> VectorStore:
        """
        使用预定义配置创建 VectorStore
        
        Args:
            persist_directory: 持久化目录
            collection_name: 集合名称
            preset: 配置模板名称
            
        Returns:
            VectorStore 实例
        """
        config = cls.get_config(preset)
        return VectorStore(
            persist_directory=persist_directory,
            collection_name=collection_name,
            hnsw_config=config
        )


# 全局向量存储实例
_default_vector_store: Optional[VectorStore] = None


def get_vector_store(
    persist_directory: str = "chroma_db",
    collection_name: str = "bazi_knowledge",
    use_preset: str = "balanced"
) -> VectorStore:
    """
    获取全局向量存储实例
    
    Args:
        persist_directory: 持久化目录
        collection_name: 集合名称
        use_preset: 预定义配置名称
        
    Returns:
        VectorStore 实例
    """
    global _default_vector_store
    
    if _default_vector_store is None:
        _default_vector_store = HNSWIndexConfig.create_vector_store(
            persist_directory=persist_directory,
            collection_name=collection_name,
            preset=use_preset
        )
    
    return _default_vector_store
