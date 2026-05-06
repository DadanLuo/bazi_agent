# src/api/health.py
"""
健康检查端点

本模块提供 Kubernetes 风格的健康检查探针，用于服务监控和容器编排。

健康检查探针类型：
- Liveness Probe (/health): 检查进程是否存活，进程活着就返回 200
- Readiness Probe (/ready): 检查服务是否就绪，检查核心依赖是否可用

使用方式：
    from src.api.health import router
    app.include_router(router)
"""
import time
import logging
from typing import Dict, Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# 创建健康检查路由
router = APIRouter(tags=["健康检查"])

# 记录服务启动时间，用于计算运行时长
_start_time = time.time()


def _check_redis() -> Dict[str, Any]:
    """
    检查 Redis 连通性
    
    尝试连接 Redis 并执行 ping 命令，验证 Redis 服务是否可用。
    
    Returns:
        Dict[str, Any]: Redis 连接状态
            - status: "healthy" | "unhealthy" | "unavailable"
            - message: 状态描述信息
    """
    try:
        from src.dependencies import redis_cache
        if not redis_cache or not redis_cache.client:
            return {
                "status": "degraded",
                "message": "Redis 未配置或未连接，系统已降级为无 Redis 模式",
            }
        redis_cache.client.ping()
        return {"status": "healthy"}
    except Exception as e:
        return {"status": "unhealthy", "message": str(e)}


def _check_llm() -> Dict[str, Any]:
    """
    检查 LLM 可用性（仅检查 API Key，不实际调用）
    
    验证 LLM API Key 是否配置，但不实际调用 API。
    
    Returns:
        Dict[str, Any]: LLM 可用性状态
            - status: "healthy" | "degraded" | "unavailable"
            - message: 状态描述信息
    """
    try:
        from src.dependencies import llm
        if not llm:
            return {"status": "unavailable", "message": "LLM 未初始化"}
        if not llm.api_key:
            return {"status": "degraded", "message": "LLM API Key 未配置"}
        return {"status": "healthy"}
    except Exception as e:
        return {"status": "unhealthy", "message": str(e)}


def _check_vector_store() -> Dict[str, Any]:
    """
    检查向量检索可用性
    
    验证向量检索器是否已初始化。
    
    Returns:
        Dict[str, Any]: 向量检索器状态
            - status: "healthy" | "unavailable"
            - message: 状态描述信息
    """
    try:
        from src.dependencies import retriever
        if not retriever:
            return {"status": "unavailable", "message": "检索器未初始化"}
        return {"status": "healthy"}
    except Exception as e:
        return {"status": "unhealthy", "message": str(e)}


@router.get("/health")
async def liveness() -> Dict[str, Any]:
    """
    存活探针（Liveness Probe）
    
    检查进程是否存活，只要进程活着就返回 200。
    用于 Kubernetes 判断是否需要重启容器。
    
    Returns:
        Dict[str, Any]: 进程存活状态
            - status: "alive"
            - uptime_seconds: 服务运行时长（秒）
    """
    return {
        "status": "alive",
        "uptime_seconds": round(time.time() - _start_time, 1),
    }


@router.get("/ready")
async def readiness() -> JSONResponse:
    """
    就绪探针（Readiness Probe）
    
    检查服务是否就绪，检查核心依赖（Redis、LLM、向量存储）是否可用。
    所有依赖都就绪时返回 200，否则返回 503。
    
    Returns:
        JSONResponse: 服务就绪状态
            - status: "ready" | "not_ready"
            - checks: 各依赖的检查结果
            - uptime_seconds: 服务运行时长（秒）
    """
    checks = {
        "redis": _check_redis(),
        "llm": _check_llm(),
        "vector_store": _check_vector_store(),
    }

    # 判断所有检查是否都通过（degraded 状态也算通过）
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
