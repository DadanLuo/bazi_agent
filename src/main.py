"""
八字分析 Agent 主应用入口
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api.bazi_api import router as bazi_router
from src.core.engine.bazi_calculator import BaziCalculator

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境中应限制为特定域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(bazi_router)


@app.get("/")
async def root():
    """
    根路径
    """
    return {
        "message": "欢迎使用赛博司命八字分析 Agent",
        "version": "1.0.0",
        "endpoints": [
            "/api/v1/bazi/analyze",
            "/api/v1/bazi/health"
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