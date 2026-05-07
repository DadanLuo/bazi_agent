"""ReAct-style runtime orchestration for Agentic RAG tools."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from src.rag.agentic.state import Document
from src.rag.agentic.tools import (
    AgenticRAGToolset,
    RetrievalContext,
    RetrievalQuery,
    evaluate_retrieval,
    expand_query,
    rerank_documents,
)

logger = logging.getLogger(__name__)


class ReactRAGOrchestrator:
    """Small bounded tool loop with deterministic fallback."""

    def __init__(
        self,
        llm: Any = None,
        toolset: Optional[AgenticRAGToolset] = None,
        max_rounds: int = 3,
        max_queries_per_round: int = 3,
    ):
        self.llm = llm
        self.toolset = toolset or AgenticRAGToolset()
        self.max_rounds = max(1, max_rounds)
        self.max_queries_per_round = max(1, max_queries_per_round)

    def run(self, query: str, graph_state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if self.llm is None or not hasattr(self.llm, "call_with_tools"):
            return self._deterministic_fallback(query, graph_state)

        try:
            return self._run_tool_loop(query, graph_state)
        except Exception as exc:
            logger.warning("ReAct RAG tool loop failed; using deterministic fallback: %s", exc)
            return self._deterministic_fallback(query, graph_state)

    def _run_tool_loop(self, query: str, graph_state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        messages: List[Dict[str, Any]] = [
            {
                "role": "user",
                "content": (
                    "Use the RAG tools to retrieve bazi domain evidence. "
                    "Call build_retrieval_context first, then expand/search/rerank/evaluate. "
                    f"Query: {query}"
                ),
            }
        ]
        tools = self._tool_schemas()
        context: Optional[RetrievalContext] = None
        queries: List[RetrievalQuery] = []
        docs: List[Document] = []
        trace: List[str] = []
        evaluation: Dict[str, Any] = {"need_more": True, "coverage": {}}

        for round_idx in range(self.max_rounds):
            result = self.llm.call_with_tools(messages=messages, tools=tools)
            if not getattr(result, "has_tool_calls", False):
                break

            messages.append(
                {
                    "role": "assistant",
                    "content": getattr(result, "content", "") or "",
                    "tool_calls": result.tool_calls,
                }
            )

            for call in result.tool_calls[: self.max_queries_per_round]:
                name = (call.get("function") or {}).get("name", "")
                raw_args = (call.get("function") or {}).get("arguments", "{}")
                args = json.loads(raw_args or "{}")

                if name == "build_retrieval_context":
                    context = self.toolset.build_retrieval_context(query, graph_state)
                    trace.append("build_retrieval_context")
                    payload = asdict(context)
                elif name == "expand_query":
                    context = context or self.toolset.build_retrieval_context(query, graph_state)
                    queries = self.toolset.expand_query(context)
                    trace.append("expand_query")
                    payload = [asdict(item) for item in queries]
                elif name in {"vector_search", "bm25_search"}:
                    context = context or self.toolset.build_retrieval_context(query, graph_state)
                    queries = queries or self.toolset.expand_query(context)
                    selected = self._select_query(queries, args)
                    if name == "vector_search":
                        new_docs = self.toolset.vector_search(selected)
                    else:
                        new_docs = self.toolset.bm25_search(selected)
                    docs.extend(new_docs)
                    trace.append(f"{name}:{selected.angle}")
                    payload = [{"content": doc.content[:120], "score": doc.score} for doc in new_docs]
                elif name == "rerank_documents":
                    context = context or self.toolset.build_retrieval_context(query, graph_state)
                    docs = self.toolset.rerank_documents(docs, context)
                    trace.append("rerank_documents")
                    payload = [{"content": doc.content[:120], "score": doc.score} for doc in docs]
                elif name == "evaluate_retrieval":
                    context = context or self.toolset.build_retrieval_context(query, graph_state)
                    evaluation = self.toolset.evaluate_retrieval(docs, context)
                    trace.append("evaluate_retrieval")
                    payload = evaluation
                else:
                    payload = {"error": f"unknown tool {name}"}

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id", ""),
                        "content": json.dumps(payload, ensure_ascii=False),
                    }
                )

            if docs and evaluation.get("need_more") is False:
                break

        if not docs:
            return self._deterministic_fallback(query, graph_state)

        context = context or self.toolset.build_retrieval_context(query, graph_state)
        docs = self.toolset.rerank_documents(docs, context)
        evaluation = self.toolset.evaluate_retrieval(docs, context)
        return self._build_result(query, docs, trace, evaluation, min(len(trace), self.max_rounds))

    def _deterministic_fallback(
        self,
        query: str,
        graph_state: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        trace: List[str] = ["fallback:build_retrieval_context"]
        context = self.toolset.build_retrieval_context(query, graph_state)
        queries = self.toolset.expand_query(context)[: self.max_queries_per_round]
        trace.append("fallback:expand_query")

        docs: List[Document] = []
        for retrieval_query in queries:
            docs.extend(self.toolset.vector_search(retrieval_query))
            docs.extend(self.toolset.bm25_search(retrieval_query))
            trace.append(f"fallback:search:{retrieval_query.angle}")

        ranked = self.toolset.rerank_documents(docs, context, queries[0] if queries else None)
        evaluation = self.toolset.evaluate_retrieval(ranked, context, queries[0] if queries else None)
        trace.extend(["fallback:rerank_documents", "fallback:evaluate_retrieval"])
        return self._build_result(query, ranked, trace, evaluation, min(len(queries), self.max_rounds))

    @staticmethod
    def _select_query(queries: List[RetrievalQuery], args: Dict[str, Any]) -> RetrievalQuery:
        angle = str(args.get("angle", "") or "")
        for item in queries:
            if item.angle == angle:
                return item
        return queries[0]

    @staticmethod
    def _build_result(
        query: str,
        docs: List[Document],
        trace: List[str],
        evaluation: Dict[str, Any],
        tool_rounds: int,
    ) -> Dict[str, Any]:
        context_lines = ["【相关古籍参考】"]
        for idx, doc in enumerate(docs[:5], 1):
            source = doc.metadata.get("source", "未知") if doc.metadata else "未知"
            context_lines.append(f"{idx}. 来源: {source}；分数: {doc.score:.2f}\n{doc.content}")

        return {
            "query": query,
            "retrieved_docs": [
                {
                    "content": doc.content,
                    "metadata": doc.metadata,
                    "score": doc.score,
                    "source_type": doc.source_type,
                }
                for doc in docs
            ],
            "final_context": "\n\n".join(context_lines) if docs else "未检索到相关知识。",
            "reasoning_trace": trace,
            "evaluation": evaluation,
            "tool_rounds": tool_rounds,
        }

    @staticmethod
    def _tool_schemas() -> List[Dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "build_retrieval_context",
                    "description": "Extract runtime bazi retrieval context from query and graph state.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "expand_query",
                    "description": "Generate multi-angle bazi retrieval queries.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "vector_search",
                    "description": "Run vector search for one query angle.",
                    "parameters": {
                        "type": "object",
                        "properties": {"angle": {"type": "string"}},
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "bm25_search",
                    "description": "Run BM25 keyword search for one query angle.",
                    "parameters": {
                        "type": "object",
                        "properties": {"angle": {"type": "string"}},
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "rerank_documents",
                    "description": "Rerank retrieved documents with runtime domain terms.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "evaluate_retrieval",
                    "description": "Evaluate coverage and decide whether more retrieval is needed.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        ]
