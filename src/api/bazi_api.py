"""
八字分析 FastAPI 接口定义
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any
from src.memory.memory_manager import memory_manager
import logging

from src.graph.bazi_graph import app
from src.graph.state import BaziAgentState

router = APIRouter(prefix="/api/v1/bazi", tags=["八字分析"])
logger = logging.getLogger(__name__)


class BaziInput(BaseModel):
    """八字输入模型"""
    year: int
    month: int
    day: int
    hour: int
    gender: str
    minute: int = 0
    timezone: str = "Asia/Shanghai"
    latitude: float = None
    longitude: float = None


class BaziResponse(BaseModel):
    """八字分析响应模型"""
    success: bool
    message: str
    data: Dict[str, Any] = {}


class FollowUpInput(BaseModel):
    """追问输入模型"""
    conversation_id: str
    question: str


@router.post("/followup", response_model=BaziResponse)
async def handle_followup(input_data: FollowUpInput):
    """
    追问接口
    支持多轮对话
    """
    logger.info(f"收到追问请求：conversation_id={input_data.conversation_id}")

    try:
        # 准备状态
        initial_state = {
            "conversation_id": input_data.conversation_id,
            "user_question": input_data.question,
            "status": "followup_initialized",
            "messages": []
        }

        # 执行追问节点
        # 这里可以单独调用节点，或者构建新的简化图
        from src.graph.nodes import handle_followup_question_node
        result = handle_followup_question_node(initial_state)

        if result.get("error"):
            raise HTTPException(status_code=400, detail=result["error"])

        return BaziResponse(
            success=True,
            message="追问处理成功",
            data={
                "response": result.get("followup_response"),
                "conversation_id": input_data.conversation_id
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"追问API失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"服务器错误: {str(e)}")

@router.post("/analyze", response_model=BaziResponse)
async def analyze_bazi(input_data: BaziInput):
    """八字分析接口"""
    logger.info(f"收到八字分析请求：{input_data.model_dump()}")

    try:
        # 创建对话
        conversation_id = memory_manager.create_conversation()

        # 准备初始状态
        initial_state: BaziAgentState = {
            "user_input": input_data.model_dump(),
            "conversation_id": conversation_id,  # 添加对话ID
            "status": "initialized",
            "messages": []
        }

        # 执行工作流
        final_state = await app.ainvoke(initial_state)

        # 存储八字数据到Memory
        if final_state.get("bazi_result"):
            memory_manager.store_bazi_data(
                conversation_id,
                {
                    "four_pillars": final_state["bazi_result"].get("four_pillars"),
                    "geju": final_state.get("geju_analysis", {}).get("geju_type"),
                    "yongshen": final_state.get("yongshen_analysis", {}).get("yongshen"),
                    "full_data": final_state.get("bazi_result")
                }
            )

        # 记录对话
        memory_manager.add_message(
            conversation_id,
            "user",
            f"请分析我的八字：{input_data.year}年{input_data.month}月{input_data.day}日{input_data.hour}时"
        )
        memory_manager.add_message(
            conversation_id,
            "assistant",
            final_state.get("llm_response", "")[:200] + "..."  # 摘要
        )

        # 返回响应
        response_data = {
            "input": input_data.model_dump(),
            "output": final_state.get("safe_output", {}),
            "conversation_id": conversation_id,  # 返回对话ID
            "final_status": final_state.get("status", "unknown")
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

@router.get("/health")
async def health_check():
    """健康检查接口"""
    return {"status": "healthy", "service": "bazi-analyzer-api"}

