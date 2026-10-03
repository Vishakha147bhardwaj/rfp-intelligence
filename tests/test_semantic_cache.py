from rfp.agents.semantic_cache import SemanticCache, guard_tokens
from rfp.settings import CacheConfig

VECTORS = {
    "What is the delivery time for the Dell laptops?": [1.0, 0.0, 0.0],
    "What's the Dell laptop delivery time?": [0.99, 0.05, 0.0],  # same meaning
    "Who is the buyer?": [0.0, 1.0, 0.0],  # different meaning
    "What is the due date for Bid1?": [0.0, 0.0, 1.0],
    "What is the due date for Bid2?": [0.0, 0.01, 1.0],  # nearly identical vector!
}
ANSWER = {
    "answer": "Within 45 days of award [1].",
    "found": True,
    "bid_ids": ["Bid2"],
    "citations": [],
}


def make_cache(tmp_path):
    return SemanticCache(
        CacheConfig(similarity_threshold=0.95),
        path=tmp_path / "c.json",
        embed=lambda q: VECTORS[q],
    )


def test_paraphrase_hits(tmp_path):
    cache = make_cache(tmp_path)
    cache.store("What is the delivery time for the Dell laptops?", ANSWER, "fp1")
    hit, sim = cache.lookup("What's the Dell laptop delivery time?", "fp1")
    assert hit == ANSWER and sim >= 0.95


def test_different_question_misses(tmp_path):
    cache = make_cache(tmp_path)
    cache.store("What is the delivery time for the Dell laptops?", ANSWER, "fp1")
    assert cache.lookup("Who is the buyer?", "fp1")[0] is None


def test_different_bid_never_hits_even_if_vectors_are_close(tmp_path):
    cache = make_cache(tmp_path)
    cache.store("What is the due date for Bid1?", ANSWER, "fp1")
    assert guard_tokens("What is the due date for Bid1?") == ["bid1"]
    assert cache.lookup("What is the due date for Bid2?", "fp1")[0] is None


def test_reindexed_documents_invalidate_entries(tmp_path):
    cache = make_cache(tmp_path)
    cache.store("What is the delivery time for the Dell laptops?", ANSWER, "fp1")
    assert (
        cache.lookup("What is the delivery time for the Dell laptops?", "fp2")[0]
        is None
    )


def test_clear(tmp_path):
    cache = make_cache(tmp_path)
    cache.store("Who is the buyer?", ANSWER, "fp1")
    cache.clear()
    assert cache.lookup("Who is the buyer?", "fp1")[0] is None
