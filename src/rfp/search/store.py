"""Qdrant collection holding dense + sparse vectors and chunk metadata per point."""

import threading

from qdrant_client import QdrantClient, models

from rfp.schemas.chunks import Chunk
from rfp.settings import PROJECT_ROOT, SearchConfig, get_settings

DENSE = "dense"
SPARSE = "sparse"


def build_filter(**conditions) -> models.Filter | None:
    """Filter from keyword args; None is ignored, a list means 'any of'. e.g. bid_id='Bid2'."""
    must = []
    for key, value in conditions.items():
        if value is None:
            continue
        match = (
            models.MatchAny(any=list(value))
            if isinstance(value, (list, tuple))
            else models.MatchValue(value=value)
        )
        must.append(models.FieldCondition(key=key, match=match))
    return models.Filter(must=must) if must else None


class ChunkStore:
    def __init__(self, cfg: SearchConfig | None = None):
        cfg = cfg or get_settings().search
        path = PROJECT_ROOT / cfg.qdrant_path  # an absolute path stays absolute
        path.mkdir(parents=True, exist_ok=True)
        try:
            self.client = QdrantClient(path=str(path))
        except RuntimeError as exc:
            if "already accessed" in str(exc):
                raise RuntimeError(
                    "The search index is open in another process - is `python main.py serve` "
                    "running? Stop it (Ctrl+C) or use the API instead of the CLI."
                ) from exc
            raise
        self.collection = cfg.collection
        self.lock = (
            threading.RLock()
        )  # embedded Qdrant: one operation at a time, across threads
        self._ensure_collection(cfg.dense_dim)

    def _ensure_collection(self, dim: int) -> None:
        with self.lock:
            if self.client.collection_exists(self.collection):
                return
            self.client.create_collection(
                self.collection,
                vectors_config={
                    DENSE: models.VectorParams(
                        size=dim, distance=models.Distance.COSINE
                    )
                },
                sparse_vectors_config={
                    SPARSE: models.SparseVectorParams(modifier=models.Modifier.IDF)
                },
            )
        # Note: embedded (local) Qdrant ignores payload indexes; with a Qdrant server we would
        # create indexes on bid_id, doc_type, file_name, addendum_number for fast filtering.

    def query(self, vector, using: str, flt, limit: int):
        with self.lock:
            return self.client.query_points(
                self.collection,
                query=vector,
                using=using,
                query_filter=flt,
                limit=limit,
                with_payload=True,
            ).points

    def upsert(
        self,
        chunks: list[Chunk],
        dense: list[list[float]],
        sparse: list[models.SparseVector],
    ) -> None:
        points = [
            models.PointStruct(
                id=c.chunk_id,
                vector={DENSE: d, SPARSE: s},
                payload=c.model_dump(mode="json"),
            )
            for c, d, s in zip(chunks, dense, sparse, strict=True)
        ]
        with self.lock:
            self.client.upsert(self.collection, points=points)

    def delete_file(self, bid_id: str, file_name: str) -> None:
        with self.lock:
            self.client.delete(
                self.collection,
                points_selector=models.FilterSelector(
                    filter=build_filter(bid_id=bid_id, file_name=file_name)
                ),
            )

    def count(self, **conditions) -> int:
        with self.lock:
            return self.client.count(
                self.collection, count_filter=build_filter(**conditions), exact=True
            ).count

    def get_chunks(
        self, bid_id: str, file_name: str, chunk_indexes: list[int]
    ) -> list[dict]:
        """Payloads of specific chunks of one file, by chunk_index (for neighbour expansion)."""
        if not chunk_indexes:
            return []
        with self.lock:
            points, _ = self.client.scroll(
                self.collection,
                scroll_filter=build_filter(
                    bid_id=bid_id, file_name=file_name, chunk_index=list(chunk_indexes)
                ),
                limit=len(chunk_indexes),
                with_payload=True,
                with_vectors=False,
            )
        return [p.payload for p in points]

    def get_texts(self, chunk_ids: list[str]) -> dict[str, str]:
        """chunk_id -> text, for the validator to read exactly what a value cites."""
        ids = list(dict.fromkeys(c for c in chunk_ids if c))
        if not ids:
            return {}
        with self.lock:
            points = self.client.retrieve(
                self.collection, ids=ids, with_payload=["text"], with_vectors=False
            )
        return {str(p.id): (p.payload or {}).get("text", "") for p in points}

    def close(self) -> None:
        self.client.close()
