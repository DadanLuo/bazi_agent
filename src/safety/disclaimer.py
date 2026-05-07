from __future__ import annotations

from src.safety.scene_strategy import SceneType


NOT_FOR = [
    "医疗诊断",
    "心理危机干预",
    "投资决策",
    "法律判断",
    "确定性生死判断",
    "替代个人重大决定",
]


def build_safety_policy(scene: SceneType) -> dict[str, object]:
    scene_name = scene.value if isinstance(scene, SceneType) else str(scene)
    if scene == SceneType.TAROT:
        positioning = "心理投射与自我反思参考"
    else:
        positioning = "文化娱乐与自我反思参考"

    return {
        "scene": scene_name,
        "positioning": positioning,
        "not_for": list(NOT_FOR),
        "disclaimer": "本结果仅供文化娱乐与自我反思参考，不构成医疗、法律、投资或人生重大决策建议。",
    }
