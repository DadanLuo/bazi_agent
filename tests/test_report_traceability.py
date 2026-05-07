from src.graph.nodes import generate_report_node
from src.graph.report_trace import build_report_trace


def sample_state():
    return {
        "bazi_result": {
            "four_pillars": {
                "year": {"tiangan": "壬", "dizhi": "午"},
                "month": {"tiangan": "庚", "dizhi": "戌"},
                "day": {"tiangan": "癸", "dizhi": "丑"},
                "hour": {"tiangan": "癸", "dizhi": "亥"},
            }
        },
        "wuxing_analysis": {"description": "日主癸水"},
        "geju_analysis": {"geju_type": "正官格", "description": "以月令取格"},
        "yongshen_analysis": {"yongshen": ["金", "水"], "reason": "身弱取印比"},
        "liunian_analysis": {"year": 2026, "fortune_level": "平"},
        "llm_response": "这是一段自然语言分析。",
        "rag_info": {
            "status": "success",
            "queries": ["[geju] 癸水 正官格"],
            "documents": [
                {
                    "content": "正官格宜清纯。",
                    "metadata": {"source": "demo.md", "topic": "格局"},
                    "distance": 0.12,
                    "route": "geju",
                    "score": 2.4,
                }
            ],
            "doc_count": 1,
        },
    }


def test_build_report_trace_separates_engine_rag_and_llm_sources():
    trace = build_report_trace(sample_state())

    assert trace["engine"]["fields"] == [
        "bazi_result",
        "wuxing_analysis",
        "geju_analysis",
        "yongshen_analysis",
        "liunian_analysis",
    ]
    assert trace["rag"]["status"] == "success"
    assert trace["rag"]["documents"][0]["source"] == "demo.md"
    assert trace["rag"]["documents"][0]["route"] == "geju"
    assert trace["llm"]["used"] is True
    assert trace["llm"]["field"] == "llm_response"


def test_generate_report_node_attaches_traceability():
    result = generate_report_node(sample_state())

    report = result["final_report"]
    assert "traceability" in report
    assert report["traceability"]["llm"]["used"] is True
    assert report["traceability"]["rag"]["doc_count"] == 1


def test_traceability_preserves_rag_scores_and_preview():
    trace = build_report_trace(sample_state())
    doc = trace["rag"]["documents"][0]

    assert doc["id"] == "rag-1"
    assert doc["score"] == 2.4
    assert doc["distance"] == 0.12
    assert doc["content_preview"] == "正官格宜清纯。"
