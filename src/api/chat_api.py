# src/api/chat_api.py
"""多轮对话 FastAPI 接口定义"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
from src.skills.memory_skill import MemorySkill
from src.skills.context_skill import ContextSkill
from src.skills.conversation_skill import ConversationSkill
from src.storage import FileStorage, StorageConfig, SessionData, Message, MessageRole
from src.config.model_config import ModelConfig
from src.config.rag_config import RAGConfigManager
from src.rag.hybrid_retriever import HybridRetriever
from src.rag.retriever import KnowledgeRetriever
from src.rag.bm25_retriever import BM25Retriever
from src.rag.reranker import Reranker
from src.llm.dashscope_llm import DashScopeLLM
from src.prompts.safety_prompt import check_safety, detect_crisis, SAFETY_SYSTEM_PROMPT
import logging
import uuid

from src.graph.bazi_graph import app
from src.graph.state import BaziAgentState

router = APIRouter(prefix="/api/v1/chat", tags=["多轮对话"])
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


# ========== 请求模型 ==========

class ChatInput(BaseModel):
    """聊天输入模型"""
    query: str  # 用户问题
    user_id: Optional[str] = "default"  # 用户ID
    session_id: Optional[str] = None  # 会话ID
    conversation_id: Optional[str] = None  # 对话ID
    context_strategy: Optional[str] = "FULL_CONTEXT"  # 上下文策略
    retrieval_mode: Optional[str] = "hybrid_rerank"  # 检索模式
    system_prompt: Optional[str] = None  # 自定义系统提示词


class ChatResponse(BaseModel):
    """聊天响应模型"""
    success: bool
    message: str
    data: Dict[str, Any] = {}


class FollowUpInput(BaseModel):
    """追问输入模型"""
    conversation_id: str
    question: str


class ExportInput(BaseModel):
    """导出输入模型"""
    conversation_id: str
    format_type: str = "openai"  # openai 或 alpaca


class ExportResponse(BaseModel):
    """导出响应模型"""
    success: bool
    message: str
    data: Dict[str, Any] = {}


# ========== API 端点 ==========

@router.post("/chat", response_model=ChatResponse)
async def handle_chat(input_data: ChatInput):
    """
    多轮对话接口
    支持新对话和已有对话的继续
    """
    logger.info(f"收到聊天请求：user_id={input_data.user_id}, query={input_data.query[:50]}...")
    
    try:
        # 检查输入
        if not input_data.query:
            raise HTTPException(status_code=400, detail="用户问题不能为空")
        
        # 检查组件初始化
        if not memory_skill or not llm:
            raise HTTPException(status_code=500, detail="系统组件未初始化")
        
        # 检查安全
        safety_check = check_safety(input_data.query)
        crisis_check = detect_crisis(input_data.query)
        
        if crisis_check.get("needs_intervention"):
            return ChatResponse(
                success=True,
                message="检测到心理危机信号，已提供援助信息",
                data={
                    "response": "我注意到您可能正在经历一些困难。请记住，每个人都会遇到低谷，这只是暂时的。如果您感到难以承受，建议您联系专业心理咨询师或拨打心理援助热线：400-161-9995（24小时）。",
                    "conversation_id": input_data.conversation_id,
                    "crisis_intervention": True
                }
            )
        
        if not safety_check.get("is_safe"):
            return ChatResponse(
                success=False,
                message="输入包含敏感内容，无法处理",
                data={"error": "敏感内容检测"}
            )
        
        # 获取或创建会话
        if input_data.conversation_id:
            session_data = memory_skill.load_session(input_data.conversation_id)
            if not session_data:
                # 创建新会话
                session_data = memory_skill.create_session(
                    conversation_id=input_data.conversation_id,
                    user_id=input_data.user_id,
                    session_id=input_data.session_id,
                    system_prompt=input_data.system_prompt or SAFETY_SYSTEM_PROMPT,
                    context_strategy=input_data.context_strategy,
                    retrieval_mode=input_data.retrieval_mode
                )
        else:
            # 创建新会话
            conversation_id = f"conv_{input_data.user_id}_{uuid.uuid4().hex[:8]}"
            session_data = memory_skill.create_session(
                conversation_id=conversation_id,
                user_id=input_data.user_id,
                session_id=input_data.session_id,
                system_prompt=input_data.system_prompt or SAFETY_SYSTEM_PROMPT,
                context_strategy=input_data.context_strategy,
                retrieval_mode=input_data.retrieval_mode
            )
            input_data.conversation_id = conversation_id
        
        # 添加用户消息
        session_data.add_message(MessageRole.USER, input_data.query)
        
        # 检测意图
        intent_info = conversation_skill.detect_intent(input_data.query, session_data)
        slots = conversation_skill.extract_slots(input_data.query)
        
        logger.info(f"检测意图: {intent_info.get('intent')}")
        
        # 构建上下文
        context_info = context_skill.build_context(
            session_data=session_data,
            user_query=input_data.query,
            retrieval_results=None,
            max_tokens=model_config.get_max_history_tokens() if model_config else 30000
        )
        
        # 执行检索
        retrieval_results = hybrid_retriever.retrieve(input_data.query)
        
        # 更新上下文
        context_info = context_skill.build_context(
            session_data=session_data,
            user_query=input_data.query,
            retrieval_results=retrieval_results,
            max_tokens=model_config.get_max_history_tokens() if model_config else 30000
        )
        
        # 构建提示词
        prompt = f"""基于以下上下文，回答用户问题：

上下文：
{context_info.get('context_text', '')}

用户问题：{input_data.query}

请提供专业、准确的回答。"""
        
        # 调用LLM
        response = llm.call(prompt)
        
        # 添加助手消息
        session_data.add_message(MessageRole.ASSISTANT, response)
        
        # 保存会话
        memory_skill._current_session = session_data
        memory_skill._update_session()
        
        # 返回响应
        return ChatResponse(
            success=True,
            message="聊天处理成功",
            data={
                "response": response,
                "conversation_id": input_data.conversation_id,
                "session_id": session_data.metadata.session_id,
                "intent": intent_info.get("intent"),
                "intent_confidence": intent_info.get("confidence"),
                "intent_slots": slots,
                "context_token_count": context_info.get("token_count"),
                "message_count": session_data.metadata.message_count
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"聊天API失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"服务器错误: {str(e)}")


@router.post("/followup", response_model=ChatResponse)
async def handle_followup(input_data: FollowUpInput):
    """
    追问接口
    基于已有对话进行追问
    """
    logger.info(f"收到追问请求：conversation_id={input_data.conversation_id}")
    
    try:
        # 检查组件初始化
        if not memory_skill or not llm:
            raise HTTPException(status_code=500, detail="系统组件未初始化")
        
        # 加载会话
        session_data = memory_skill.load_session(input_data.conversation_id)
        
        if not session_data:
            raise HTTPException(status_code=404, detail="会话不存在")
        
        # 检查安全
        safety_check = check_safety(input_data.question)
        if not safety_check.get("is_safe"):
            return ChatResponse(
                success=False,
                message="输入包含敏感内容，无法处理",
                data={"error": "敏感内容检测"}
            )
        
        # 添加用户消息
        session_data.add_message(MessageRole.USER, input_data.question)
        
        # 检测意图
        intent_info = conversation_skill.detect_intent(input_data.question, session_data)
        
        # 构建上下文
        context_info = context_skill.build_context(
            session_data=session_data,
            user_query=input_data.question,
            retrieval_results=None,
            max_tokens=model_config.get_max_history_tokens() if model_config else 30000
        )
        
        # 执行检索
        retrieval_results = hybrid_retriever.retrieve(input_data.question)
        
        # 更新上下文
        context_info = context_skill.build_context(
            session_data=session_data,
            user_query=input_data.question,
            retrieval_results=retrieval_results,
            max_tokens=model_config.get_max_history_tokens() if model_config else 30000
        )
        
        # 构建提示词
        prompt = f"""基于以下上下文，回答用户问题：

上下文：
{context_info.get('context_text', '')}

用户问题：{input_data.question}

请提供专业、准确的回答。"""
        
        # 调用LLM
        response = llm.call(prompt)
        
        # 添加助手消息
        session_data.add_message(MessageRole.ASSISTANT, response)
        
        # 保存会话
        memory_skill._current_session = session_data
        memory_skill._update_session()
        
        # 返回响应
        return ChatResponse(
            success=True,
            message="追问处理成功",
            data={
                "response": response,
                "conversation_id": input_data.conversation_id,
                "intent": intent_info.get("intent"),
                "intent_confidence": intent_info.get("confidence"),
                "context_token_count": context_info.get("token_count"),
                "message_count": session_data.metadata.message_count
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"追问API失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"服务器错误: {str(e)}")


@router.post("/export", response_model=ExportResponse)
async def handle_export(input_data: ExportInput):
    """
    导出对话数据接口
    支持 OpenAI 和 Alpaca 格式
    """
    logger.info(f"收到导出请求：conversation_id={input_data.conversation_id}, format={input_data.format_type}")
    
    try:
        # 检查组件初始化
        if not memory_skill:
            raise HTTPException(status_code=500, detail="系统组件未初始化")
        
        # 加载会话
        session_data = memory_skill.load_session(input_data.conversation_id)
        
        if not session_data:
            raise HTTPException(status_code=404, detail="会话不存在")
        
        # 导出数据
        if input_data.format_type == "alpaca":
            export_data = session_data.get_alpaca_format()
            file_name = f"{input_data.conversation_id}_alpaca.jsonl"
        else:
            export_data = {"messages": session_data.get_openai_format()}
            file_name = f"{input_data.conversation_id}_openai.jsonl"
        
        # 返回响应
        return ExportResponse(
            success=True,
            message="导出成功",
            data={
                "export_data": export_data,
                "format": input_data.format_type,
                "file_name": file_name,
                "message_count": session_data.metadata.message_count
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"导出API失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"服务器错误: {str(e)}")


@router.get("/sessions/{user_id}")
async def list_sessions(user_id: str):
    """
    列出用户的所有会话
    """
    logger.info(f"收到会话列表请求：user_id={user_id}")
    
    try:
        # 检查组件初始化
        if not storage:
            raise HTTPException(status_code=500, detail="系统组件未初始化")
        
        # 获取会话列表
        sessions = storage.list_sessions(user_id=user_id)
        
        return {
            "success": True,
            "message": "会话列表获取成功",
            "data": {
                "sessions": sessions,
                "total": len(sessions)
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"会话列表API失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"服务器错误: {str(e)}")


@router.get("/session/{conversation_id}")
async def get_session(conversation_id: str):
    """
    获取会话详情
    """
    logger.info(f"收到会话详情请求：conversation_id={conversation_id}")
    
    try:
        # 检查组件初始化
        if not storage:
            raise HTTPException(status_code=500, detail="系统组件未初始化")
        
        # 加载会话
        session_data = storage.load_session(conversation_id)
        
        if not session_data:
            raise HTTPException(status_code=404, detail="会话不存在")
        
        return {
            "success": True,
            "message": "会话详情获取成功",
            "data": {
                "conversation_id": session_data.conversation_id,
                "user_id": session_data.user_id,
                "messages": session_data.get_openai_format(),
                "metadata": session_data.metadata.model_dump(),
                "message_count": session_data.metadata.message_count
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"会话详情API失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"服务器错误: {str(e)}")


@router.delete("/session/{conversation_id}")
async def delete_session(conversation_id: str):
    """
    删除会话
    """
    logger.info(f"收到删除会话请求：conversation_id={conversation_id}")
    
    try:
        # 检查组件初始化
        if not storage:
            raise HTTPException(status_code=500, detail="系统组件未初始化")
        
        # 删除会话
        success = storage.delete_session(conversation_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="会话删除失败")
        
        return {
            "success": True,
            "message": "会话删除成功"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除会话API失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"服务器错误: {str(e)}")


@router.post("/clear")
async def clear_session(input_data: ChatInput):
    """
    清空会话
    """
    logger.info(f"收到清空会话请求：conversation_id={input_data.conversation_id}")
    
    try:
        # 检查组件初始化
        if not memory_skill:
            raise HTTPException(status_code=500, detail="系统组件未初始化")
        
        # 加载会话
        session_data = memory_skill.load_session(input_data.conversation_id)
        
        if not session_data:
            raise HTTPException(status_code=404, detail="会话不存在")
        
        # 清空会话
        memory_skill.clear_session()
        
        return {
            "success": True,
            "message": "会话已清空"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"清空会话API失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"服务器错误: {str(e)}")