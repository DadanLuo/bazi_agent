# src/dependencies.py
"""
共享依赖 — 无状态单例 + 请求级 SessionContext 工厂

无状态组件（redis_cache, file_storage, llm, retriever 等）保持模块级单例。
有状态组件使用 get_session_context() 工厂，每个请求独立实例。

清理说明：
    - 移除了不存在的模块导入（ContextSkill, ConversationSkill, ModelConfig, HybridRetriever, Reranker）
    - 移除了过时的 UnifiedStateManager（已被 SessionContext 替代）
    - 保留 KnowledgeRetriever 作为主检索器入口
"""
import logging
from src.storage import FileStorage
from src.cache.redis_cache import RedisCacheManager
from src.rag.retriever import KnowledgeRetriever
from src.llm.dashscope_llm import DashScopeLLM
from src.core.session_context import SessionContext

logger = logging.getLogger(__name__)

# ========== 无状态单例 ==========
redis_cache = None
file_storage = None
retriever = None
llm = None


def _init_component(name: str, factory):
    """逐项初始化共享依赖，避免一个组件失败拖垮全部单例。"""
    try:
        instance = factory()
        logger.info(f"{name} 初始化成功")
        return instance
    except Exception as e:
        logger.warning(f"{name} 初始化失败: {e}")
        return None


redis_cache = _init_component("RedisCacheManager", RedisCacheManager)
file_storage = _init_component("FileStorage", FileStorage)
retriever = _init_component("KnowledgeRetriever", KnowledgeRetriever)
llm = _init_component("DashScopeLLM", DashScopeLLM)


# ========== 请求级工厂 ==========

def get_session_context() -> SessionContext:
    """每个 API 请求调用一次，获取独立的 SessionContext 实例"""
    return SessionContext(redis_cache=redis_cache, file_storage=file_storage)


# ========== 向后兼容别名 ==========
# 旧代码中 from src.dependencies import state_manager 仍可用
# 但新代码应使用 get_session_context()
# 注意：state_manager 现在返回一个默认的 SessionContext 实例
state_manager = get_session_context() if redis_cache is not None else None
