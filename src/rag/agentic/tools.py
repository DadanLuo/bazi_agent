"""Runtime tools for Agentic RAG retrieval orchestration."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from src.rag.agentic.state import Document
from src.rag.domain_lexicon import get_domain_lexicon
from src.rag.retrievers.bm25_retriever import BM25Retriever

logger = logging.getLogger(__name__)


def _unique(values: Iterable[str]) -> List[str]:
    return list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip()


def _as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [_enum_value(item) for item in value if _enum_value(item)]
    if isinstance(value, tuple) or isinstance(value, set):
        return [_enum_value(item) for item in value if _enum_value(item)]
    return [_enum_value(value)] if _enum_value(value) else []


def _stem_to_element(stem: str) -> str:
    return {
        "甲": "木",
        "乙": "木",
        "丙": "火",
        "丁": "火",
        "戊": "土",
        "己": "土",
        "庚": "金",
        "辛": "金",
        "壬": "水",
        "癸": "水",
    }.get(stem, "")


@dataclass
class RetrievalContext:
    original_query: str
    day_master: str = ""
    month_branch: str = ""
    wangshuai: str = ""
    geju: str = ""
    yongshen: List[str] = field(default_factory=list)
    jishen: List[str] = field(default_factory=list)
    ten_gods: List[str] = field(default_factory=list)
    domain_terms: List[str] = field(default_factory=list)
    required_terms: List[str] = field(default_factory=list)
    boost_terms: List[str] = field(default_factory=list)
    avoid_terms: List[str] = field(default_factory=list)
    current_target: str = ""


@dataclass
class RetrievalQuery:
    angle: str
    query: str
    required_terms: List[str] = field(default_factory=list)
    boost_terms: List[str] = field(default_factory=list)
    target_topic: str = ""


def _extract_four_pillars(bazi_result: Dict[str, Any]) -> Tuple[str, str]:
    pillars = (bazi_result or {}).get("four_pillars", {})
    if isinstance(pillars, dict):
        day = pillars.get("day", {}) or {}
        month = pillars.get("month", {}) or {}
        day_master = _enum_value(day.get("tiangan"))
        month_branch = _enum_value(month.get("dizhi"))
        return day_master, month_branch

    if isinstance(pillars, list):
        day = pillars[2] if len(pillars) > 2 else {}
        month = pillars[1] if len(pillars) > 1 else {}
        return _enum_value(day.get("tiangan")), _enum_value(month.get("dizhi"))

    return "", ""


def _normalize_day_master(value: str) -> str:
    value = _enum_value(value)
    if len(value) == 1:
        element = _stem_to_element(value)
        return f"{value}{element}" if element else value
    return value


def _normalize_month_branch(value: str) -> str:
    value = _enum_value(value)
    if len(value) == 1 and value in "子丑寅卯辰巳午未申酉戌亥":
        return f"{value}月"
    return value


def _extract_wangshuai(wuxing_analysis: Dict[str, Any]) -> str:
    if not isinstance(wuxing_analysis, dict):
        return ""
    for key in ("strength", "day_master_strength", "riyuan_strength", "身强身弱", "旺衰"):
        value = _enum_value(wuxing_analysis.get(key))
        if value:
            return value
    serialized = str(wuxing_analysis)
    if "身弱" in serialized:
        return "身弱"
    if "身强" in serialized or "身旺" in serialized:
        return "身强"
    return ""


def build_retrieval_context(
    query: str,
    graph_state: Optional[Dict[str, Any]] = None,
) -> RetrievalContext:
    """Build runtime metadata from query plus the full LangGraph state."""
    graph_state = graph_state or {}
    lexicon = get_domain_lexicon()
    original_query = str(query or graph_state.get("user_query") or "")

    day_stem, month_zhi = _extract_four_pillars(graph_state.get("bazi_result") or {})
    day_master = _normalize_day_master(day_stem)
    month_branch = _normalize_month_branch(month_zhi)
    wangshuai = _extract_wangshuai(graph_state.get("wuxing_analysis") or {})

    geju_analysis = graph_state.get("geju_analysis") or {}
    geju = _enum_value(geju_analysis.get("geju_type") or geju_analysis.get("geju") or geju_analysis.get("pattern"))
    yongshen_analysis = graph_state.get("yongshen_analysis") or {}
    yongshen = _as_list(
        yongshen_analysis.get("yongshen")
        or yongshen_analysis.get("用神")
        or yongshen_analysis.get("xiyong")
    )
    jishen = _as_list(yongshen_analysis.get("jishen") or yongshen_analysis.get("忌神"))
    ten_gods = _as_list(geju_analysis.get("ten_gods") or geju_analysis.get("shishen"))

    base_terms = lexicon.canonical_terms(original_query)
    state_terms = lexicon.canonical_terms(
        " ".join([day_master, month_branch, wangshuai, geju, " ".join(yongshen), " ".join(jishen)])
    )

    required_terms = _unique([day_master, month_branch] + base_terms[:2])
    boost_terms = _unique(base_terms + state_terms + yongshen + ten_gods)

    if geju:
        boost_terms.extend(lexicon.expand_terms([geju]))
    if "身弱" in wangshuai and any(term in boost_terms for term in ("七杀格", "七杀", "杀旺身弱")):
        boost_terms.extend(["杀旺身弱", "用印", "杀印相生", "食神制杀"])
    if day_master and month_branch and "身弱" in wangshuai:
        boost_terms.append("扶抑")

    domain_terms = _unique(base_terms + state_terms + boost_terms)
    return RetrievalContext(
        original_query=original_query,
        day_master=day_master,
        month_branch=month_branch,
        wangshuai=wangshuai,
        geju=geju,
        yongshen=yongshen,
        jishen=jishen,
        ten_gods=ten_gods,
        domain_terms=domain_terms,
        required_terms=required_terms,
        boost_terms=_unique(boost_terms),
        avoid_terms=jishen,
    )


def expand_query(context: RetrievalContext, max_queries: int = 5) -> List[RetrievalQuery]:
    """Generate multi-angle retrieval queries from runtime context."""
    lexicon = get_domain_lexicon()
    query = context.original_query
    common_required = _unique(context.required_terms)
    common_boost = _unique(context.boost_terms + lexicon.expand_terms(context.domain_terms))

    candidates = [
        RetrievalQuery(
            angle="命局",
            query=" ".join(_unique([query, context.day_master, context.month_branch, context.wangshuai, "日主", "月令", "旺衰", "调候"])),
            required_terms=common_required,
            boost_terms=_unique(common_boost + ["日主", "月令", "调候"]),
            target_topic="命局",
        ),
        RetrievalQuery(
            angle="格局",
            query=" ".join(_unique([query, context.geju, "成格", "破格", "喜忌", "格局"])),
            required_terms=_unique([context.geju] if context.geju else common_required),
            boost_terms=_unique(common_boost + ["成格", "破格", "喜忌"]),
            target_topic="格局",
        ),
        RetrievalQuery(
            angle="用神",
            query=" ".join(_unique([query, " ".join(context.yongshen), "用神", "喜神", "忌神", "扶抑", "通关", "杀印相生", "食神制杀"])),
            required_terms=common_required,
            boost_terms=_unique(common_boost + ["用神", "用印", "扶抑", "通关", "杀印相生", "食神制杀"]),
            target_topic="用神",
        ),
        RetrievalQuery(
            angle="十神制化",
            query=" ".join(_unique([query, "七杀", "伤官", "正印", "偏印", "食神制杀", "杀印相生", "制化"])),
            required_terms=common_required,
            boost_terms=_unique(common_boost + ["七杀", "伤官", "正印", "偏印", "食神制杀", "杀印相生"]),
            target_topic="十神",
        ),
    ]

    deduped: List[RetrievalQuery] = []
    seen = set()
    for item in candidates:
        if not item.query.strip() or item.angle in seen:
            continue
        seen.add(item.angle)
        deduped.append(item)
        if len(deduped) >= max_queries:
            break
    return deduped


def _metadata_text(metadata: Dict[str, Any]) -> str:
    values: List[str] = []
    for value in (metadata or {}).values():
        if isinstance(value, list):
            values.extend(str(item) for item in value)
        elif value is not None:
            values.append(str(value))
    return " ".join(values)


class BM25ChromaAdapter:
    """Read-only sidecar BM25 index built from the active Chroma collection."""

    _cache: Dict[str, BM25Retriever] = {}

    def __init__(self, collection: Any):
        self.collection = collection

    def _cache_key(self) -> str:
        name = getattr(self.collection, "name", "") or getattr(self.collection, "_name", "collection")
        try:
            count = self.collection.count()
        except Exception:
            count = 0
        return f"{name}:{count}"

    def _load_documents(self) -> List[Document]:
        try:
            total = int(self.collection.count())
        except Exception:
            total = 0
        if total <= 0:
            return []

        batch_size = 1000
        docs: List[Document] = []
        for offset in range(0, total, batch_size):
            result = self.collection.get(
                include=["documents", "metadatas"],
                limit=batch_size,
                offset=offset,
            )
            documents = result.get("documents", []) or []
            metadatas = result.get("metadatas", []) or []
            for idx, content in enumerate(documents):
                metadata = metadatas[idx] if idx < len(metadatas) and metadatas[idx] else {}
                docs.append(Document(content=content or "", metadata=metadata, source_type="bm25"))
        return docs

    def _get_retriever(self) -> BM25Retriever:
        key = self._cache_key()
        retriever = self._cache.get(key)
        if retriever is None:
            retriever = BM25Retriever(self._load_documents())
            self._cache[key] = retriever
        return retriever

    def search(
        self,
        query: str,
        top_k: int = 5,
        threshold: float = 0.0,
        filter: Optional[Dict[str, Any]] = None,
    ) -> List[Document]:
        return self._get_retriever().search(query, top_k=top_k, threshold=threshold, filter=filter)


def rerank_documents(
    documents: Sequence[Document],
    context: RetrievalContext,
    query: Optional[RetrievalQuery] = None,
    max_docs: int = 8,
) -> List[Document]:
    lexicon = get_domain_lexicon()
    required_terms = _unique((query.required_terms if query else []) + context.required_terms)
    boost_terms = _unique((query.boost_terms if query else []) + context.boost_terms)
    target_topic = (query.target_topic if query else "") or context.current_target

    best_by_key: Dict[str, Document] = {}
    for doc in documents:
        if not doc.content.strip():
            continue
        key = doc.content[:180]
        haystack = f"{_metadata_text(doc.metadata)} {doc.content}"
        score = float(doc.score or 0.0)
        score += lexicon.lexical_score(haystack, required_terms) * 1.8
        score += lexicon.lexical_score(haystack, boost_terms) * 0.9
        if target_topic and target_topic in haystack:
            score += 0.35
        if doc.source_type == "bm25":
            score += 0.18
        if _looks_like_timeline_or_table(doc.content):
            score -= 0.75
        if re.search(r"例[\d一二三四五六七八九十]", doc.content) and lexicon.lexical_score(haystack, boost_terms) < 0.3:
            score -= 0.35

        ranked = Document(
            content=doc.content,
            metadata={**(doc.metadata or {}), "runtime_rerank_score": score},
            score=score,
            source_type=doc.source_type,
        )
        existing = best_by_key.get(key)
        if existing is None or ranked.score > existing.score:
            best_by_key[key] = ranked

    return sorted(best_by_key.values(), key=lambda item: item.score, reverse=True)[:max_docs]


def _looks_like_timeline_or_table(text: str) -> bool:
    compact = re.sub(r"\s+", " ", str(text or ""))
    if not compact:
        return False
    digit_count = sum(char.isdigit() for char in compact)
    if digit_count / max(len(compact), 1) > 0.14 and len(re.findall(r"\d{2,4}", compact)) >= 8:
        return True
    return len(re.findall(r"(?:18|19|20)\d{2}", compact)) >= 4


def evaluate_retrieval(
    documents: Sequence[Document],
    context: RetrievalContext,
    query: Optional[RetrievalQuery] = None,
) -> Dict[str, Any]:
    haystack = " ".join([doc.content + " " + _metadata_text(doc.metadata) for doc in documents])
    required_terms = _unique((query.required_terms if query else []) + context.required_terms)
    boost_terms = _unique((query.boost_terms if query else []) + context.boost_terms)
    missing_required = [term for term in required_terms if term and term not in haystack]
    covered_boost = [term for term in boost_terms if term and term in haystack]
    required_coverage = 1.0 if not required_terms else (len(required_terms) - len(missing_required)) / len(required_terms)
    boost_coverage = 0.0 if not boost_terms else len(covered_boost) / len(boost_terms)
    need_more = not documents or required_coverage < 0.75 or (boost_terms and boost_coverage < 0.12)

    return {
        "coverage": {
            "required_coverage": required_coverage,
            "boost_coverage": boost_coverage,
            "missing_required_terms": missing_required,
            "covered_boost_terms": covered_boost,
        },
        "need_more": need_more,
        "suggested_angles": [] if not need_more else ["用神", "格局", "十神制化"],
    }


class AgenticRAGToolset:
    """Callable runtime tools used by deterministic and LLM-guided orchestration."""

    def __init__(self, knowledge_retriever: Any = None):
        self.knowledge_retriever = knowledge_retriever
        self._bm25_adapter: Optional[BM25ChromaAdapter] = None

    def build_retrieval_context(self, query: str, graph_state: Optional[Dict[str, Any]] = None) -> RetrievalContext:
        return build_retrieval_context(query, graph_state)

    def expand_query(self, context: RetrievalContext) -> List[RetrievalQuery]:
        return expand_query(context)

    def vector_search(self, retrieval_query: RetrievalQuery, top_k: int = 5) -> List[Document]:
        if not self.knowledge_retriever:
            return []
        try:
            where = self.knowledge_retriever.build_where_from_query(retrieval_query.query)
        except Exception:
            where = {}
        results = self.knowledge_retriever.search(
            retrieval_query.query,
            top_k=top_k,
            where=where if where else None,
        )
        docs = []
        for result in results:
            distance = float(result.get("distance", 1.0) or 1.0)
            docs.append(
                Document(
                    content=result.get("content", ""),
                    metadata=result.get("metadata", {}) or {},
                    score=float(result.get("score", max(0.0, 1.0 - distance))),
                    source_type="vector",
                )
            )
        return docs

    def bm25_search(self, retrieval_query: RetrievalQuery, top_k: int = 5) -> List[Document]:
        if not self.knowledge_retriever or not getattr(self.knowledge_retriever, "collection", None):
            return []
        if self._bm25_adapter is None:
            self._bm25_adapter = BM25ChromaAdapter(self.knowledge_retriever.collection)
        return self._bm25_adapter.search(retrieval_query.query, top_k=top_k, threshold=0.0)

    def rerank_documents(
        self,
        documents: Sequence[Document],
        context: RetrievalContext,
        query: Optional[RetrievalQuery] = None,
    ) -> List[Document]:
        return rerank_documents(documents, context, query)

    def evaluate_retrieval(
        self,
        documents: Sequence[Document],
        context: RetrievalContext,
        query: Optional[RetrievalQuery] = None,
    ) -> Dict[str, Any]:
        return evaluate_retrieval(documents, context, query)
