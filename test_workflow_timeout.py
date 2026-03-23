"""测试工作流 - 带超时控制"""
import asyncio
import logging
from src.graph.bazi_graph import app
from src.graph.state import BaziAgentState

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def test_workflow_with_timeout():
    """测试完整工作流（带超时）"""
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

    print("开始执行工作流（30秒超时）...")
    try:
        final_state = await asyncio.wait_for(
            app.ainvoke(initial_state),
            timeout=30.0
        )

        print("\n" + "="*50)
        print("最终状态:")
        print(f"status: {final_state.get('status')}")

        safe_output = final_state.get('safe_output', {})
        print(f"\nsafe_output.message: {safe_output.get('message')}")

        data = safe_output.get('data', {})
        if data:
            print(f"\n数据内容:")
            if 'basic_data' in data:
                basic = data['basic_data']
                print(f"  - 八字: {basic.get('bazi', {})}")
                print(f"  - 五行: {basic.get('wuxing', {})}")
                print(f"  - 格局: {basic.get('geju', {})}")
                print(f"  - 喜用神: {basic.get('yongshen', {})}")

        print("="*50)
        return final_state

    except asyncio.TimeoutError:
        print("\n❌ 工作流执行超时（30秒）")
        print("可能原因：API调用卡住或网络问题")
        return None
    except Exception as e:
        print(f"\n❌ 工作流执行失败: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    asyncio.run(test_workflow_with_timeout())
