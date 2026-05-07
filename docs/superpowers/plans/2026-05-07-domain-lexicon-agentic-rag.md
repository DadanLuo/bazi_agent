# Agentic RAG Runtime Domain Lexicon Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve 八字 Agentic RAG retrieval at runtime with a domain lexicon, state-aware query expansion, sidecar BM25, reranking, and bounded ReAct orchestration without rebuilding Chroma.

**Architecture:** Keep the existing Chroma collection read-only and avoid changing ingestion embeddings. Build runtime metadata from the LangGraph state, generate multi-angle retrieval queries, let the Agentic RAG orchestrator call vector/BM25/rerank/evaluate tools, and fall back to a deterministic pipeline when LLM tool calling is unavailable.

**Tech Stack:** Python 3.10+, pytest, ChromaDB, DashScope/OpenAI-compatible tool calling, existing LangGraph Agentic RAG modules under `src/rag/agentic`.

---

## Scope

This first phase does:

- Add `src/rag/domain_lexicon.json` and `src/rag/domain_lexicon.py`.
- Keep `src/rag/term_normalizer.py` as a compatibility facade.
- Add runtime `RetrievalContext` and `RetrievalQuery`.
- Add query expansion based on query + LangGraph state.
- Add sidecar BM25 over the active Chroma collection.
- Add runtime rerank/evaluate tools.
- Add bounded ReAct orchestration with deterministic fallback.
- Pass full upstream `BaziAgentState` into Agentic RAG.

This first phase does not:

- Modify `src/rag/knowledge_processor.py`.
- Enrich document embeddings at ingestion time.
- Rebuild Chroma.
- Add `RAG_LEXICON_VERSION`.
- Write LangGraph state into Chroma metadata.

## Implementation Tasks

### Task 1: Domain Lexicon

- [x] Create `src/rag/domain_lexicon.json`.
- [x] Create `src/rag/domain_lexicon.py`.
- [x] Support long-term-first extraction, alias normalization, related term expansion, and search tokenization.
- [x] Update `src/rag/term_normalizer.py` to delegate public compatibility functions to `DomainLexicon`.

### Task 2: Runtime Agentic Tools

- [x] Create `src/rag/agentic/tools.py`.
- [x] Add `RetrievalContext` with query, day master, month branch, wangshuai, geju, yongshen, jishen, ten_gods, domain terms, required terms, boost terms, and avoid terms.
- [x] Add `RetrievalQuery` with `angle`, `query`, `required_terms`, `boost_terms`, and `target_topic`.
- [x] Add `build_retrieval_context(query, graph_state)`.
- [x] Add `expand_query(context)` for 命局、格局、用神、十神制化 angles.
- [x] Add `BM25ChromaAdapter` that builds an in-memory BM25 index from the current Chroma collection and caches by `collection name + count`.
- [x] Add `rerank_documents` and `evaluate_retrieval`.

### Task 3: BM25 Domain Tokenization

- [x] Modify `src/rag/retrievers/bm25_retriever.py`.
- [x] Replace regex-only tokenization with `DomainLexicon.tokenize_for_search`.
- [x] Keep existing BM25 scoring and `Document(source_type="bm25")` output shape.

### Task 4: ReAct Orchestration

- [x] Create `src/rag/agentic/react_orchestrator.py`.
- [x] Prefer `DashScopeLLM.call_with_tools` when an LLM is available.
- [x] Bound tool loop by `max_rounds=3`.
- [x] Bound retrieval query fanout by `max_queries_per_round=3`.
- [x] Add deterministic fallback: context -> expand -> vector + BM25 -> rerank -> evaluate.
- [x] Return `retrieved_docs`, `final_context`, `reasoning_trace`, `evaluation`, and `tool_rounds`.

### Task 5: Agentic RAG Integration

- [x] Export new runtime tools from `src/rag/agentic/__init__.py`.
- [x] Add `graph_state` to `AgenticRAGState`.
- [x] Modify `src/rag/agentic/nodes.py::execute_retrieval_node` to call `ReactRAGOrchestrator`.
- [x] Modify `src/graph/nodes.py::agentic_rag_node` to pass the full upstream state into Agentic RAG.

## Test Plan

- [x] `tests/test_domain_lexicon_runtime.py`
  - `伤官佩印 -> 伤官配印`
  - `七煞 / 偏官 -> 七杀`
  - `杀重身轻 -> 杀旺身弱`
  - Long phrase matching preserves `杀印相生` and `食神制杀`.

- [x] `tests/test_agentic_rag_runtime_tools.py`
  - Runtime context uses LangGraph state for short follow-up queries.
  - Query expansion generates 命局、格局、用神 angles.
  - BM25 tokenizer preserves domain terms.
  - BM25 adapter builds an index from a mock Chroma collection.
  - Rerank prefers documents matching required and boost terms.
  - Evaluation reports missing required terms.
  - ReAct orchestrator uses deterministic fallback without LLM and stays within round limits.

## Verification Commands

```bash
pytest tests/test_domain_lexicon_runtime.py tests/test_agentic_rag_runtime_tools.py -v
python -c "from src.rag.agentic import ReactRAGOrchestrator, build_retrieval_context; print('agentic imports ok')"
```

## Operational Notes

- If the active Chroma collection is missing, existing initialization still logs a warning and Agentic RAG cannot retrieve real documents. This behavior existed before the runtime tool work.
- Chroma telemetry may attempt outbound requests during import or collection access; this does not affect local runtime tests.
- A second phase can optionally add ingestion-time embedding enrichment and index versioning if runtime retrieval quality remains insufficient.
