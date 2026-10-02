"""Qdrant collection holding dense + sparse vectors and chunk metadata per point."""

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
        match = (models.MatchAny(any=list(value)) if isinstance(value, (list, tuple))
                 else models.MatchValue(value=value))
        must.append(models.FieldCondition(key=key, match=match))
    return models.Filter(must=must) if must else None


class ChunkStore:
    def __init__(self, cfg: SearchConfig | None = None):
        cfg = cfg or get_settings().search
        path = PROJECT_ROOT / cfg.qdrant_path          # an absolute path stays absolute
        path.mkdir(parents=True, exist_ok=True)
        self.client = QdrantClient(path=str(path))
        self.collection = cfg.collection
        self._ensure_collection(cfg.dense_dim)

    def _ensure_collection(self, dim: int) -> None:
        if self.client.collection_exists(self.collection):
            return
        self.client.create_collection(
            self.collection,
            vectors_config={DENSE: models.VectorParams(size=dim, distance=models.Distance.COSINE)},
            sparse_vectors_config={SPARSE: models.SparseVectorParams(modifier=models.Modifier.IDF)},
        )
        # Note: embedded (local) Qdrant ignores payload indexes; with a Qdrant server we would
        # create indexes on bid_id, doc_type, file_name, addendum_number for fast filtering.

    def upsert(self, chunks: list[Chunk], dense: list[list[float]],
               sparse: list[models.SparseVector]) -> None:
        points = [
            models.PointStruct(id=c.chunk_id, vector={DENSE: d, SPARSE: s},
                               payload=c.model_dump(mode="json"))
            for c, d, s in zip(chunks, dense, sparse, strict=True)
        ]
        self.client.upsert(self.collection, points=points)

    def delete_file(self, bid_id: str, file_name: str) -> None:
        self.client.delete(
            self.collection,
            points_selector=models.FilterSelector(filter=build_filter(bid_id=bid_id, file_name=file_name)),
        )

    def count(self, **conditions) -> int:
        return self.client.count(self.collection, count_filter=build_filter(**conditions), exact=True).count

    def close(self) -> None:
        self.client.close()