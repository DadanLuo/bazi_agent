"""测试工作流"""
import asyncio
import logging
from src.graph.bazi_graph import app
from src.graph.state import BaziAgentState

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def test_workflow():
    """测试完整工作流"""
    initial_state: BaziAgentState = {
        "user_input": {
            "year": 1990,
            "month": 1,
            "day": 1,
            "hour": 12,
            "minute": 0,
            "gender": "男"
        },
        "conversation_id": "test_conv",
        "status": "initialized",
        "messages": []
    }

    print("开始执行工作流...")
    final_state = await app.ainvoke(initial_state)

    print("\n" + "="*50)
    print("最终状态:")
    print(f"status: {final_state.get('status')}")
    print(f"safe_output: {final_state.get('safe_output')}")
    print(f"final_report: {final_state.get('final_report')}")
    print(f"error: {final_state.get('error')}")
    print("="*50)

    return final_state

if __name__ == "__main__":
    asyncio.run(test_workflow())
