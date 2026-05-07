from src.graph.nodes import safety_check_node
from src.safety.disclaimer import build_safety_policy
from src.safety.scene_strategy import SceneType


def test_build_bazi_safety_policy_contains_high_risk_boundaries():
    policy = build_safety_policy(SceneType.BAZI)

    assert policy["scene"] == "bazi"
    assert policy["positioning"] == "文化娱乐与自我反思参考"
    assert "医疗诊断" in policy["not_for"]
    assert "投资决策" in policy["not_for"]
    assert "确定性生死判断" in policy["not_for"]


def test_safety_check_attaches_policy_to_safe_bazi_output():
    state = {
        "user_input": {"year": 2002, "month": 10, "day": 12, "hour": 21, "gender": "男"},
        "final_report": {"message": "分析完成", "llm_analysis": "命理只是趋势参考。"},
        "llm_response": "命理只是趋势参考。",
    }

    result = safety_check_node(state)
    safe_output = result["safe_output"]

    assert safe_output["blocked"] is False
    assert safe_output["data"]["safety_policy"]["scene"] == "bazi"
    assert (
        "不构成医疗、法律、投资或人生重大决策建议"
        in safe_output["data"]["safety_policy"]["disclaimer"]
    )
