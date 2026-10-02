"""Query understanding: synonym expansion (for keyword search) and identifier detection."""

import re
from dataclasses import dataclass, field
from functools import lru_cache

import yaml

from rfp.settings import PROJECT_ROOT, SearchConfig

EXPANSION_PATH = PROJECT_ROOT / "config" / "query_expansion.yaml"
TOKEN = re.compile(r"[A-Za-z0-9#][A-Za-z0-9#-]*")


@dataclass
class QueryPlan:
    original: str
    keyword_query: str                       # original + expansions, for BM25
    expansions: list[str] = field(default_factory=list)
    identifiers: list[str] = field(default_factory=list)
    sparse_weight: float = 1.0


@lru_cache
def _synonym_groups() -> list[list[str]]:
    data = yaml.safe_load(EXPANSION_PATH.read_text()) if EXPANSION_PATH.exists() else {}
    return [[t.lower() for t in group] for group in (data or {}).get("synonyms", [])]


def _contains(text: str, term: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text) is not None


def expand_query(query: str) -> list[str]:
    q = query.lower()
    extra: list[str] = []
    for group in _synonym_groups():
        if any(_contains(q, term) for term in group):
            extra += [t for t in group if not _contains(q, t) and t not in extra]
    return extra


def find_identifiers(query: str) -> list[str]:
    """Tokens that mix letters and digits and are at least 5 chars: JA-207652, WD22TB4, 210-BLYZ."""
    return [
        tok for tok in TOKEN.findall(query)
        if len(tok) >= 5 and re.search(r"\d", tok) and re.search(r"[A-Za-z]", tok)
    ]


def plan_query(query: str, cfg: SearchConfig) -> QueryPlan:
    expansions = expand_query(query)
    identifiers = find_identifiers(query)
    return QueryPlan(
        original=query,
        keyword_query=" ".join([query, *expansions]),
        expansions=expansions,
        identifiers=identifiers,
        sparse_weight=cfg.identifier_sparse_weight if identifiers else cfg.sparse_weight,
    )