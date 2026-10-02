"""Retrieval agent: runs each field's queries through the search engine, returns numbered evidence."""

from collections.abc import Callable

import structlog
from pydantic import BaseModel, Field

from rfp.schemas.agents import Evidence, FieldSpec
from rfp.search.engine import SearchResult
from rfp.search.fusion import reciprocal_rank_fusion
from rfp.settings import AgentsConfig, get_settings

log = structlog.get_logger()

RESULT_KEYS = ("chunk_id", "bid_id", "file_name", "page_number", "doc_type", "addendum_number",
               "section", "text", "context_header", "chunk_index")


class EvidenceBundle(BaseModel):
    """Evidence for a set of fields. Agents refer to passages only by evidence_id."""

    evidence: list[Evidence] = Field(default_factory=list)
    by_field: dict[str, list[str]] = Field(default_factory=dict)   # field -> evidence_ids, best first
    queries_run: int = 0
    neighbors_added: int = 0

    def get(self, evidence_id: str) -> Evidence | None:
        return next((e for e in self.evidence if e.evidence_id == evidence_id), None)

    def for_fields(self, names: list[str]) -> list[Evidence]:
        """Evidence for these fields, deduplicated, in first-seen order."""
        seen: list[str] = []
        for name in names:
            for eid in self.by_field.get(name, []):
                if eid not in seen:
                    seen.append(eid)
        return [e for eid in seen if (e := self.get(eid))]


class RetrievalAgent:
    def __init__(self, engine, cfg: AgentsConfig | None = None,
                 fetch_chunks: Callable[[str, str, list[int]], list[dict]] | None = None):
        self.engine = engine            # anything with .search(query, top_k=, bid_id=, doc_type=)
        self.cfg = cfg or get_settings().agents
        store = getattr(engine, "store", None)
        self.fetch_chunks = fetch_chunks or getattr(store, "get_chunks", None)

    def gather(self, bid_id: str, specs: list[FieldSpec],
               extra_queries: dict[str, list[str]] | None = None,
               doc_type: str | list[str] | None = None,
               id_prefix: str = "E") -> EvidenceBundle:
        bundle = EvidenceBundle()
        id_for_chunk: dict[str, str] = {}

        for spec in specs:
            queries = spec.queries + (extra_queries or {}).get(spec.name, [])
            k = spec.evidence_k or self.cfg.per_field_k
            rankings: list[list[str]] = []
            hits: dict[str, SearchResult] = {}
            for query in queries:
                results = self.engine.search(query, top_k=max(self.cfg.per_query_k, k),
                                             bid_id=bid_id, doc_type=doc_type)
                bundle.queries_run += 1
                rankings.append([r.chunk_id for r in results])
                for r in results:
                    hits.setdefault(r.chunk_id, r)

            best = list(reciprocal_rank_fusion(rankings))[:k] if rankings else []
            if spec.expand_neighbors and self.fetch_chunks and best:
                added = self._neighbors(bid_id, best, hits)
                bundle.neighbors_added += len(added)
                best += added

            for chunk_id in best:
                if chunk_id not in id_for_chunk:
                    hit = hits[chunk_id]
                    evidence_id = f"{id_prefix}{len(bundle.evidence) + 1}"
                    id_for_chunk[chunk_id] = evidence_id
                    bundle.evidence.append(Evidence(
                        evidence_id=evidence_id, chunk_id=chunk_id, bid_id=hit.bid_id,
                        file_name=hit.file_name, page_number=hit.page_number, doc_type=hit.doc_type,
                        addendum_number=hit.addendum_number, text=hit.text, score=hit.score,
                    ))
            bundle.by_field[spec.name] = [id_for_chunk[c] for c in best]

        log.info("retrieval_done", bid=bid_id, fields=len(specs), doc_type=doc_type,
                 queries=bundle.queries_run, evidence=len(bundle.evidence),
                 neighbors_added=bundle.neighbors_added)
        return bundle

    def _neighbors(self, bid_id: str, best: list[str], hits: dict[str, SearchResult]) -> list[str]:
        """Chunks just before/after the top seeds in the same file (small-to-big expansion)."""
        wanted: dict[str, set[int]] = {}
        for chunk_id in best[: self.cfg.neighbor_seeds]:
            seed = hits[chunk_id]
            if seed.chunk_index is None:
                continue
            for d in range(1, self.cfg.neighbor_window + 1):
                wanted.setdefault(seed.file_name, set()).update({seed.chunk_index - d, seed.chunk_index + d})

        selected, added = set(best), []
        for file_name, indexes in wanted.items():
            payloads = self.fetch_chunks(bid_id, file_name, sorted(i for i in indexes if i >= 0))
            for p in sorted(payloads, key=lambda p: p["chunk_index"]):
                chunk_id = p["chunk_id"]
                if chunk_id in selected:
                    continue
                if chunk_id not in hits:
                    hits[chunk_id] = SearchResult(score=0.0, **{key: p.get(key) for key in RESULT_KEYS})
                selected.add(chunk_id)
                added.append(chunk_id)
        return added
