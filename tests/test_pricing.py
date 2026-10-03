from rfp.agents.tracing import summarize_events
from rfp.llm.pricing import call_cost
from rfp.settings import ModelPrice

PRICES = {"m": ModelPrice(input_per_mtok=1.0, output_per_mtok=5.0)}


def test_cost_of_input_and_output_tokens():
    assert call_cost("m", 1_000_000, 200_000, prices=PRICES) == 1.0 + 1.0


def test_cache_tokens_use_default_multipliers():
    # 1M cache reads at 0.1x and 1M cache writes at 1.25x of the $1 input price
    assert call_cost("m", cache_read_tokens=1_000_000, cache_write_tokens=1_000_000, prices=PRICES) == 0.1 + 1.25


def test_unknown_model_has_no_cost():
    assert call_cost("unknown", 1000, 1000, prices=PRICES) is None


def test_summary_breaks_down_latency_and_cost_by_node():
    events = [
        {"node": "extract", "latency_ms": 100, "cost_usd": 0.01, "input_tokens": 10, "output_tokens": 1,
         "llm_calls": [{"model": "m", "input_tokens": 10, "output_tokens": 1}]},
        {"node": "extract", "latency_ms": 50, "cost_usd": 0.02, "input_tokens": 0, "output_tokens": 0,
         "llm_calls": []},
        {"node": "validate", "latency_ms": 30, "cost_usd": None, "input_tokens": 0, "output_tokens": 0,
         "llm_calls": [], "error": "boom"},
    ]
    s = summarize_events(events)
    assert s["latency_by_node_ms"] == {"extract": 150, "validate": 30}
    assert s["cost_by_node_usd"] == {"extract": 0.03, "validate": 0.0}
    assert s["cost_usd"] == 0.03 and s["errors"] == ["boom"]
    assert s["tokens_by_model"]["m"]["calls"] == 1
