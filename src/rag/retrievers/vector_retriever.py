"""
==============================================================================
向量检索器（Agentic RAG 组件）
==============================================================================

功能说明：
    本模块是 Agentic RAG 系统的向量检索组件，用于从知识库中检索语义相关的
    文档。

注意：
    对于简单的检索需求，推荐使用主入口 KnowledgeRetriever (src.rag.retriever)。
    本类主要用于 Agentic RAG 工作流内部，由 RetrievalPlanner 调度。

核心功能：
    - 向量检索：使用向量相似度检索相关文档
    - 过滤检索：支持元数据过滤
    - 多语言支持：支持中文查询

使用场景：
    - Agentic RAG 工作流中的向量检索节点
    - 需要更细粒度控制的检索场景

==============================================================================
"""

import logging
from typing import List, Dict, Any, Optional

import dashscope
from chromadb import Client
from chromadb.config import Settings
from dashscope import TextEmbedding

from config.settings import settings
from src.config.rag_config import rag_config
from src.rag.agentic.state import Document

logger = logging.getLogger(__name__)


class VectorRetriever:
    """
    ==============================================================================
    向量检索器
    ==============================================================================
    
    功能说明：
        基于向量数据库的语义检索器，用于从知识库中检索语义相关的文档。
    
    核心方法：
        - search(): 向量检索
    
    ==============================================================================
    """

    def __init__(
        self,
        chroma_path: str | None = None,
        collection_name: str | None = None,
    ):
        """
        ==============================================================================
        初始化向量检索器
        ==============================================================================
        
        参数说明：
            chroma_path: ChromaDB 数据库存储路径
            collection_name: ChromaDB 集合名称
        
        ==============================================================================
        """
        self.chroma_path = chroma_path or rag_config.chroma_persist_dir
        self.collection_name = collection_name or rag_config.collection_name
        self.embedding_model = rag_config.embedding_model
        self.api_key = settings.resolved_embedding_api_key
        if self.api_key:
            dashscope.api_key = self.api_key
        self.client = Client(Settings(
            persist_directory=self.chroma_path,
            is_persistent=True
        ))
        self.collection = self.client.get_collection(name=self.collection_name)
        logger.info(f"VectorRetriever 初始化完成，集合: {self.collection_name}")

    def search(
        self,
        query: str,
        top_k: int = 5,
        threshold: float = 0.6,
        filter: Optional[Dict[str, Any]] = None
    ) -> List[Document]:
        """
        ==============================================================================
        向量检索
        ==============================================================================
        
        功能说明：
            使用向量相似度检索相关文档。
        
        参数说明：
            query: 用户查询文本
            top_k: 返回的文档数量
            threshold: 相似度阈值
            filter: 元数据过滤器
        
        返回值：
            List[Document]: 检索到的文档列表
        
        ==============================================================================
        """
        logger.info(f"开始向量检索: {query}")
        
        try:
            # 获取查询向量
            query_vector = self._get_embedding(query)
            
            # 执行检索
            results = self.collection.query(
                query_embeddings=[query_vector],
                n_results=top_k,
                where=filter
            )
            
            # 转换为 Document 列表
            docs = self._convert_to_documents(results, threshold)
            
            logger.info(f"向量检索完成，返回 {len(docs)} 个文档")
            return docs
            
        except Exception as e:
            logger.error(f"向量检索失败: {e}")
            return []

    def _get_embedding(self, text: str) -> List[float]:
        """
        ==============================================================================
        获取文本向量
        ==============================================================================
        
        功能说明：
            调用向量 API 获取文本的向量表示。
        
        参数说明：
            text: 文本
        
        返回值：
            List[float]: 文本向量
        
        ==============================================================================
        """
        if not self.api_key:
            raise RuntimeError("未设置 Embedding API Key，请在 config 中配置")

        response = TextEmbedding.call(
            model=self.embedding_model,
            input=[text],
        )
        if response.status_code != 200:
            raise RuntimeError(f"Embedding API 错误: {response.code}")

        return response.output["embeddings"][0]["embedding"]

    def _convert_to_documents(
        self,
        results: Dict[str, Any],
        threshold: float
    ) -> List[Document]:
        """
        ==============================================================================
        转换为 Document 列表
        ==============================================================================
        
        功能说明：
            将 ChromaDB 检索结果转换为 Document 列表。
        
        参数说明：
            results: ChromaDB 检索结果
            threshold: 相似度阈值
        
        返回值：
            List[Document]: Document 列表
        
        ==============================================================================
        """
        docs = []
        
        if not results or "documents" not in results:
            return docs
        
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]
        
        for i, doc_text in enumerate(documents):
            if i < len(distances):
                # 距离转换为相似度（假设使用余弦距离）
                similarity = 1.0 - distances[i]
            else:
                similarity = 0.0
            
            if similarity >= threshold:
                docs.append(Document(
                    content=doc_text,
                    metadata=metadatas[i] if i < len(metadatas) else {},
                    score=similarity,
                    source_type="vector"
                ))
        
        return docs

    def batch_search(
        self,
        queries: List[str],
        top_k: int = 5,
        threshold: float = 0.6
    ) -> List[List[Document]]:
        """
        ==============================================================================
        批量向量检索
        ==============================================================================
        
        功能说明：
            批量执行向量检索。
        
        参数说明：
            queries: 查询文本列表
            top_k: 返回的文档数量
            threshold: 相似度阈值
        
        返回值：
            List[List[Document]]: 每个查询的检索结果列表
        
        ==============================================================================
        """
        return [
            self.search(query, top_k, threshold)
            for query in queries
        ]
