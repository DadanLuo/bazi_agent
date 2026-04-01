"""
八字分析 FastAPI 接口定义

本模块提供八字命理分析的 HTTP API 接口，基于 FastAPI 框架实现。
主要功能：
- 八字排盘分析
- 健康检查

使用方式：
    from src.api.bazi_api import router
    app.include_router(router)
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional, Literal
import logging

from src.agents.bazi_agent import BaziAgent
from src.dependencies import get_session_context
from src.graph.bazi_graph import app as bazi_app
from src.graph.simple_graph import simple_app
from src.graph.state import BaziAgentState

# 创建 API 路由
router = APIRouter(prefix="/api/v1/bazi", tags=["八字分析"])
logger = logging.getLogger(__name__)


class BaziInput(BaseModel):
    """
    八字输入模型
    
    定义八字排盘所需的输入参数，所有字段都是必需的（除可选字段外）。
    
    Attributes:
        year: 出生年份（4位数字）
        month: 出生月份（1-12）
        day: 出生日（1-31）
        hour: 出生小时（0-23）
        gender: 性别（"男" 或 "女"）
        minute: 出生分钟（可选，默认为 0）
        timezone: 时区（可选，默认为 "Asia/Shanghai"）
        latitude: 纬度（可选，用于精确计算）
        longitude: 经度（可选，用于精确计算）
    """
    year: int
    month: int
    day: int
    hour: int
    gender: str
    minute: int = 0
    timezone: str = "Asia/Shanghai"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    analysis_mode: Literal["full", "simple"] = "full"
    conversation_id: Optional[str] = None
    user_id: str = "web_user"


class FollowupInput(BaseModel):
    conversation_id: str
    query: str
    user_id: str = "web_user"


class BaziResponse(BaseModel):
    """
    八字分析响应模型
    
    定义 API 返回的响应格式。
    
    Attributes:
        success: 是否成功
        message: 响应消息
        data: 响应数据
    """
    success: bool
    message: str
    data: Dict[str, Any] = {}


def _normalize_gender(gender: str) -> str:
    mapping = {
        "male": "男",
        "female": "女",
        "男": "男",
        "女": "女",
    }
    return mapping.get(gender, gender)


def _normalize_graph_output(final_state: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any]]:
    safe_output = final_state.get("safe_output")

    if isinstance(safe_output, dict) and "data" in safe_output and "blocked" in safe_output:
        normalized_output = safe_output.get("data") or {}
        safety_info = {
            "message": safe_output.get("message", ""),
            "blocked": safe_output.get("blocked", False),
            "blocked_category": safe_output.get("blocked_category"),
        }
        return normalized_output, safety_info

    if isinstance(safe_output, dict):
        return safe_output, {"message": "分析完成", "blocked": False}

    final_report = final_state.get("final_report")
    if isinstance(final_report, dict):
        return final_report, {"message": "分析完成", "blocked": False}

    return {}, {"message": "分析完成", "blocked": False}


def _build_bazi_query(payload: Dict[str, Any]) -> str:
    minute = payload.get("minute", 0)
    gender = payload.get("gender", "男")
    return (
        f"请分析八字：{payload['year']}年{payload['month']}月{payload['day']}日"
        f"{payload['hour']}时{minute}分，{gender}"
    )


@router.post("/analyze", response_model=BaziResponse)
async def analyze_bazi(input_data: BaziInput) -> BaziResponse:
    """
    八字分析接口
    
    接收用户的出生信息，执行完整的八字排盘分析流程，
    包括：四柱计算、五行分析、格局判断、喜用神查找、流年分析等。
    
    Args:
        input_data: 八字输入数据，包含出生年月日时、性别等信息
        
    Returns:
        BaziResponse: 八字分析结果响应
        
    Raises:
        HTTPException: 当分析失败或发生错误时抛出
    """
    logger.info(f"收到八字分析请求：{input_data.model_dump()}")

    try:
        request_payload = input_data.model_dump()
        analysis_mode = request_payload.pop("analysis_mode", "full")
        conversation_id = request_payload.pop("conversation_id", None)
        user_id = request_payload.pop("user_id", "web_user")
        request_payload["gender"] = _normalize_gender(request_payload["gender"])
        query_text = _build_bazi_query(request_payload)

        session_ctx = get_session_context()
        if conversation_id:
            session_ctx.load_session(conversation_id)
        if not session_ctx.get_session():
            session_ctx.create_session(user_id=user_id, agent_id="bazi")

        session = session_ctx.get_session()
        if session:
            session.metadata.agent_id = "bazi"
            session_ctx.add_message("user", query_text)

        # 准备初始状态（使用字典而非 Pydantic 模型）
        initial_state: BaziAgentState = {
            "user_input": request_payload,
            "status": "initialized",
            "messages": session.get_openai_format() if session else []
        }

        # 执行 LangGraph 工作流
        graph_app = simple_app if analysis_mode == "simple" else bazi_app
        final_state = await graph_app.ainvoke(initial_state)

        # 检查最终状态是否包含错误
        if final_state.get("error") and final_state.get("status") != "safety_blocked":
            logger.error(f"工作流执行失败：{final_state['error']}")
            raise HTTPException(status_code=400, detail=final_state["error"])

        normalized_output, safety_info = _normalize_graph_output(final_state)
        response_text = (
            normalized_output.get("llm_analysis")
            or normalized_output.get("message")
            or safety_info.get("message", "分析完成")
        )

        if session:
            session_ctx.absorb_graph_result(final_state)
            session_ctx.add_message("assistant", response_text)
            session_ctx.save(force=True)

        # 返回成功响应
        response_data = {
            "input": request_payload,
            "output": normalized_output,
            "safety": safety_info,
            "analysis_mode": analysis_mode,
            "final_status": final_state.get("status", "unknown"),
            "conversation_id": session.metadata.conversation_id if session else None,
        }

        logger.info("八字分析完成")
        return BaziResponse(
            success=True,
            message="八字分析成功",
            data=response_data
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API 处理失败：{e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"服务器内部错误：{str(e)}"
        )


@router.post("/followup", response_model=BaziResponse)
async def followup_bazi(input_data: FollowupInput) -> BaziResponse:
    logger.info(f"收到八字追问请求：conversation_id={input_data.conversation_id}")

    session_ctx = get_session_context()
    session_ctx.load_session(input_data.conversation_id)
    session = session_ctx.get_session()

    if not session:
        raise HTTPException(status_code=404, detail="会话不存在，请先进行一次八字分析")

    session.metadata.agent_id = "bazi"
    agent = BaziAgent()

    session_ctx.add_message("user", input_data.query)
    response_text = await agent.handle_followup(session, input_data.query)
    session_ctx.add_message("assistant", response_text)
    session_ctx.save(force=True)

    return BaziResponse(
        success=True,
        message="八字追问成功",
        data={
            "conversation_id": session.metadata.conversation_id,
            "response": response_text,
        }
    )


@router.get("/health")
async def health_check() -> Dict[str, str]:
    """
    健康检查接口
    
    用于检查八字分析服务的运行状态。
    
    Returns:
        Dict: 服务健康状态信息
    """
    return {"status": "healthy", "service": "bazi-analyzer-api"}
