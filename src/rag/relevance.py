"""
RAG relevance helpers.

These helpers keep the retrieval node focused on orchestration while
encapsulating query planning, lexical filtering and reranking logic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Sequence, Set


ROUTE_TOPIC_ALIASES = {
    "命局": {"命局", "八字", "命造", "原局", "本命"},
    "格局": {"格局", "成格", "破格"},
    "用神": {"用神", "喜神", "忌神", "扶抑", "调候"},
}

GENERIC_SUB_TOPICS = {
    "命局": {"命局", "八字", "日主", "日元", "日干", "命主", "本命", "原局"},
    "格局": {"格局", "成格", "破格"},
    "用神": {"用神", "喜神", "忌神", "扶抑", "调候"},
    "五行": {"五行", "旺衰", "生克", "强弱"},
    "十神": {"十神"},
    "流年": {"流年", "大运", "岁运"},
}

LOW_SIGNAL_CHUNK_MARKERS = ("case", "example", "案例", "示例")


@dataclass(frozen=True)
class RagQueryPlan:
    route: str
    query: str
    tokens: List[str]
    weight: float = 1.0
    expected_topic: str = ""
    preferred_sub_topic: str = ""
    required_terms: List[str] = field(default_factory=list)
    strong_terms: List[str] = field(default_factory=list)


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _unique_terms(values: Iterable[str]) -> List[str]:
    return list(dict.fromkeys([str(value).strip() for value in values if str(value).strip()]))


def build_bazi_query_plans(
    bazi_result: Dict[str, Any],
    geju_analysis: Dict[str, Any],
    yongshen_analysis: Dict[str, Any],
) -> List[RagQueryPlan]:
    plans: List[RagQueryPlan] = []

    day_master = _enum_value(
        bazi_result.get("four_pillars", {}).get("day", {}).get("tiangan", "")
    )
    month_zhi = _enum_value(
        bazi_result.get("four_pillars", {}).get("month", {}).get("dizhi", "")
    )
    if day_master and month_zhi:
        plans.append(
            RagQueryPlan(
                route="命局",
                query=f"{day_master}日主生于{month_zhi}月 月令旺衰 调候取用",
                tokens=_unique_terms([day_master, month_zhi, "日主", "月令", "旺衰", "调候"]),
                weight=1.05,
                expected_topic="命局",
                required_terms=[day_master, month_zhi],
                strong_terms=[f"{day_master}日主", f"生于{month_zhi}月", "月令", "调候"],
            )
        )

    geju_type = str(geju_analysis.get("geju_type", "") or "").strip()
    if geju_type and geju_type != "常格":
        plans.append(
            RagQueryPlan(
                route="格局",
                query=f"{geju_type} 成格条件 喜忌 用神取法",
                tokens=_unique_terms([geju_type, "成格", "喜忌", "用神"]),
                weight=1.2,
                expected_topic="格局",
                preferred_sub_topic=geju_type,
                required_terms=[geju_type],
                strong_terms=[geju_type, "成格", "喜忌"],
            )
        )

    yongshen = _unique_terms(yongshen_analysis.get("yongshen", []) or [])
    if yongshen:
        joined = "、".join(yongshen)
        plans.append(
            RagQueryPlan(
                route="用神",
                query=f"{joined}为用神时的取用原则 喜神 忌神 调候 扶抑",
                tokens=_unique_terms(yongshen + ["用神", "喜神", "忌神", "调候", "扶抑"]),
                weight=1.1,
                expected_topic="用神",
                required_terms=yongshen,
                strong_terms=yongshen + ["用神", "喜神", "调候", "扶抑"],
            )
        )

    return plans


def relax_where_condition(
    where_condition: Dict[str, Any],
    *,
    drop_topic: bool,
    drop_sub_topic: bool,
    drop_keywords: bool,
) -> Dict[str, Any]:
    if not where_condition:
        return {}

    if "$and" not in where_condition:
        if drop_topic and "topic" in where_condition:
            return {}
        if drop_sub_topic and "sub_topic" in where_condition:
            return {}
        return where_condition

    relaxed_predicates = []
    for predicate in where_condition.get("$and", []):
        if not isinstance(predicate, dict):
            continue
        if drop_topic and "topic" in predicate:
            continue
        if drop_sub_topic and "sub_topic" in predicate:
            continue
        if drop_keywords and "$or" in predicate:
            keyword_or = predicate.get("$or", [])
            if keyword_or and all(
                isinstance(item, dict) and "keywords" in item for item in keyword_or
            ):
                continue
        relaxed_predicates.append(predicate)

    if not relaxed_predicates:
        return {}
    if len(relaxed_predicates) == 1:
        return relaxed_predicates[0]
    return {"$and": relaxed_predicates}


def normalize_source_name(source: Any) -> str:
    return str(source or "").strip().lower()


def should_keep_sub_topic(topic: str, sub_topic: str) -> bool:
    topic = str(topic or "").strip()
    sub_topic = str(sub_topic or "").strip()
    if not sub_topic or sub_topic == "general" or sub_topic == topic:
        return False
    if sub_topic in GENERIC_SUB_TOPICS.get(topic, set()):
        return False
    return True


def _collect_metadata_values(metadata: Dict[str, Any]) -> List[str]:
    values: List[str] = []
    for value in metadata.values():
        if isinstance(value, list):
            values.extend(str(item) for item in value if item is not None)
        elif value is not None:
            values.append(str(value))
    return values


def build_doc_haystack(doc: Dict[str, Any]) -> str:
    metadata = doc.get("metadata", {}) or {}
    metadata_values = _collect_metadata_values(metadata)
    content = str(doc.get("content", "") or "")
    return " ".join(metadata_values) + " " + content[:480]


def count_term_hits(haystack: str, terms: Sequence[str]) -> int:
    return sum(1 for term in _unique_terms(terms) if term and term in haystack)


def looks_like_timeline_or_table(text: str) -> bool:
    compact = re.sub(r"\s+", " ", str(text or ""))
    if not compact:
        return False

    digit_count = sum(char.isdigit() for char in compact)
    digit_ratio = digit_count / max(len(compact), 1)
    year_hits = len(re.findall(r"(?:18|19|20)\d{2}", compact))
    number_hits = len(re.findall(r"\d{2,4}", compact))

    if year_hits >= 4:
        return True
    if digit_ratio > 0.14 and number_hits >= 8:
        return True
    if re.search(r"(?:\d{2,4}\s+){7,}", compact):
        return True
    return False


def is_high_signal_doc(
    doc: Dict[str, Any],
    plan: RagQueryPlan,
    excluded_sources: Set[str] | None = None,
) -> bool:
    metadata = doc.get("metadata", {}) or {}
    source = normalize_source_name(metadata.get("source"))
    if excluded_sources and source in excluded_sources:
        return False

    content = str(doc.get("content", "") or "")
    if not content.strip() or looks_like_timeline_or_table(content):
        return False

    chunk_type = str(metadata.get("chunk_type", "") or "").lower()
    if any(marker in chunk_type for marker in LOW_SIGNAL_CHUNK_MARKERS):
        return False

    haystack = build_doc_haystack(doc)
    topic = str(metadata.get("topic", "") or "").strip()
    sub_topic = str(metadata.get("sub_topic", "") or "").strip()
    topic_aliases = ROUTE_TOPIC_ALIASES.get(plan.route, {plan.expected_topic}) | {
        plan.expected_topic
    }
    topic_match = topic in topic_aliases or sub_topic in topic_aliases
    token_hits = count_term_hits(haystack, plan.tokens)
    required_hits = count_term_hits(haystack, plan.required_terms)
    strong_hits = count_term_hits(haystack, plan.strong_terms)

    if plan.route == "格局" and required_hits == 0:
        return False

    if plan.route == "用神":
        has_route_terms = count_term_hits(haystack, ["用神", "喜神", "忌神", "调候", "扶抑"])
        if has_route_terms == 0 and topic != "用神":
            return False

    if not topic_match and token_hits == 0 and strong_hits == 0:
        return False

    return True


def score_rag_doc(doc: Dict[str, Any], plan: RagQueryPlan) -> float:
    metadata = doc.get("metadata", {}) or {}
    content = str(doc.get("content", "") or "")
    haystack = build_doc_haystack(doc)

    distance = float(doc.get("distance", 1.0) or 1.0)
    similarity_score = max(0.0, 1.28 - distance)
    token_hits = count_term_hits(haystack, plan.tokens)
    required_hits = count_term_hits(haystack, plan.required_terms)
    strong_hits = count_term_hits(haystack, plan.strong_terms)

    topic = str(metadata.get("topic", "") or "").strip()
    sub_topic = str(metadata.get("sub_topic", "") or "").strip()
    topic_aliases = ROUTE_TOPIC_ALIASES.get(plan.route, {plan.expected_topic}) | {
        plan.expected_topic
    }

    score = similarity_score
    score += float(plan.weight) * 0.22
    score += min(token_hits, 4) * 0.16
    score += min(required_hits, 2) * 0.16
    score += min(strong_hits, 3) * 0.18

    if topic in topic_aliases or sub_topic in topic_aliases:
        score += 0.32
    elif topic not in ("", "general"):
        score -= 0.4

    if plan.preferred_sub_topic:
        if sub_topic == plan.preferred_sub_topic:
            score += 0.42
        elif plan.preferred_sub_topic in haystack:
            score += 0.24
        elif should_keep_sub_topic(topic, sub_topic):
            score -= 0.12

    importance = float(metadata.get("importance", 0.0) or 0.0)
    score += min(max(importance, 0.0), 2.5) * 0.08

    chunk_type = str(metadata.get("chunk_type", "") or "").lower()
    if any(marker in chunk_type for marker in LOW_SIGNAL_CHUNK_MARKERS):
        score -= 0.55

    if looks_like_timeline_or_table(content):
        score -= 0.8

    if len(re.findall(r"例[\d一二三四五六七八九十]", content)) >= 1 and strong_hits == 0:
        score -= 0.28

    if len(content) > 650:
        score -= 0.12

    return score


def select_rag_documents(
    docs: Sequence[Dict[str, Any]],
    *,
    max_docs: int = 4,
    min_score: float = 1.0,
    fallback_score: float = 0.72,
) -> List[Dict[str, Any]]:
    unique_docs: Dict[str, Dict[str, Any]] = {}
    for doc in docs:
        content = str(doc.get("content", "") or "")
        if not content:
            continue
        metadata = doc.get("metadata", {}) or {}
        chunk_type = str(metadata.get("chunk_type", "") or "").lower()
        if any(marker in chunk_type for marker in LOW_SIGNAL_CHUNK_MARKERS):
            continue
        if looks_like_timeline_or_table(content):
            continue
        if len(re.findall(r"例[\d一二三四五六七八九十]", content)) >= 1 and float(doc.get("_score", 0.0)) < 1.35:
            continue
        existing = unique_docs.get(content)
        if existing is None or float(doc.get("_score", 0.0)) > float(existing.get("_score", 0.0)):
            unique_docs[content] = doc

    ranked_docs = sorted(
        unique_docs.values(),
        key=lambda item: float(item.get("_score", 0.0)),
        reverse=True,
    )

    selected = [doc for doc in ranked_docs if float(doc.get("_score", 0.0)) >= min_score][:max_docs]
    if selected:
        return selected

    return [doc for doc in ranked_docs if float(doc.get("_score", 0.0)) >= fallback_score][: min(max_docs, 2)]
