"""Retrieval agent: runs each field's queries through the search engine, returns numbered evidence."""

import structlog
from pydantic import BaseModel, Field

from rfp.schemas.agents import Evidence, FieldSpec
from rfp.search.fusion import reciprocal_rank_fusion
from rfp.settings import AgentsConfig, get_settings

log = structlog.get_logger()


class EvidenceBundle(BaseModel):
    """Evidence for a set of fields. Agents refer to passages only by evidence_id."""

    evidence: list[Evidence] = Field(default_factory=list)
    by_field: dict[str, list[str]] = Field(default_factory=dict)   # field -> evidence_ids, best first
    queries_run: int = 0

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
    def __init__(self, engine, cfg: AgentsConfig | None = None):
        self.engine = engine            # anything with .search(query, top_k=, bid_id=)
        self.cfg = cfg or get_settings().agents

    def gather(self, bid_id: str, specs: list[FieldSpec],
               extra_queries: dict[str, list[str]] | None = None) -> EvidenceBundle:
        bundle = EvidenceBundle()
        id_for_chunk: dict[str, str] = {}

        for spec in specs:
            queries = spec.queries + (extra_queries or {}).get(spec.name, [])
            rankings: list[list[str]] = []
            hits_by_chunk = {}
            for query in queries:
                hits = self.engine.search(query, top_k=self.cfg.per_query_k, bid_id=bid_id)
                bundle.queries_run += 1
                rankings.append([h.chunk_id for h in hits])
                for h in hits:
                    hits_by_chunk.setdefault(h.chunk_id, h)

            best = list(reciprocal_rank_fusion(rankings))[: self.cfg.per_field_k] if rankings else []
            for chunk_id in best:
                if chunk_id not in id_for_chunk:
                    hit = hits_by_chunk[chunk_id]
                    evidence_id = f"E{len(bundle.evidence) + 1}"
                    id_for_chunk[chunk_id] = evidence_id
                    bundle.evidence.append(Evidence(
                        evidence_id=evidence_id, chunk_id=chunk_id, bid_id=hit.bid_id,
                        file_name=hit.file_name, page_number=hit.page_number, doc_type=hit.doc_type,
                        addendum_number=hit.addendum_number, text=hit.text, score=hit.score,
                    ))
            bundle.by_field[spec.name] = [id_for_chunk[c] for c in best]

        log.info("retrieval_done", bid=bid_id, fields=len(specs),
                 queries=bundle.queries_run, evidence=len(bundle.evidence))
        return bundle