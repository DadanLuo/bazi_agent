from src.rag.agentic.react_orchestrator import ReactRAGOrchestrator
from src.rag.agentic.state import Document
from src.rag.agentic.tools import (
    BM25ChromaAdapter,
    AgenticRAGToolset,
    RetrievalContext,
    build_retrieval_context,
    expand_query,
    evaluate_retrieval,
    rerank_documents,
)
from src.rag.retrievers.bm25_retriever import BM25Retriever


def _sample_graph_state():
    return {
        "user_query": "怎么办？",
        "bazi_result": {
            "four_pillars": {
                "day": {"tiangan": "甲"},
                "month": {"dizhi": "申"},
            }
        },
        "wuxing_analysis": {"strength": "身弱"},
        "geju_analysis": {"geju_type": "七杀格"},
        "yongshen_analysis": {"yongshen": ["用印"]},
    }


def test_build_retrieval_context_uses_langgraph_state_for_short_followup():
    context = build_retrieval_context("怎么办？", _sample_graph_state())

    assert context.day_master == "甲木"
    assert context.month_branch == "申月"
    assert context.wangshuai == "身弱"
    assert context.geju == "七杀格"
    assert "甲木" in context.required_terms
    assert "申月" in context.required_terms
    assert "杀旺身弱" in context.boost_terms
    assert "用印" in context.boost_terms


def test_expand_query_generates_multiple_domain_angles():
    context = build_retrieval_context("甲木生申月，杀旺身弱怎么办？", _sample_graph_state())

    queries = expand_query(context)
    angles = {query.angle for query in queries}

    assert {"命局", "格局", "用神"}.issubset(angles)
    assert all(query.target_topic for query in queries)
    assert any("杀印相生" in query.boost_terms for query in queries)


def test_bm25_tokenizer_preserves_domain_terms():
    retriever = BM25Retriever()

    tokens = retriever._tokenize("甲木生申月，杀旺身弱，食神制杀。")

    assert "甲木" in tokens
    assert "申月" in tokens
    assert "杀旺身弱" in tokens
    assert "食神制杀" in tokens


class FakeCollection:
    name = "fake_collection"

    def count(self):
        return 2

    def get(self, include=None, limit=None, offset=None):
        return {
            "documents": [
                "甲木生于申月，杀旺身弱，宜用印化杀。",
                "甲木为阳木，泛论其性情。",
            ],
            "metadatas": [
                {"source": "rule", "topic": "用神"},
                {"source": "general", "topic": "命局"},
            ],
        }


def test_bm25_adapter_builds_index_from_chroma_collection():
    adapter = BM25ChromaAdapter(FakeCollection())

    docs = adapter.search("甲木申月杀旺身弱用印", top_k=2, threshold=0.0)

    assert docs
    assert docs[0].source_type == "bm25"
    assert "用印" in docs[0].content


def test_rerank_prefers_required_and_boost_term_matches():
    context = RetrievalContext(
        original_query="甲木申月杀旺身弱怎么办",
        day_master="甲木",
        month_branch="申月",
        wangshuai="身弱",
        geju="七杀格",
        yongshen=["用印"],
        domain_terms=["甲木", "申月", "杀旺身弱"],
        required_terms=["甲木", "申月"],
        boost_terms=["杀旺身弱", "用印", "杀印相生", "食神制杀"],
    )
    docs = [
        Document(content="甲木为阳木，泛论其性情。", score=0.9, source_type="vector"),
        Document(content="甲木生于申月，杀旺身弱，宜用印化杀。", score=0.6, source_type="bm25"),
    ]

    ranked = rerank_documents(docs, context)

    assert ranked[0].content.startswith("甲木生于申月")


def test_evaluate_retrieval_reports_missing_required_terms():
    context = RetrievalContext(
        original_query="甲木申月杀旺身弱怎么办",
        required_terms=["甲木", "申月"],
        boost_terms=["用印"],
    )

    result = evaluate_retrieval(
        [Document(content="甲木为阳木。", score=0.5)],
        context,
    )

    assert result["need_more"] is True
    assert "申月" in result["coverage"]["missing_required_terms"]


def test_react_orchestrator_falls_back_without_llm_and_limits_rounds():
    class FakeToolset(AgenticRAGToolset):
        def __init__(self):
            super().__init__(knowledge_retriever=None)

        def vector_search(self, retrieval_query, top_k=5):
            return [
                Document(
                    content="甲木生于申月，杀旺身弱，宜用印。",
                    score=0.7,
                    source_type="vector",
                )
            ]

        def bm25_search(self, retrieval_query, top_k=5):
            return []

    orchestrator = ReactRAGOrchestrator(llm=None, toolset=FakeToolset(), max_rounds=3)

    result = orchestrator.run("甲木生申月怎么办？", graph_state=_sample_graph_state())

    assert result["retrieved_docs"]
    assert result["final_context"]
    assert result["tool_rounds"] <= 3
