# src/api/health.py
"""
健康检查端点

- GET /health  — 存活探针（liveness），进程活着就返回 200
- GET /ready   — 就绪探针（readiness），检查核心依赖
"""
import time
import logging
from typing import Dict, Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["健康检查"])

_start_time = time.time()


def _check_redis() -> Dict[str, Any]:
    """检查 Redis 连通性"""
    try:
        from src.dependencies import redis_cache
        if not redis_cache or not redis_cache.client:
            return {"status": "unavailable", "message": "Redis 未配置或未连接"}
        redis_cache.client.ping()
        return {"status": "healthy"}
    except Exception as e:
        return {"status": "unhealthy", "message": str(e)}


def _check_llm() -> Dict[str, Any]:
    """检查 LLM 可用性（仅检查 API Key，不实际调用）"""
    try:
        from src.dependencies import llm
        if not llm:
            return {"status": "unavailable", "message": "LLM 未初始化"}
        if not llm.api_key:
            return {"status": "degraded", "message": "DASHSCOPE_API_KEY 未配置"}
        return {"status": "healthy"}
    except Exception as e:
        return {"status": "unhealthy", "message": str(e)}


def _check_vector_store() -> Dict[str, Any]:
    """检查向量检索可用性"""
    try:
        from src.dependencies import hybrid_retriever
        if not hybrid_retriever:
            return {"status": "unavailable", "message": "检索器未初始化"}
        return {"status": "healthy"}
    except Exception as e:
        return {"status": "unhealthy", "message": str(e)}


@router.get("/health")
async def liveness():
    """存活探针 — 进程活着就返回 200"""
    return {
        "status": "alive",
        "uptime_seconds": round(time.time() - _start_time, 1),
    }


@router.get("/ready")
async def readiness():
    """就绪探针 — 检查核心依赖是否就绪"""
    checks = {
        "redis": _check_redis(),
        "llm": _check_llm(),
        "vector_store": _check_vector_store(),
    }

    all_healthy = all(c["status"] in ("healthy", "degraded") for c in checks.values())
    overall = "ready" if all_healthy else "not_ready"
    status_code = 200 if all_healthy else 503

    return JSONResponse(
        status_code=status_code,
        content={
            "status": overall,
            "checks": checks,
            "uptime_seconds": round(time.time() - _start_time, 1),
        },
    )
