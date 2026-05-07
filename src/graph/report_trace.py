from __future__ import annotations

from typing import Any


ENGINE_FIELDS = [
    "bazi_result",
    "wuxing_analysis",
    "geju_analysis",
    "yongshen_analysis",
    "liunian_analysis",
]


def _document_source(metadata: dict[str, Any]) -> str:
    return str(
        metadata.get("source")
        or metadata.get("file")
        or metadata.get("path")
        or metadata.get("title")
        or "unknown"
    )


def build_report_trace(state: dict[str, Any]) -> dict[str, Any]:
    rag_info = state.get("rag_info") or {}
    rag_documents = []

    for index, doc in enumerate(rag_info.get("documents") or [], start=1):
        metadata = doc.get("metadata") or {}
        rag_documents.append(
            {
                "id": doc.get("evidence_id") or f"rag-{index}",
                "source": _document_source(metadata),
                "topic": metadata.get("topic"),
                "route": doc.get("route"),
                "distance": doc.get("distance"),
                "score": doc.get("score"),
                "content_preview": (doc.get("content") or "")[:160],
            }
        )

    used_engine_fields = [field for field in ENGINE_FIELDS if state.get(field)]

    return {
        "engine": {
            "used": bool(used_engine_fields),
            "fields": used_engine_fields,
            "description": "Deterministic chart, wuxing, geju, yongshen, and liunian data.",
        },
        "rag": {
            "used": bool(rag_documents),
            "status": rag_info.get("status", "skipped"),
            "reason": rag_info.get("reason", ""),
            "queries": rag_info.get("queries", []),
            "doc_count": len(rag_documents),
            "documents": rag_documents,
        },
        "llm": {
            "used": bool(state.get("llm_response")),
            "field": "llm_response" if state.get("llm_response") else None,
            "description": "Natural-language synthesis based on engine data and retrieved context.",
        },
    }


def attach_traceability(report: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    report["traceability"] = build_report_trace(state)
    return report
