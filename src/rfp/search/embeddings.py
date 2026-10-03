"""Dense (bge-small) and sparse (BM25) encoders. Models load once, on first use."""

from functools import lru_cache

from fastembed import SparseTextEmbedding, TextEmbedding
from qdrant_client import models

from rfp.settings import get_settings


@lru_cache
def _dense_model() -> TextEmbedding:
    return TextEmbedding(get_settings().search.dense_model)


@lru_cache
def _sparse_model() -> SparseTextEmbedding:
    return SparseTextEmbedding(get_settings().search.sparse_model)


def _to_sparse(vec) -> models.SparseVector:
    return models.SparseVector(indices=vec.indices.tolist(), values=vec.values.tolist())


def embed_dense(texts: list[str]) -> list[list[float]]:
    return [v.tolist() for v in _dense_model().embed(texts)]


def embed_sparse(texts: list[str]) -> list[models.SparseVector]:
    return [_to_sparse(v) for v in _sparse_model().embed(texts)]


def embed_dense_query(query: str) -> list[float]:
    return next(iter(_dense_model().query_embed(query))).tolist()


def embed_sparse_query(query: str) -> models.SparseVector:
    return _to_sparse(next(iter(_sparse_model().query_embed(query))))
