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

# Agentic RAG 模块
from .agentic import (
    AgenticRAGState,
    AgentState,
    QueryAnalysis,
    RetrievalPlan,
    EvaluationResult,
    ReflectionResult,
    SearchRecord,
    Document,
    ConversationContext,
    QueryAnalyzer,
    RetrievalPlanner,
    ResultEvaluator,
    ReflectionEngine,
    KnowledgeSynthesizer,
    QueryCompleter,
    create_agentic_rag_graph,
)

# 检索器模块
from .retrievers import (
    VectorRetriever,
    BM25Retriever,
    GraphRetriever,
)

__all__ = [
    # 核心类
    "KnowledgeRetriever",
    "VectorStore",
    # 处理函数
    "process_documents",
    "build_knowledge_base",
    "get_qwen_embeddings",
    "smart_chunk_text",
    "clean_text",
    # Agentic RAG - 状态定义
    "AgenticRAGState",
    "AgentState",
    "QueryAnalysis",
    "RetrievalPlan",
    "EvaluationResult",
    "ReflectionResult",
    "SearchRecord",
    "Document",
    "ConversationContext",
    # Agentic RAG - 核心组件
    "QueryAnalyzer",
    "RetrievalPlanner",
    "ResultEvaluator",
    "ReflectionEngine",
    "KnowledgeSynthesizer",
    "QueryCompleter",
    # Agentic RAG - 工作流
    "create_agentic_rag_graph",
    # 检索器
    "VectorRetriever",
    "BM25Retriever",
    "GraphRetriever",
]
