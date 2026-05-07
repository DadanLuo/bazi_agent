"""Runtime domain lexicon for 八字 RAG retrieval."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence


def _unique(values: Iterable[str]) -> List[str]:
    return list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


@dataclass(frozen=True)
class DomainTerm:
    canonical: str
    category: str
    aliases: List[str] = field(default_factory=list)
    related: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class DomainTermHit:
    text: str
    canonical: str
    category: str
    start: int
    end: int
    is_alias: bool = False


class DomainLexicon:
    """Domain terms, aliases, and query-time lexical helpers."""

    def __init__(self, payload: Dict[str, Any]):
        self.version = str(payload.get("version", "runtime-v1"))
        self.terms: Dict[str, DomainTerm] = {}
        self.alias_to_canonical: Dict[str, str] = {}
        self._surface_to_term: Dict[str, DomainTerm] = {}

        for category, terms in (payload.get("categories") or {}).items():
            for canonical, spec in terms.items():
                term = DomainTerm(
                    canonical=canonical,
                    category=category,
                    aliases=list(spec.get("aliases", [])),
                    related=list(spec.get("related", [])),
                )
                self.terms[canonical] = term
                self._surface_to_term[canonical] = term
                for alias in term.aliases:
                    self.alias_to_canonical[alias] = canonical
                    self._surface_to_term[alias] = term

        self._surfaces = sorted(self._surface_to_term, key=len, reverse=True)

    def normalize_text(self, text: str) -> str:
        normalized = str(text or "")
        for surface in self._surfaces:
            term = self._surface_to_term[surface]
            if surface != term.canonical:
                normalized = normalized.replace(surface, term.canonical)
        return normalized.replace("与", "").replace("和", "")

    def extract(self, text: str) -> List[DomainTermHit]:
        raw = str(text or "")
        normalized = self.normalize_text(raw)
        occupied = [False] * len(normalized)
        hits: List[DomainTermHit] = []

        for surface in self._surfaces:
            term = self._surface_to_term[surface]
            search_surface = term.canonical if surface != term.canonical else surface
            for match in re.finditer(re.escape(search_surface), normalized):
                start, end = match.span()
                if any(occupied[start:end]):
                    continue
                for idx in range(start, end):
                    occupied[idx] = True
                hits.append(
                    DomainTermHit(
                        text=search_surface,
                        canonical=term.canonical,
                        category=term.category,
                        start=start,
                        end=end,
                        is_alias=surface != term.canonical,
                    )
                )

        return sorted(hits, key=lambda hit: hit.start)

    def canonical_terms(self, text: str) -> List[str]:
        return _unique(hit.canonical for hit in self.extract(text))

    def expand_terms(self, terms: Sequence[str]) -> List[str]:
        expanded: List[str] = []
        for term_name in terms:
            canonical = self.alias_to_canonical.get(term_name, term_name)
            expanded.append(canonical)
            term = self.terms.get(canonical)
            if term:
                expanded.extend(term.related)
        return _unique(expanded)

    def tokenize_for_search(self, text: str) -> List[str]:
        normalized = self.normalize_text(text)
        domain_terms = self.canonical_terms(normalized)
        fallback = re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}", normalized)
        return _unique(domain_terms + fallback)

    def lexical_score(self, text: str, terms: Sequence[str]) -> float:
        haystack = self.normalize_text(text)
        unique_terms = _unique(terms)
        if not unique_terms:
            return 0.0

        score = 0.0
        for term in unique_terms:
            canonical = self.alias_to_canonical.get(term, term)
            if canonical in haystack:
                score += 1.0 + min(len(canonical), 6) * 0.08
        return score / len(unique_terms)


@lru_cache(maxsize=1)
def get_domain_lexicon() -> DomainLexicon:
    path = Path(__file__).with_name("domain_lexicon.json")
    with open(path, "r", encoding="utf-8") as f:
        return DomainLexicon(json.load(f))
