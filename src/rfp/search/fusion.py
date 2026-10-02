"""Reciprocal Rank Fusion: merge ranked lists using ranks, not raw (incomparable) scores."""


def reciprocal_rank_fusion(
    rankings: list[list[str]],
    weights: list[float] | None = None,
    k: int = 60,
) -> dict[str, float]:
    """Each item scores sum(weight / (k + rank)) over the lists it appears in. Sorted best-first."""
    weights = weights or [1.0] * len(rankings)
    scores: dict[str, float] = {}
    for ranking, weight in zip(rankings, weights, strict=True):
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + weight / (k + rank)
    return dict(sorted(scores.items(), key=lambda kv: kv[1], reverse=True))