"""
演示测试脚本 - 验证所有核心功能
"""
import requests
import json
from datetime import datetime

BASE_URL = "http://localhost:8003"  # 根据实际端口修改

def print_section(title):
    """打印分节标题"""
    print("\n" + "="*60)
    print(f"  {title}")
    print("="*60)

def test_health():
    """测试健康检查"""
    print_section("1. 健康检查")
    response = requests.get(f"{BASE_URL}/api/v1/bazi/health")
    print(f"状态码: {response.status_code}")
    print(f"响应: {response.json()}")
    return response.status_code == 200

def test_simple_analyze():
    """测试简化版分析"""
    print_section("2. 简化版八字分析")

    test_data = {
        "year": 1990,
        "month": 1,
        "day": 1,
        "hour": 12,
        "minute": 0,
        "gender": "male"
    }

    print(f"请求数据: {json.dumps(test_data, ensure_ascii=False, indent=2)}")
    print("\n发送请求...")

    response = requests.post(
        f"{BASE_URL}/api/v1/bazi/analyze-simple",
        json=test_data,
        timeout=15
    )

    print(f"状态码: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print(f"\n✅ 分析成功！")

        # 提取关键信息
        output = data.get("data", {}).get("output", {})
        basic_data = output.get("basic_data", {})

        # 八字
        bazi = basic_data.get("bazi", {})
        print(f"\n【八字排盘】")
        print(f"  年柱: {bazi.get('year', {}).get('tiangan')}{bazi.get('year', {}).get('dizhi')}")
        print(f"  月柱: {bazi.get('month', {}).get('tiangan')}{bazi.get('month', {}).get('dizhi')}")
        print(f"  日柱: {bazi.get('day', {}).get('tiangan')}{bazi.get('day', {}).get('dizhi')}")
        print(f"  时柱: {bazi.get('hour', {}).get('tiangan')}{bazi.get('hour', {}).get('dizhi')}")

        # 五行
        wuxing = basic_data.get("wuxing", {}).get("score", {})
        print(f"\n【五行分析】")
        print(f"  木: {wuxing.get('mu')} | 火: {wuxing.get('huo')} | 土: {wuxing.get('tu')}")
        print(f"  金: {wuxing.get('jin')} | 水: {wuxing.get('shui')}")

        # 格局
        geju = basic_data.get("geju", {})
        print(f"\n【格局判断】")
        print(f"  格局: {geju.get('geju_type')}")
        print(f"  说明: {geju.get('description')}")

        # 喜用神
        yongshen = basic_data.get("yongshen", {})
        print(f"\n【喜用神】")
        print(f"  喜用神: {', '.join(yongshen.get('yongshen', []))}")
        print(f"  忌神: {', '.join(yongshen.get('jishen', []))}")

        # 流年
        liunian = basic_data.get("liunian", {})
        print(f"\n【流年运势】")
        print(f"  年份: {liunian.get('year')}年 ({liunian.get('ganzhi')})")
        print(f"  吉凶: {liunian.get('jixiong', {}).get('level')}")
        print(f"  说明: {liunian.get('jixiong', {}).get('description')}")

        # 大运
        dayun = basic_data.get("dayun", {})
        current_dayun = dayun.get("current_dayun", {})
        print(f"\n【当前大运】")
        print(f"  年龄段: {current_dayun.get('age_range')}")
        print(f"  运势: {current_dayun.get('analysis', {}).get('level')}")
        print(f"  说明: {current_dayun.get('analysis', {}).get('description')}")

        return True
    else:
        print(f"\n❌ 分析失败")
        print(f"错误: {response.text}")
        return False

def main():
    """主测试流程"""
    print("\n" + "🎯"*30)
    print("  赛博司命 - 八字分析 Agent 演示测试")
    print("  " + "🎯"*30)

    results = []

    # 测试1: 健康检查
    try:
        results.append(("健康检查", test_health()))
    except Exception as e:
        print(f"❌ 健康检查失败: {e}")
        results.append(("健康检查", False))

    # 测试2: 简化版分析
    try:
        results.append(("简化版分析", test_simple_analyze()))
    except Exception as e:
        print(f"❌ 简化版分析失败: {e}")
        results.append(("简化版分析", False))

    # 总结
    print_section("测试总结")
    for name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"  {name}: {status}")

    total = len(results)
    passed = sum(1 for _, success in results if success)
    print(f"\n总计: {passed}/{total} 通过")

    if passed == total:
        print("\n🎉 所有测试通过！系统运行正常，可以进行演示。")
    else:
        print("\n⚠️ 部分测试失败，请检查服务状态。")

if __name__ == "__main__":
    main()
