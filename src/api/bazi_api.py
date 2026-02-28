"""
八字分析 FastAPI 接口定义
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any
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


@router.post("/analyze", response_model=BaziResponse)
async def analyze_bazi(input_data: BaziInput):
    """八字分析接口"""
    logger.info(f"收到八字分析请求：{input_data.model_dump()}")

    try:
        # 准备初始状态（使用字典而非 Pydantic 模型）
        initial_state: BaziAgentState = {
            "user_input": input_data.model_dump(),
            "status": "initialized",
            "messages": []
        }

        # 执行 LangGraph 工作流
        final_state = await app.ainvoke(initial_state)

        # 检查最终状态是否包含错误
        if final_state.get("error"):
            logger.error(f"工作流执行失败：{final_state['error']}")
            raise HTTPException(status_code=400, detail=final_state["error"])

        # 返回成功响应
        response_data = {
            "input": input_data.model_dump(),
            "output": final_state.get("safe_output", {}),
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