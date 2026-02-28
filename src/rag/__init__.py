"""
RAG 模块
整合知识库处理与检索功能
"""
from .retriever import KnowledgeRetriever
from .vector_store import VectorStore
from .knowledge_processor import (
    process_documents,
    get_qwen_embeddings,
    smart_chunk_text,
    clean_text
)
from .build_knowledge_base import build_knowledge_base

__all__ = [
    # 核心类
    "KnowledgeRetriever",
    "VectorStore",
    # 处理函数
    "process_documents",
    "build_knowledge_base",
    "get_qwen_embeddings",
    "smart_chunk_text",
    "clean_text"
]
