"""
八字微调数据生成脚本
功能：生成用于LLM微调的八字问答数据集
输出格式：JSONL (OpenAI Fine-tuning format)
"""
import sys
import os
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

# 添加项目根目录到路径
sys.path.append(str(Path(__file__).parent.parent))

from src.core.engine.bazi_calculator import BaziCalculator
from src.core.engine.dayun import DayunEngine
from src.core.engine.geju import GejuEngine
from src.core.engine.yongshen import YongshenEngine
from src.core.engine.liunian import LiunianEngine
from src.core.engine.solar_terms import SolarTermsCalculator
from src.core.models.bazi_models import BirthInfo

# 配置
OUTPUT_FILE = "data/training_data/bazi_qa_dataset.jsonl"
SAMPLE_SIZE = 1000  # 生成数据条数

# 初始化引擎
calculator = BaziCalculator()
dayun_engine = DayunEngine()
geju_engine = GejuEngine()
yongshen_engine = YongshenEngine()
liunian_engine = LiunianEngine()
solar_calc = SolarTermsCalculator()


def random_date(start_year=1970, end_year=2005):
    """生成随机日期"""
    start = datetime(start_year, 1, 1)
    end = datetime(end_year, 12, 31)
    delta = end - start
    random_days = random.randint(0, delta.days)
    random_seconds = random.randint(0, 86399)
    return start + timedelta(days=random_days, seconds=random_seconds)


def get_expert_response(bazi_result, geju, yongshen, dayun_res):
    """
    根据计算结果生成专家回复
    这里我们使用模板化的回复，但在微调时模型会学习这些结构
    """
    four_pillars = bazi_result['four_pillars']

    # 构建回复文本
    response = f"根据您的八字排盘分析如下：\n\n"

    # 1. 基础排盘
    response += f"【四柱八字】\n"
    response += f"年柱：{four_pillars['year']['tiangan']}{four_pillars['year']['dizhi']}\n"
    response += f"月柱：{four_pillars['month']['tiangan']}{four_pillars['month']['dizhi']}\n"
    response += f"日柱：{four_pillars['day']['tiangan']}{four_pillars['day']['dizhi']}\n"
    response += f"时柱：{four_pillars['hour']['tiangan']}{four_pillars['hour']['dizhi']}\n\n"

    # 2. 五行分析
    wuxing = bazi_result['wuxing_score']
    response += f"【五行分析】\n"
    response += f"木：{wuxing['mu']}，火：{wuxing['huo']}，土：{wuxing['tu']}，金：{wuxing['jin']}，水：{wuxing['shui']}\n"

    # 简单的五行强弱判断
    scores = {'木': wuxing['mu'], '火': wuxing['huo'], '土': wuxing['tu'], '金': wuxing['jin'], '水': wuxing['shui']}
    strong = max(scores, key=scores.get)
    weak = min(scores, key=scores.get)
    response += f"五行中{strong}最旺，{weak}最弱。\n\n"

    # 3. 格局与用神
    response += f"【命局分析】\n"
    response += f"格局：{geju.get('geju_type', '未知')}。\n"
    response += f"格局描述：{geju.get('description', '')}\n"
    response += f"喜用神：{', '.join(yongshen.get('yongshen', []))}。\n"
    response += f"忌神：{', '.join(yongshen.get('jishen', []))}。\n"
    response += f"推导理由：{yongshen.get('reason', '')}\n\n"

    # 4. 大运简析
    if dayun_res:
        response += f"【大运走势】\n"
        response += f"起运年龄：{dayun_res['qiyun_age']}岁，{dayun_res['direction']}。\n"
        current_dayun = dayun_res.get('current_dayun')
        if current_dayun:
            response += f"当前大运：{current_dayun['age_range']}，"
            response += f"运势等级：{current_dayun['analysis']['level']}。\n"

    return response


def generate_sample():
    """生成单条数据"""
    # 1. 随机生成出生信息
    dt = random_date()
    gender = random.choice(["男", "女"])

    # 随机生成经纬度 (中国范围大致经度: 73-135, 纬度: 18-53)
    lon = round(random.uniform(100.0, 130.0), 2)
    lat = round(random.uniform(20.0, 45.0), 2)

    birth_info = BirthInfo(
        year=dt.year,
        month=dt.month,
        day=dt.day,
        hour=dt.hour,
        minute=dt.minute,
        gender=gender,
        longitude=lon,
        latitude=lat
    )

    # 2. 调用引擎计算
    try:
        # 基础排盘
        bazi_result = calculator.calculate(birth_info)

        # 重建对象用于后续分析
        pillars = bazi_result.four_pillars
        wuxing_score = bazi_result.wuxing_score

        # 格局
        geju_res = geju_engine.determine_geju(pillars, calculator.wuxing_calculator.get_day_master_strength(pillars))

        # 喜用神
        yongshen_res = yongshen_engine.determine_yongshen(
            pillars,
            calculator.wuxing_calculator.get_day_master_strength(pillars),
            geju_res
        )

        # 大运
        year_terms = solar_calc.get_solar_terms_in_year(birth_info.year)
        adjusted_dt, _ = calculator._get_adjusted_time(birth_info)
        current_age = datetime.now().year - birth_info.year

        dayun_res = dayun_engine.analyze_dayun(
            pillars, yongshen_res, adjusted_dt, birth_info.gender, year_terms, current_age
        )

        # 3. 构建对话数据
        user_prompt = f"请帮我分析八字。出生时间：{dt.year}年{dt.month}月{dt.day}日 {dt.hour}点{dt.minute}分，性别：{gender}，出生地经度：{lon}，纬度：{lat}。"

        assistant_response = get_expert_response(
            bazi_result.model_dump(),
            geju_res,
            yongshen_res,
            dayun_res
        )

        # 4. 格式化为 OpenAI 微调格式
        data_entry = {
            "messages": [
                {"role": "system",
                 "content": "你是一位专业的八字命理大师，精通子平术、滴天髓等经典著作。请根据提供的出生信息进行精准排盘和详细分析。"},
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": assistant_response}
            ]
        }

        return data_entry

    except Exception as e:
        print(f"生成失败: {e}")
        return None


def main():
    output_dir = Path("data/training_data")
    output_dir.mkdir(parents=True, exist_ok=True)

    data_list = []
    print(f"开始生成 {SAMPLE_SIZE} 条微调数据...")

    count = 0
    while count < SAMPLE_SIZE:
        sample = generate_sample()
        if sample:
            data_list.append(sample)
            count += 1
            if count % 100 == 0:
                print(f"已生成 {count} 条数据...")

    # 写入文件
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for item in data_list:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"✅ 数据生成完成！保存路径: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
