"""Estimate the USD cost of LLM calls from token counts and configured prices."""

from rfp.settings import ModelPrice, get_settings

CACHE_READ_MULTIPLIER = 0.1     # used when no explicit cache price is configured
CACHE_WRITE_MULTIPLIER = 1.25


def call_cost(
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    prices: dict[str, ModelPrice] | None = None,
) -> float | None:
    """USD cost of one call, or None if the model has no configured price.

    Anthropic reports cached tokens separately from input_tokens, so nothing is counted twice.
    """
    prices = get_settings().llm.prices if prices is None else prices
    price = prices.get(model)
    if price is None:
        return None
    read = (price.cache_read_per_mtok if price.cache_read_per_mtok is not None
            else price.input_per_mtok * CACHE_READ_MULTIPLIER)
    write = (price.cache_write_per_mtok if price.cache_write_per_mtok is not None
             else price.input_per_mtok * CACHE_WRITE_MULTIPLIER)
    total = (input_tokens * price.input_per_mtok + output_tokens * price.output_per_mtok
             + cache_read_tokens * read + cache_write_tokens * write)
    return total / 1_000_000
