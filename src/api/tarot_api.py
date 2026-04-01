"""塔罗占卜 FastAPI 接口定义"""

from typing import Any, Dict, Optional

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.agents.tarot_agent import TarotAgent
from src.dependencies import get_session_context
from src.graph.tarot_graph import tarot_app
from src.graph.tarot_state import TarotAgentState

router = APIRouter(prefix="/api/v1/tarot", tags=["塔罗占卜"])
logger = logging.getLogger(__name__)


class TarotInput(BaseModel):
    question: str = Field(..., min_length=1, description="用户的占卜问题")
    question_type: str = Field(default="综合", description="问题类型")
    spread_type: Optional[str] = Field(default=None, description="可选牌阵")
    conversation_id: Optional[str] = Field(default=None, description="会话ID")
    user_id: str = Field(default="web_user", description="用户ID")


class TarotFollowupInput(BaseModel):
    conversation_id: str
    query: str
    user_id: str = "web_user"


class TarotResponse(BaseModel):
    success: bool
    message: str
    data: Dict[str, Any] = {}


def _normalize_tarot_output(final_state: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any]]:
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
        return safe_output, {"message": "占卜完成", "blocked": False}

    tarot_result = final_state.get("tarot_result")
    if isinstance(tarot_result, dict):
        return tarot_result, {"message": "占卜完成", "blocked": False}

    return {}, {"message": "占卜完成", "blocked": False}


@router.post("/analyze", response_model=TarotResponse)
async def analyze_tarot(input_data: TarotInput) -> TarotResponse:
    logger.info(f"收到塔罗占卜请求：{input_data.model_dump()}")

    try:
        request_payload = input_data.model_dump()
        question = request_payload["question"].strip()
        question_type = request_payload.get("question_type") or "综合"
        spread_type = request_payload.get("spread_type") or ""
        conversation_id = request_payload.get("conversation_id")
        user_id = request_payload.get("user_id", "web_user")

        session_ctx = get_session_context()
        if conversation_id:
            session_ctx.load_session(conversation_id)
        if not session_ctx.get_session():
            session_ctx.create_session(user_id=user_id, agent_id="tarot")

        session = session_ctx.get_session()
        if session:
            session.metadata.agent_id = "tarot"

        user_msg = f"用户想进行塔罗牌占卜。\n问题类型：{question_type}\n具体问题：{question}\n"
        if spread_type:
            user_msg += f"用户指定牌阵：{spread_type}\n"
        else:
            user_msg += "用户未指定牌阵，请你根据问题自主选择合适的牌阵。\n"
        user_msg += "\n请开始占卜流程。"

        if session:
            session_ctx.add_message("user", question)

        initial_state: TarotAgentState = {
            "user_input": {
                "question_type": question_type,
                "spread_type": spread_type,
                "specific_question": question,
            },
            "user_query": question,
            "messages": [{"role": "user", "content": user_msg}],
            "conversation_id": session.metadata.conversation_id if session else None,
            "user_id": user_id,
            "iteration": 0,
            "pending_tool_calls": [],
            "executor_state": {},
            "status": "initialized",
        }

        final_state = await tarot_app.ainvoke(initial_state)

        if final_state.get("error") and final_state.get("status") != "safety_blocked":
            logger.error(f"塔罗工作流执行失败：{final_state['error']}")
            raise HTTPException(status_code=400, detail=final_state["error"])

        normalized_output, safety_info = _normalize_tarot_output(final_state)
        response_text = final_state.get("llm_response", "")
        if session:
            session_ctx.absorb_graph_result(final_state)
            session_ctx.add_message("assistant", response_text or normalized_output.get("synthesis") or safety_info.get("message", "占卜完成"))
            session_ctx.save(force=True)

        return TarotResponse(
            success=True,
            message="塔罗占卜成功",
            data={
                "input": request_payload,
                "output": normalized_output,
                "response_text": response_text,
                "safety": safety_info,
                "final_status": final_state.get("status", "unknown"),
                "conversation_id": session.metadata.conversation_id if session else None,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"塔罗 API 处理失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"服务器内部错误：{str(e)}")


@router.post("/followup", response_model=TarotResponse)
async def followup_tarot(input_data: TarotFollowupInput) -> TarotResponse:
    logger.info(f"收到塔罗追问请求：conversation_id={input_data.conversation_id}")

    session_ctx = get_session_context()
    session_ctx.load_session(input_data.conversation_id)
    session = session_ctx.get_session()

    if not session:
        raise HTTPException(status_code=404, detail="会话不存在，请先进行一次塔罗占卜")

    session.metadata.agent_id = "tarot"
    agent = TarotAgent()

    session_ctx.add_message("user", input_data.query)
    response_text = await agent.handle_followup(session, input_data.query)
    session_ctx.add_message("assistant", response_text)
    session_ctx.save(force=True)

    return TarotResponse(
        success=True,
        message="塔罗追问成功",
        data={
            "conversation_id": session.metadata.conversation_id,
            "response": response_text,
        }
    )
