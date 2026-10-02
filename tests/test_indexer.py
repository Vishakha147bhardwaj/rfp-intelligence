import pytest
from qdrant_client import models

import rfp.search.indexer as indexer
from rfp.schemas.documents import DocType, Page, ParsedDocument
from rfp.search.indexer import index_documents
from rfp.search.store import ChunkStore
from rfp.settings import SearchConfig


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(indexer, "embed_dense", lambda texts: [[0.1] * 384 for _ in texts])
    monkeypatch.setattr(indexer, "embed_sparse",
                        lambda texts: [models.SparseVector(indices=[1], values=[1.0]) for _ in texts])
    s = ChunkStore(SearchConfig(qdrant_path=str(tmp_path / "q")))
    yield s
    s.close()


def doc(name, file_hash, text="Delivery within 45 days of award."):
    return ParsedDocument(bid_id="B1", file_name=name, file_path=name, file_hash=file_hash,
                          file_type="pdf", doc_type=DocType.RFP,
                          pages=[Page(page_number=1, text=text)])


def test_incremental_indexing(store, tmp_path):
    manifest = tmp_path / "manifest.json"

    first = index_documents([doc("a.pdf", "h1"), doc("b.pdf", "h2")], store, manifest)
    assert set(first.indexed) == {"a.pdf", "b.pdf"} and store.count(bid_id="B1") == 2

    second = index_documents([doc("a.pdf", "h1"), doc("b.pdf", "h2")], store, manifest)
    assert second.indexed == {} and set(second.skipped) == {"a.pdf", "b.pdf"}

    third = index_documents([doc("a.pdf", "h1-changed"), doc("b.pdf", "h2")], store, manifest)
    assert list(third.indexed) == ["a.pdf"] and store.count(bid_id="B1") == 2

    fourth = index_documents([doc("a.pdf", "h1-changed")], store, manifest)
    assert fourth.removed == ["b.pdf"] and store.count(file_name="b.pdf") == 0