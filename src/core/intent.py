# src/core/intent.py
"""
无状态意图检测 — 纯函数，无实例变量，线程安全
"""
from typing import Dict, Any, List, Optional


def detect_intent(
    query: str,
    keywords: Dict[str, List[str]],
    has_prior_analysis: bool = False,
    re_analyze_keywords: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    通用意图检测 — 基于关键词评分

    Args:
        query: 用户输入
        keywords: 意图 → 关键词列表映射（由 agent 提供）
        has_prior_analysis: 是否已有分析结果（影响降级逻辑）
        re_analyze_keywords: 触发重新分析的关键词（如 ["重新", "换一个"]）

    Returns:
        {"intent": str, "confidence": float, "all_scores": dict, "has_prior": bool}
    """
    if re_analyze_keywords is None:
        re_analyze_keywords = ["重新", "换一个", "另一个人", "帮别人"]

    query_lower = query.lower()

    # 处理 [八字信息] 前缀（兼容旧前端）
    real_query = query_lower
    has_bazi_context = False
    if "[八字信息]" in query_lower:
        has_bazi_context = True
        for sep in ["用户问题:", "用户问题："]:
            if sep in query_lower:
                real_query = query_lower.split(sep)[-1].strip()
                break

    has_prior = has_prior_analysis or has_bazi_context

    # 关键词评分
    intent_scores: Dict[str, int] = {}
    for intent_type, kw_list in keywords.items():
        score = sum(1 for kw in kw_list if kw in real_query)
        intent_scores[intent_type] = score

    max_score = max(intent_scores.values()) if intent_scores else 0
    if max_score > 0:
        detected = max(intent_scores, key=intent_scores.get)
    else:
        detected = "GENERAL_QUERY"

    # 已有分析结果时：除非明确要求重新分析，否则降级为 FOLLOW_UP
    if has_prior and detected != "FOLLOW_UP":
        if not any(kw in real_query for kw in re_analyze_keywords):
            detected = "FOLLOW_UP"

    # 计算置信度
    kw_count = len(keywords.get(detected, [])) or 1
    confidence = min(max_score / kw_count, 1.0)

    return {
        "intent": detected,
        "confidence": confidence,
        "all_scores": intent_scores,
        "has_prior": has_prior,
    }
