# src/dependencies.py
"""
共享依赖 — 无状态单例 + 请求级 SessionContext 工厂

无状态组件（redis_cache, file_storage, llm, retriever 等）保持模块级单例。
有状态组件（state_manager）替换为 get_session_context() 工厂，每个请求独立实例。
旧 state_manager 保留为兼容别名，指向一个默认 SessionContext（仅用于非 API 场景）。
"""
import logging
from src.storage import FileStorage
from src.cache.redis_cache import RedisCacheManager
from src.graph.state_manager import UnifiedStateManager
from src.skills.context_skill import ContextSkill
from src.skills.conversation_skill import ConversationSkill
from src.config.model_config import ModelConfig
from src.rag.hybrid_retriever import HybridRetriever
from src.rag.retriever import KnowledgeRetriever
from src.rag.bm25_retriever import BM25Retriever
from src.rag.reranker import Reranker
from src.llm.dashscope_llm import DashScopeLLM
from src.llm.base import LLMConfig
from src.core.session_context import SessionContext

logger = logging.getLogger(__name__)

# ========== 无状态单例 ==========
try:
    redis_cache = RedisCacheManager()
    file_storage = FileStorage()
    context_skill = ContextSkill()
    conversation_skill = ConversationSkill()
    model_config = ModelConfig()

    vector_retriever = KnowledgeRetriever()
    bm25_retriever = BM25Retriever()
    reranker = Reranker()
    hybrid_retriever = HybridRetriever(
        vector_retriever=vector_retriever,
        bm25_retriever=bm25_retriever,
        reranker=reranker
    )

    llm = DashScopeLLM(config=LLMConfig())
    logger.info("共享依赖初始化成功")
except Exception as e:
    logger.warning(f"共享依赖初始化失败: {e}")
    redis_cache = None
    file_storage = None
    context_skill = None
    conversation_skill = None
    model_config = None
    vector_retriever = None
    bm25_retriever = None
    reranker = None
    hybrid_retriever = None
    llm = None


# ========== 请求级工厂 ==========

def get_session_context() -> SessionContext:
    """每个 API 请求调用一次，获取独立的 SessionContext 实例"""
    return SessionContext(redis_cache=redis_cache, file_storage=file_storage)


# ========== 向后兼容 ==========
# 旧代码中 from src.dependencies import state_manager 仍可用
# 但新代码应使用 get_session_context()
state_manager = UnifiedStateManager(redis_cache=redis_cache, file_storage=file_storage) if redis_cache is not None else None
