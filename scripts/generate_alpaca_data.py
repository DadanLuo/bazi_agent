"""
LlamaFactory 微调数据生成脚本 (完整版)
生成专业的八字分析报告
"""
import sys
import os
import json
import random
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

sys.path.append(str(Path(__file__).parent.parent))

from src.core.engine.bazi_calculator import BaziCalculator
from src.core.engine.dayun import DayunEngine
from src.core.engine.geju import GejuEngine
from src.core.engine.yongshen import YongshenEngine
from src.core.engine.liunian import LiunianEngine
from src.core.engine.solar_terms import SolarTermsCalculator
from src.core.engine.wuxing_calculator import WuxingCalculator
from src.core.models.bazi_models import BirthInfo

# 初始化引擎
calculator = BaziCalculator()
dayun_engine = DayunEngine()
geju_engine = GejuEngine()
yongshen_engine = YongshenEngine()
liunian_engine = LiunianEngine()
solar_calc = SolarTermsCalculator()
wuxing_calc = WuxingCalculator()

SYSTEM_INSTRUCTION = """你是一位精通八字命理的专业分析师，拥有深厚的易学理论基础和丰富的实战经验。
请根据提供的出生信息，运用《子平真诠》《滴天髓》《三命通会》等经典理论，
进行精准排盘，并给出格局、五行、喜用神、大运流年的详细分析。
分析要客观、专业、有条理，既要有理论依据，也要有实际指导意义。"""


def random_date(start_year=1960, end_year=2010):
    """生成随机日期"""
    start = datetime(start_year, 1, 1)
    end = datetime(end_year, 12, 31)
    delta = end - start
    random_days = random.randint(0, delta.days)
    random_seconds = random.randint(0, 86399)
    return start + timedelta(days=random_days, seconds=random_seconds)


def get_pillar_name(pillar_dict):
    """将字典形式的柱转换为中文名称"""
    tg = pillar_dict['tiangan']
    dz = pillar_dict['dizhi']

    # 处理枚举值
    if hasattr(tg, 'value'):
        tg = tg.value
    if hasattr(dz, 'value'):
        dz = dz.value

    return f"{tg}{dz}"


def generate_comprehensive_report(bazi_result, geju, yongshen, dayun_res, liunian_res, birth_info):
    """
    生成完整的专业八字分析报告
    """
    four_pillars = bazi_result['four_pillars']
    wuxing = bazi_result['wuxing_score']

    report = []

    # ========== 一、八字排盘 ==========
    report.append("【一、八字排盘】\n")
    report.append(
        f"出生时间：{birth_info.year}年{birth_info.month}月{birth_info.day}日 {birth_info.hour}:{birth_info.minute:02d}")
    report.append(f"性别：{birth_info.gender}")
    report.append(f"出生地：经度{birth_info.longitude}°，纬度{birth_info.latitude}°\n")

    report.append("四柱八字：")
    report.append(f"  年柱：{get_pillar_name(four_pillars['year'])}")
    report.append(f"  月柱：{get_pillar_name(four_pillars['month'])}")
    report.append(f"  日柱：{get_pillar_name(four_pillars['day'])}  （日主）")
    report.append(f"  时柱：{get_pillar_name(four_pillars['hour'])}\n")

    # ========== 二、五行分析 ==========
    report.append("【二、五行分析】\n")
    report.append("五行力量分布：")
    report.append(f"  木：{wuxing['mu']}分")
    report.append(f"  火：{wuxing['huo']}分")
    report.append(f"  土：{wuxing['tu']}分")
    report.append(f"  金：{wuxing['jin']}分")
    report.append(f"  水：{wuxing['shui']}分\n")

    # 五行旺衰判断
    scores = {
        '木': wuxing['mu'],
        '火': wuxing['huo'],
        '土': wuxing['tu'],
        '金': wuxing['jin'],
        '水': wuxing['shui']
    }
    sorted_wx = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    report.append(f"五行最旺：{sorted_wx[0][0]}（{sorted_wx[0][1]}分）")
    report.append(f"五行最弱：{sorted_wx[-1][0]}（{sorted_wx[-1][1]}分）\n")

    # 五行平衡度
    total = sum(scores.values())
    avg = total / 5
    variance = sum((v - avg) ** 2 for v in scores.values()) / 5

    if variance < 1000:
        balance = "五行较为均衡，无明显偏颇"
    elif variance < 5000:
        balance = "五行略有偏颇，需注意调节"
    else:
        balance = "五行失衡严重，亟需调候"

    report.append(f"五行平衡度：{balance}\n")

    # ========== 三、格局分析 ==========
    report.append("【三、格局分析】\n")
    geju_type = geju.get('geju_type', '常格')
    geju_desc = geju.get('description', '无明显格局特征，以五行平衡论命')

    report.append(f"命局格局：{geju_type}")
    report.append(f"格局特征：{geju_desc}\n")

    # 格局详解
    geju_details = {
        "正官格": "为人正直，有责任感，适合管理、公务员等职业。性格稳重，做事有条理。",
        "七杀格": "性格刚强，有决断力，适合创业、军警等职业。勇敢果断，但需控制冲动。",
        "正印格": "为人仁慈，有学识，适合教育、文化等职业。聪明好学，心地善良。",
        "偏印格": "思维独特，有专长，适合技术、艺术等职业。悟性高，但性格孤僻。",
        "正财格": "勤俭持家，重实际，适合财务、经商等职业。踏实稳重，善于理财。",
        "偏财格": "善于理财，有商业头脑，适合投资、经商等职业。慷慨大方，人缘好。",
        "食神格": "才华横溢，有艺术天赋，适合文艺、设计等职业。性格温和，乐观向上。",
        "伤官格": "聪明伶俐，有创造力，适合创新行业。但需注意言辞，避免得罪人。",
        "从弱格": "日主衰弱至极，宜从其弱势。顺势而为，不可强求。",
        "魁罡格": "魁罡日出生，性格刚强，有领导才能。适合管理岗位。",
        "日德格": "日德坐命，为人慈善，有福报。一生多得贵人相助。",
        "常格": "无明显格局特征，以五行平衡论命。宜根据喜用神进行调整。"
    }

    if geju_type in geju_details:
        report.append(f"格局详解：{geju_details[geju_type]}\n")

    # ========== 四、喜用神分析 ==========
    report.append("【四、喜用神分析】\n")
    yongshen_list = yongshen.get('yongshen', [])
    jishen_list = yongshen.get('jishen', [])
    reason = yongshen.get('reason', '')

    report.append(f"喜用神：{', '.join(yongshen_list) if yongshen_list else '需综合判断'}")
    report.append(f"忌神：{', '.join(jishen_list) if jishen_list else '需综合判断'}\n")
    report.append(f"推导依据：{reason}\n")

    # 喜用神应用建议
    report.append("喜用神应用建议：")

    yongshen_advice = {
        "木": "适合从事教育、文化、出版、林业等行业。宜往东方发展。穿戴绿色系服饰有利。",
        "火": "适合从事IT、电子、能源、餐饮等行业。宜往南方发展。穿戴红色系服饰有利。",
        "土": "适合从事房地产、建筑、农业、物流等行业。宜本地发展。穿戴黄色系服饰有利。",
        "金": "适合从事金融、法律、机械、珠宝等行业。宜往西方发展。穿戴白色系服饰有利。",
        "水": "适合从事贸易、航运、水产、服务业等行业。宜往北方发展。穿戴黑蓝色系服饰有利。"
    }

    for ys in yongshen_list:
        if ys in yongshen_advice:
            report.append(f"  • {yongshen_advice[ys]}")

    report.append("")

    # ========== 五、大运分析 ==========
    if dayun_res:
        report.append("【五、大运分析】\n")
        report.append(f"起运年龄：{dayun_res['qiyun_age']}岁")
        report.append(f"运行方向：{dayun_res['direction']}\n")

        # 当前大运
        current_dayun = dayun_res.get('current_dayun')
        if current_dayun:
            pillar_wrapper = current_dayun['pillar']
            actual_pillar = pillar_wrapper.pillar

            tg = actual_pillar.tiangan.value if hasattr(actual_pillar.tiangan, 'value') else str(actual_pillar.tiangan)
            dz = actual_pillar.dizhi.value if hasattr(actual_pillar.dizhi, 'value') else str(actual_pillar.dizhi)

            analysis = current_dayun['analysis']

            report.append(f"当前大运：{current_dayun['age_range']}，{tg}{dz}运")
            report.append(f"运势等级：{analysis['level']}")
            report.append(f"运势描述：{analysis['description']}\n")

            if analysis.get('advice'):
                report.append("运程建议：")
                for advice in analysis['advice']:
                    report.append(f"  • {advice}")
                report.append("")

        # 大运总览
        overall = dayun_res.get('overall_analysis', '')
        if overall:
            report.append(f"大运总评：{overall}\n")

    # ========== 六、流年分析 ==========
    if liunian_res:
        report.append("【六、流年分析】\n")
        current_year = datetime.now().year
        current_liunian = liunian_res.get('current_year')

        if current_liunian:
            pillar = current_liunian['pillar']
            tg = pillar.tiangan.value if hasattr(pillar.tiangan, 'value') else str(pillar.tiangan)
            dz = pillar.dizhi.value if hasattr(pillar.dizhi, 'value') else str(pillar.dizhi)

            report.append(f"当前流年：{current_year}年，{tg}{dz}年")
            report.append(f"流年分析：{current_liunian.get('analysis', '平稳发展')}\n")

    # ========== 七、综合建议 ==========
    report.append("【七、综合建议】\n")

    # 根据格局和喜用神给出综合建议
    suggestions = []

    if geju_type == "正官格":
        suggestions.append("事业发展：适合体制内或大型企业，稳扎稳打，循序渐进。")
    elif geju_type == "七杀格":
        suggestions.append("事业发展：适合创业或挑战性工作，勇敢果断，但需控制风险。")
    elif geju_type == "正印格":
        suggestions.append("事业发展：适合学术研究或教育事业，修身养性，积累知识。")
    elif geju_type in ["正财格", "偏财格"]:
        suggestions.append("事业发展：适合经商或财务管理，精打细算，稳健投资。")

    if '水' in yongshen_list or '木' in yongshen_list:
        suggestions.append("健康养生：注意肝肾保养，多食黑色绿色食物，适量运动。")
    if '火' in yongshen_list or '土' in yongshen_list:
        suggestions.append("健康养生：注意心脑血管和脾胃保养，饮食规律，心态平和。")
    if '金' in yongshen_list:
        suggestions.append("健康养生：注意呼吸系统保养，多食白色食物，保持空气清新。")

    suggestions.append("心态调整：命由己造，相由心生。知命而不认命，顺势而为，自强不息。")

    for i, sug in enumerate(suggestions, 1):
        report.append(f"{i}. {sug}")

    report.append("\n【结语】")
    report.append("命理分析仅供参考，人生道路还需自己把握。愿您知命懂运，趋吉避凶，成就美好人生！")

    return "\n".join(report)


def generate_one_sample():
    """生成单条完整数据"""
    dt = random_date()
    gender = random.choice(["男", "女"])
    lon = round(random.uniform(100.0, 130.0), 2)
    lat = round(random.uniform(20.0, 45.0), 2)

    birth_info = BirthInfo(
        year=dt.year, month=dt.month, day=dt.day,
        hour=dt.hour, minute=dt.minute,
        gender=gender, longitude=lon, latitude=lat
    )

    try:
        # 1. 基础排盘
        bazi_result = calculator.calculate(birth_info)
        pillars = bazi_result.four_pillars

        # 2. 格局分析
        day_master_strength = wuxing_calc.get_day_master_strength(pillars)
        geju_res = geju_engine.determine_geju(pillars, day_master_strength)

        # 3. 喜用神分析
        yongshen_res = yongshen_engine.determine_yongshen(
            pillars, day_master_strength, geju_res
        )

        # 4. 大运分析
        year_terms = solar_calc.get_solar_terms_in_year(birth_info.year)
        adjusted_dt, _ = calculator._get_adjusted_time(birth_info)
        current_age = datetime.now().year - birth_info.year

        dayun_res = dayun_engine.analyze_dayun(
            pillars, yongshen_res, adjusted_dt, birth_info.gender, year_terms, current_age
        )

        # 5. 流年分析
        liunian_res = liunian_engine.analyze_liunian(
            pillars, yongshen_res, datetime.now().year
        )

        # 6. 生成完整报告
        user_input = f"出生时间：{dt.year}年{dt.month}月{dt.day}日 {dt.hour}:{dt.minute:02d}，性别：{gender}，出生地经纬度：({lon}, {lat})"

        model_output = generate_comprehensive_report(
            bazi_result.model_dump(),
            geju_res,
            yongshen_res,
            dayun_res,
            liunian_res,
            birth_info
        )

        return {
            "instruction": SYSTEM_INSTRUCTION,
            "input": user_input,
            "output": model_output
        }

    except Exception as e:
        print(f"Error generating sample: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    parser = argparse.ArgumentParser(description="生成八字微调数据集")
    parser.add_argument("--count", type=int, default=1000, help="生成的数据条数")
    parser.add_argument("--output", type=str, default="data/bazi_train.json", help="输出文件路径")
    parser.add_argument("--overwrite", action="store_true", help="是否覆盖已有文件")

    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    existing_data = []
    if not args.overwrite and output_path.exists():
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                content = f.read()
                if content.strip().startswith("["):
                    existing_data = json.loads(content)
                    print(f"检测到已有数据 {len(existing_data)} 条，将追加新数据...")
        except Exception as e:
            print(f"读取已有文件失败，将重新创建: {e}")
            existing_data = []

    existing_keys = set()
    for item in existing_data:
        if "input" in item:
            existing_keys.add(item["input"])

    new_data = []
    count = 0
    attempts = 0
    max_attempts = args.count * 3

    print(f"开始生成 {args.count} 条新数据...")

    while count < args.count and attempts < max_attempts:
        attempts += 1
        sample = generate_one_sample()

        if sample:
            if sample["input"] not in existing_keys:
                new_data.append(sample)
                existing_keys.add(sample["input"])
                count += 1

                if count % 10 == 0:
                    print(f"已生成: {count}/{args.count}")

    final_data = existing_data + new_data

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(final_data, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 任务完成！")
    print(f"新增数据: {len(new_data)} 条")
    print(f"总数据量: {len(final_data)} 条")
    print(f"保存位置: {output_path}")


if __name__ == "__main__":
    main()
