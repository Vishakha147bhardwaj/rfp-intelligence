"""SearchEngine: hybrid retrieval + RRF + reranking, with metadata filters and citations."""

from typing import Literal

from pydantic import BaseModel

from rfp.search.embeddings import embed_dense_query, embed_sparse_query
from rfp.search.fusion import reciprocal_rank_fusion
from rfp.search.query import plan_query
from rfp.search.reranker import rerank_scores
from rfp.search.store import DENSE, SPARSE, ChunkStore, build_filter
from rfp.settings import SearchConfig, get_settings

Mode = Literal["dense", "sparse", "hybrid", "hybrid_rerank"]
MODES = ("dense", "sparse", "hybrid", "hybrid_rerank")


class SearchResult(BaseModel):
    chunk_id: str
    bid_id: str
    file_name: str
    page_number: int
    doc_type: str
    addendum_number: int | None = None
    section: str | None = None
    text: str
    context_header: str
    score: float
    dense_rank: int | None = None     # position in the dense list (None = not retrieved)
    sparse_rank: int | None = None

    @property
    def citation(self) -> str:
        return f"{self.file_name}, p.{self.page_number}"


class SearchEngine:
    def __init__(self, store: ChunkStore, cfg: SearchConfig | None = None):
        self.store = store
        self.cfg = cfg or get_settings().search

    def _retrieve(self, vector, using: str, flt, limit: int):
        return self.store.client.query_points(
            self.store.collection, query=vector, using=using,
            query_filter=flt, limit=limit, with_payload=True,
        ).points

    def search(
        self,
        query: str,
        top_k: int = 5,
        mode: Mode = "hybrid_rerank",
        bid_id: str | list[str] | None = None,
        doc_type: str | list[str] | None = None,
        addendum_number: int | None = None,
        file_name: str | None = None,
    ) -> list[SearchResult]:
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        plan = plan_query(query, self.cfg)
        flt = build_filter(bid_id=bid_id, doc_type=doc_type,
                           addendum_number=addendum_number, file_name=file_name)
        n = self.cfg.retrieve_k
        payloads: dict[str, dict] = {}
        dense_ids: list[str] = []
        sparse_ids: list[str] = []

        if mode != "sparse":
            for p in self._retrieve(embed_dense_query(query), DENSE, flt, n):
                payloads[str(p.id)] = p.payload
                dense_ids.append(str(p.id))
        if mode != "dense":
            for p in self._retrieve(embed_sparse_query(plan.keyword_query), SPARSE, flt, n):
                payloads[str(p.id)] = p.payload
                sparse_ids.append(str(p.id))

        rankings, weights = [], []
        if dense_ids:
            rankings.append(dense_ids)
            weights.append(1.0)
        if sparse_ids:
            rankings.append(sparse_ids)
            weights.append(plan.sparse_weight)
        fused = reciprocal_rank_fusion(rankings, weights, self.cfg.rrf_k)
        candidates = list(fused)[:n]

        if mode == "hybrid_rerank" and candidates:
            passages = [
                (f"{payloads[c]['context_header']}\n" if self.cfg.rerank_include_header else "")
                + payloads[c]["text"]
                for c in candidates
            ]
            scores = dict(zip(candidates, rerank_scores(query, passages, self.cfg.rerank_model)))
            candidates.sort(key=lambda c: scores[c], reverse=True)
        else:
            scores = fused

        return [
            SearchResult(
                chunk_id=c,
                score=float(scores[c]),
                dense_rank=dense_ids.index(c) + 1 if c in dense_ids else None,
                sparse_rank=sparse_ids.index(c) + 1 if c in sparse_ids else None,
                **{k: payloads[c][k] for k in ("bid_id", "file_name", "page_number", "doc_type",
                                                "addendum_number", "section", "text", "context_header")},
            )
            for c in candidates[:top_k]
        ]