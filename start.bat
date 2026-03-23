@echo off
REM 八字分析 Agent 启动脚本 (Windows)

echo ================================
echo   赛博司命 - 八字分析 Agent
echo   v0.2.0
echo ================================
echo.

REM 检查虚拟环境
if not exist ".venv" (
    echo ❌ 虚拟环境不存在，请先运行: python -m venv .venv
    exit /b 1
)

REM 激活虚拟环境
echo ✓ 激活虚拟环境...
call .venv\Scripts\activate.bat

REM 检查依赖
echo ✓ 检查依赖...
python -c "import fastapi, langgraph" 2>nul
if errorlevel 1 (
    echo ❌ 依赖缺失，请运行: pip install -r requirements.txt
    exit /b 1
)

REM 启动服务
echo ✓ 启动服务...
echo.
echo 服务地址: http://localhost:8000
echo API文档: http://localhost:8000/docs
echo.
echo 按 Ctrl+C 停止服务
echo.

python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
