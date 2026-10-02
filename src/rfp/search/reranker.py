"""Cross-encoder reranker: scores (query, passage) pairs together. Loads once, on first use."""

from functools import lru_cache

from fastembed.rerank.cross_encoder import TextCrossEncoder

from rfp.settings import get_settings


@lru_cache
def _model() -> TextCrossEncoder:
    return TextCrossEncoder(get_settings().search.rerank_model)


def rerank_scores(query: str, passages: list[str]) -> list[float]:
    return list(_model().rerank(query, passages))