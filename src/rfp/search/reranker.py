"""Cross-encoder reranker: scores (query, passage) pairs together. One model per name, cached."""

from functools import lru_cache

from fastembed.rerank.cross_encoder import TextCrossEncoder


@lru_cache
def _model(name: str) -> TextCrossEncoder:
    return TextCrossEncoder(name)


def rerank_scores(query: str, passages: list[str], model_name: str) -> list[float]:
    return list(_model(model_name).rerank(query, passages))