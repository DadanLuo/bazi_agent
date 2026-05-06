"""
================================================================================
赛博司命 - 八字分析 Agent 主应用入口
================================================================================

功能说明：
    FastAPI 应用入口，配置中间件、路由和生命周期管理。

中间件执行顺序（洋葱模型）：
    请求 → LoggingMiddleware → RateLimitMiddleware → TimeoutMiddleware
         → CORSMiddleware → GZipMiddleware → 路由处理 → 响应

注册路由：
    - /api/v1/bazi/* - 八字分析 API
    - /health - 存活探针
    - /ready - 就绪探针

================================================================================
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from src.api.bazi_api import router as bazi_router
from src.api.bazi_chart_api import router as bazi_chart_router
from src.api.health import router as health_router
from src.api.tarot_api import router as tarot_router
from src.core.engine.bazi_calculator import BaziCalculator
from src.config.middleware_config import middleware_config

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = PROJECT_ROOT / "static"
INDEX_FILE = STATIC_DIR / "index.html"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理
    """
    # 启动时
    logger.info("八字分析 Agent 正在启动...")

    # 初始化计算器（可以在这里加载模型等）
    calculator = BaziCalculator()
    app.state.calculator = calculator

    yield

    # 关闭时
    logger.info("八字分析 Agent 正在关闭...")


# 创建 FastAPI 应用
app = FastAPI(
    title="赛博司命 - 八字分析 Agent",
    description="基于 LangGraph 的智能八字分析系统",
    version="1.0.0",
    lifespan=lifespan
)

# ============================================================================
# 注册中间件（按洋葱模型顺序：后添加的先执行）
# ============================================================================

# 5. GZip 压缩中间件
app.add_middleware(
    GZipMiddleware,
    minimum_size=1000  # 大于 1KB 的响应才压缩
)

# 4. CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境中应限制为特定域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. 超时中间件
try:
    from src.middleware.timeout import TimeoutMiddleware
    app.add_middleware(TimeoutMiddleware)
    logger.info("超时中间件注册成功")
except ImportError as e:
    logger.warning(f"超时中间件导入失败，跳过: {e}")

# 2. 限流中间件
try:
    from src.middleware.rate_limit import RateLimitMiddleware
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=middleware_config.RATE_LIMIT_PER_MINUTE,
        llm_requests_per_minute=middleware_config.RATE_LIMIT_LLM_PER_MINUTE,
        whitelist=middleware_config.RATE_LIMIT_WHITELIST
    )
    logger.info("限流中间件注册成功")
except ImportError as e:
    logger.warning(f"限流中间件导入失败，跳过: {e}")

# 1. 日志中间件（最外层，最先执行）
try:
    from src.middleware.logging_middleware import LoggingMiddleware
    app.add_middleware(
        LoggingMiddleware,
        slow_request_threshold=middleware_config.SLOW_REQUEST_THRESHOLD,
        skip_paths=middleware_config.LOG_SKIP_PATHS
    )
    logger.info("日志中间件注册成功")
except ImportError as e:
    logger.warning(f"日志中间件导入失败，跳过: {e}")


# ============================================================================
# 注册路由
# ============================================================================

# 静态资源
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# 八字分析 API
app.include_router(bazi_router)
app.include_router(bazi_chart_router)
app.include_router(tarot_router)

# 健康检查 API
app.include_router(health_router)


@app.get("/")
async def root():
    """
    根路径 - 返回前端页面
    """
    if INDEX_FILE.exists():
        return FileResponse(INDEX_FILE)

    return {
        "message": "欢迎使用赛博司命八字分析 Agent",
        "version": "1.0.0",
        "endpoints": [
            "/api/v1/bazi/analyze",
            "/api/v1/bazi/health",
            "/health",
            "/ready"
        ]
    }


@app.get("/service-info")
async def service_info():
    """
    服务信息接口
    """
    return {
        "message": "欢迎使用赛博司命八字分析 Agent",
        "version": "1.0.0",
        "endpoints": [
            "/api/v1/bazi/analyze",
            "/api/v1/bazi/health",
            "/health",
            "/ready",
            "/service-info"
        ]
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
