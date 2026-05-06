from src.rag.relevance import (
    RagQueryPlan,
    build_bazi_query_plans,
    is_high_signal_doc,
    score_rag_doc,
    select_rag_documents,
)
from src.rag.retriever import KnowledgeRetriever


def test_build_bazi_query_plans_use_route_specific_queries():
    plans = build_bazi_query_plans(
        bazi_result={
            "four_pillars": {
                "day": {"tiangan": "己"},
                "month": {"dizhi": "巳"},
            }
        },
        geju_analysis={"geju_type": "正印格"},
        yongshen_analysis={"yongshen": ["土"]},
    )

    plan_map = {plan.route: plan for plan in plans}

    assert "月令旺衰" in plan_map["命局"].query
    assert "成格条件" in plan_map["格局"].query
    assert "用神" in plan_map["用神"].query
    assert "调候" in plan_map["用神"].query


def test_build_where_from_query_skips_generic_sub_topic():
    retriever = KnowledgeRetriever.__new__(KnowledgeRetriever)
    where = retriever.build_where_from_query("己日主生于巳月 月令旺衰 调候取用")

    predicates = where.get("$and", [where])
    sub_topics = [item.get("sub_topic") for item in predicates if isinstance(item, dict) and "sub_topic" in item]

    assert "日主" not in sub_topics


def test_is_high_signal_doc_filters_timeline_dump():
    plan = RagQueryPlan(
        route="命局",
        query="己日主生于巳月 月令旺衰 调候取用",
        tokens=["己", "巳", "日主", "月令", "调候"],
        expected_topic="命局",
        required_terms=["己", "巳"],
        strong_terms=["日主", "月令", "调候"],
    )

    good_doc = {
        "content": "己土日主生于巳月，月令火旺，论命先看调候，再看扶抑与通关。",
        "metadata": {"topic": "命局", "sub_topic": "命局", "chunk_type": "命局_chunk", "source": "测试古籍"},
        "distance": 0.42,
    }
    noisy_doc = {
        "content": "1947 丁亥 1967 丁未 1987丁卯 1948戊子 1968戊申 1988戊辰 1949己丑 1969己酉 1989己巳",
        "metadata": {"topic": "命局", "sub_topic": "八字", "chunk_type": "命局_chunk", "source": "测试古籍"},
        "distance": 0.31,
    }

    assert is_high_signal_doc(good_doc, plan, excluded_sources={"treelist"}) is True
    assert is_high_signal_doc(noisy_doc, plan, excluded_sources={"treelist"}) is False


def test_select_rag_documents_prefers_route_matching_theory():
    plan = RagQueryPlan(
        route="格局",
        query="正印格 成格条件 喜忌 用神取法",
        tokens=["正印格", "成格", "喜忌", "用神"],
        weight=1.2,
        expected_topic="格局",
        preferred_sub_topic="正印格",
        required_terms=["正印格"],
        strong_terms=["正印格", "成格", "喜忌"],
    )

    high_signal = {
        "content": "正印格成格以月令得印为先，再看身强身弱与喜忌配置，不可只看单一十神。",
        "metadata": {"topic": "格局", "sub_topic": "正印格", "chunk_type": "格局_chunk", "source": "测试古籍"},
        "distance": 0.48,
    }
    generic_case = {
        "content": "例1：甲子 丙寅 己巳 庚午，以上命例仅作说明。",
        "metadata": {"topic": "格局", "sub_topic": "成格", "chunk_type": "case", "source": "测试古籍"},
        "distance": 0.35,
    }
    off_topic = {
        "content": "金木水火土就是五行，动态五行讲的是循环运行。",
        "metadata": {"topic": "五行", "sub_topic": "五行", "chunk_type": "五行_chunk", "source": "测试古籍"},
        "distance": 0.33,
    }

    candidates = []
    for doc in (high_signal, generic_case, off_topic):
        doc = dict(doc)
        doc["_score"] = score_rag_doc(doc, plan)
        candidates.append(doc)

    selected = select_rag_documents(candidates, max_docs=3, min_score=1.0, fallback_score=0.72)

    assert selected
    assert selected[0]["content"] == high_signal["content"]
    assert generic_case["content"] not in [doc["content"] for doc in selected]
