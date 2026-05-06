from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.core.engine.bazi_chart_skill import BaziChartSkill
from src.core.models.bazi_chart_models import BaziChartRequest, BaziChartResponse
from src.core.exceptions import ValidationError as BaziValidationError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/bazi", tags=["八字排盘 Skill"])
skill = BaziChartSkill()


class BaziChartApiEnvelope(BaseModel):
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="响应消息")
    data: BaziChartResponse | dict[str, Any] = Field(..., description="排盘结果")


@router.post("/chart", response_model=BaziChartApiEnvelope)
async def generate_bazi_chart(payload: BaziChartRequest) -> BaziChartApiEnvelope:
    try:
        result = skill.chart(payload)
        return BaziChartApiEnvelope(
            success=True,
            message="八字排盘完成",
            data=result,
        )
    except BaziValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("八字排盘 Skill 执行失败: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"排盘失败：{exc}") from exc
