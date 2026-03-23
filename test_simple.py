"""简单测试 - 只测试核心计算功能"""
import asyncio
import logging
from src.core.models.bazi_models import BirthInfo
from src.core.engine.bazi_calculator import BaziCalculator

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def test_core():
    """测试核心计算功能"""
    print("="*50)
    print("测试八字核心计算功能")
    print("="*50)

    # 创建出生信息
    birth_info = BirthInfo(
        year=1990,
        month=1,
        day=1,
        hour=12,
        minute=0,
        gender="男"
    )

    print(f"\n出生信息: {birth_info.model_dump()}")

    # 计算八字
    calculator = BaziCalculator()
    result = calculator.calculate(birth_info)

    print(f"\n八字结果:")
    print(f"  年柱: {result.four_pillars.year}")
    print(f"  月柱: {result.four_pillars.month}")
    print(f"  日柱: {result.four_pillars.day}")
    print(f"  时柱: {result.four_pillars.hour}")

    print(f"\n五行统计:")
    print(f"  木: {result.wuxing_score.mu}")
    print(f"  火: {result.wuxing_score.huo}")
    print(f"  土: {result.wuxing_score.tu}")
    print(f"  金: {result.wuxing_score.jin}")
    print(f"  水: {result.wuxing_score.shui}")

    print("\n✅ 核心功能测试通过！")
    return result

if __name__ == "__main__":
    asyncio.run(test_core())
