# src/graph/chat_nodes.py
"""多轮对话节点 - 新增节点定义"""
import logging
from typing import Dict, Any, Optional, Literal
from src.graph.state import BaziAgentState, IntentType, ContextStrategy, RetrievalMode
from src.skills.memory_skill import MemorySkill
from src.skills.context_skill import ContextSkill
from src.skills.conversation_skill import ConversationSkill
from src.storage import FileStorage, StorageConfig
from src.config.model_config import ModelConfig
from src.config.rag_config import RAGConfigManager
from src.rag.hybrid_retriever import HybridRetriever
from src.rag.retriever import KnowledgeRetriever
from src.rag.bm25_retriever import BM25Retriever
from src.rag.reranker import Reranker
from src.llm.dashscope_llm import DashScopeLLM
from src.prompts.safety_prompt import check_safety, detect_crisis, SAFETY_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

# 全局初始化组件
try:
    storage = FileStorage()
    memory_skill = MemorySkill(storage=storage)
    context_skill = ContextSkill()
    conversation_skill = ConversationSkill()
    model_config = ModelConfig()
    
    # 初始化检索器
    vector_retriever = KnowledgeRetriever()
    bm25_retriever = BM25Retriever()
    reranker = Reranker()
    hybrid_retriever = HybridRetriever(
        vector_retriever=vector_retriever,
        bm25_retriever=bm25_retriever,
        reranker=reranker
    )
    
    llm = DashScopeLLM()
except Exception as e:
    logger.warning(f"⚠️ 组件初始化失败: {e}")
    storage = None
    memory_skill = None
    context_skill = None
    conversation_skill = None
    model_config = None
    vector_retriever = None
    bm25_retriever = None
    reranker = None
    hybrid_retriever = None
    llm = None


def chat_node(state: BaziAgentState) -> Dict[str, Any]:
    """节点：多轮对话处理"""
    logger.info("=" * 30)
    logger.info("【节点】执行多轮对话处理...")
    
    try:
        # 获取用户输入
        user_input = state.get("user_input", {})
        user_query = user_input.get("query", user_input.get("content", ""))
        
        if not user_query:
            return {
                "error": "用户输入为空",
                "status": "chat_failed"
            }
        
        # 获取会话ID
        conversation_id = state.get("conversation_id")
        
        # 加载或创建会话
        if conversation_id:
            session_data = memory_skill.load_session(conversation_id)
            if not session_data:
                # 创建新会话
                session_data = memory_skill.create_session(
                    conversation_id=conversation_id,
                    user_id=state.get("user_id", "default"),
                    system_prompt=SAFETY_SYSTEM_PROMPT,
                    context_strategy=state.get("context_strategy", "FULL_CONTEXT"),
                    retrieval_mode=state.get("retrieval_mode", "hybrid_rerank")
                )
        else:
            # 创建新会话
            conversation_id = f"conv_{state.get('user_id', 'default')}_{state.get('session_id', '')}"
            session_data = memory_skill.create_session(
                conversation_id=conversation_id,
                user_id=state.get("user_id", "default"),
                system_prompt=SAFETY_SYSTEM_PROMPT,
                context_strategy=state.get("context_strategy", "FULL_CONTEXT"),
                retrieval_mode=state.get("retrieval_mode", "hybrid_rerank")
            )
        
        # 添加用户消息
        session_data.add_message("user", user_query)
        
        # 检测意图
        intent_info = conversation_skill.detect_intent(user_query, session_data)
        slots = conversation_skill.extract_slots(user_query)
        
        logger.info(f"检测意图: {intent_info.get('intent')}")
        logger.info(f"槽位信息: {slots}")
        
        # 检查安全
        safety_check = check_safety(user_query)
        crisis_check = detect_crisis(user_query)
        
        if crisis_check.get("needs_intervention"):
            return {
                "llm_response": "我注意到您可能正在经历一些困难。请记住，每个人都会遇到低谷，这只是暂时的。如果您感到难以承受，建议您联系专业心理咨询师或拨打心理援助热线：400-161-9995（24小时）。",
                "status": "crisis_intervention"
            }
        
        if not safety_check.get("is_safe"):
            return {
                "error": "输入包含敏感内容，无法处理",
                "status": "safety_check_failed"
            }
        
        # 构建上下文
        context_info = context_skill.build_context(
            session_data=session_data,
            user_query=user_query,
            retrieval_results=None,
            max_tokens=model_config.get_max_history_tokens() if model_config else 30000
        )
        
        # 执行检索（如果需要）
        retrieval_mode = state.get("retrieval_mode", "hybrid_rerank")
        if retrieval_mode != "vector_only":
            retrieval_results = hybrid_retriever.retrieve(user_query)
        else:
            retrieval_results = vector_retriever.search(user_query, top_k=5)
        
        # 更新上下文
        context_info = context_skill.build_context(
            session_data=session_data,
            user_query=user_query,
            retrieval_results=retrieval_results,
            max_tokens=model_config.get_max_history_tokens() if model_config else 30000
        )
        
        # 保存会话
        memory_skill._current_session = session_data
        memory_skill._update_session()
        
        # 更新状态
        return {
            "conversation_id": conversation_id,
            "session_id": state.get("session_id"),
            "messages": session_data.get_openai_format(),
            "intent": intent_info.get("intent"),
            "intent_confidence": intent_info.get("confidence"),
            "intent_slots": slots,
            "context_text": context_info.get("context_text"),
            "context_token_count": context_info.get("token_count"),
            "retrieval_results": retrieval_results,
            "reranked_results": retrieval_results,  # 简化处理
            "status": "chat_processed"
        }
        
    except Exception as e:
        logger.error(f"❌ 多轮对话处理失败: {e}", exc_info=True)
        return {
            "error": f"多轮对话处理错误: {str(e)}",
            "status": "chat_failed"
        }


def intent_router_node(state: BaziAgentState) -> Dict[str, Any]:
    """节点：意图路由"""
    logger.info("=" * 30)
    logger.info("【节点】执行意图路由...")
    
    try:
        intent = state.get("intent")
        
        if not intent:
            # 默认路由到分析节点
            return {"next_node": "analyze", "route_decision": "default"}
        
        # 根据意图路由
        if intent == "NEW_ANALYSIS":
            return {"next_node": "validate_input", "route_decision": "new_analysis"}
        elif intent == "FOLLOW_UP":
            return {"next_node": "chat_node", "route_decision": "follow_up"}
        elif intent == "TOPIC_SWITCH":
            return {"next_node": "chat_node", "route_decision": "topic_switch"}
        elif intent == "CLARIFICATION":
            return {"next_node": "chat_node", "route_decision": "clarification"}
        else:
            return {"next_node": "chat_node", "route_decision": "general_query"}
            
    except Exception as e:
        logger.error(f"❌ 意图路由失败: {e}", exc_info=True)
        return {
            "error": f"意图路由错误: {str(e)}",
            "next_node": "chat_node",
            "route_decision": "error"
        }


def chat_generate_node(state: BaziAgentState) -> Dict[str, Any]:
    """节点：聊天生成响应"""
    logger.info("=" * 30)
    logger.info("【节点】执行聊天生成...")
    
    if not llm:
        logger.warning("⚠️ LLM未初始化")
        return {"llm_response": "系统配置错误，无法生成回答。", "status": "llm_skipped"}
    
    try:
        # 获取上下文
        context_text = state.get("context_text", "")
        user_query = state.get("user_input", {}).get("query", "")
        
        # 构建提示词
        prompt = f"""基于以下上下文，回答用户问题：

上下文：
{context_text}

用户问题：{user_query}

请提供专业、准确的回答。"""
        
        # 调用LLM
        response = llm.call(prompt)
        
        logger.info("✅ 聊天生成完成")
        return {
            "llm_response": response,
            "status": "chat_generated"
        }
        
    except Exception as e:
        logger.error(f"❌ 聊天生成失败: {e}", exc_info=True)
        return {
            "error": f"聊天生成错误: {str(e)}",
            "status": "chat_generation_failed"
        }


def chat_save_node(state: BaziAgentState) -> Dict[str, Any]:
    """节点：保存聊天记录"""
    logger.info("=" * 30)
    logger.info("【节点】保存聊天记录...")
    
    try:
        conversation_id = state.get("conversation_id")
        
        if not conversation_id or not memory_skill:
            return {"status": "skip_save"}
        
        # 加载会话
        session_data = memory_skill.load_session(conversation_id)
        
        if not session_data:
            return {"status": "session_not_found"}
        
        # 添加助手消息
        llm_response = state.get("llm_response", "")
        session_data.add_message("assistant", llm_response)
        
        # 更新元数据
        session_data.metadata.updated_at = __import__('datetime').datetime.now()
        
        # 保存会话
        memory_skill.storage.save_session(session_data)
        
        logger.info("✅ 聊天记录保存完成")
        return {
            "status": "chat_saved",
            "message_count": session_data.metadata.message_count
        }
        
    except Exception as e:
        logger.error(f"❌ 聊天记录保存失败: {e}", exc_info=True)
        return {
            "error": f"聊天记录保存错误: {str(e)}",
            "status": "chat_save_failed"
        }


def chat_safety_check_node(state: BaziAgentState) -> Dict[str, Any]:
    """节点：聊天安全检查"""
    logger.info("=" * 30)
    logger.info("【节点】执行聊天安全检查...")
    
    try:
        llm_response = state.get("llm_response", "")
        
        # 检查响应
        safety_check = check_safety(llm_response)
        
        if not safety_check.get("is_safe"):
            return {
                "error": "响应包含敏感内容",
                "status": "safety_check_failed"
            }
        
        logger.info("✅ 聊天安全检查完成")
        return {
            "status": "safety_checked"
        }
        
    except Exception as e:
        logger.error(f"❌ 聊天安全检查失败: {e}", exc_info=True)
        return {
            "error": f"安全检查错误: {str(e)}",
            "status": "safety_check_failed"
        }