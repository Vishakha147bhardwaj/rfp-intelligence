from qdrant_client import models

from rfp.search.fusion import reciprocal_rank_fusion
from rfp.search.query import expand_query, find_identifiers, plan_query
from rfp.search.store import build_filter
from rfp.settings import SearchConfig


def test_rrf_rewards_agreement():
    fused = reciprocal_rank_fusion([["a", "b", "c"], ["c", "a"]])
    assert list(fused) == ["a", "c", "b"]  # a is high in both lists


def test_rrf_weights_shift_the_winner():
    fused = reciprocal_rank_fusion([["a", "b", "c"], ["c", "a"]], weights=[1.0, 3.0])
    assert next(iter(fused)) == "c"


def test_deadline_expands_to_due_date():
    extra = expand_query("What is the deadline for Bid1?")
    assert "due date" in extra and "closing date" in extra


def test_identifiers_detected_but_not_bid_names():
    assert find_identifiers("Is JA-207652 the same as WD22TB4 in Bid1 with DDR5?") == [
        "JA-207652",
        "WD22TB4",
    ]


def test_identifier_query_boosts_keyword_weight():
    cfg = SearchConfig()
    assert (
        plan_query("part 210-BLYZ", cfg).sparse_weight == cfg.identifier_sparse_weight
    )
    assert plan_query("warranty terms", cfg).sparse_weight == cfg.sparse_weight


def test_filter_list_means_any_of():
    flt = build_filter(
        bid_id="Bid2", doc_type=["rfp", "addendum"], addendum_number=None
    )
    assert len(flt.must) == 2
    assert isinstance(flt.must[1].match, models.MatchAny)
