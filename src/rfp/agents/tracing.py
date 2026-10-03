"""Trace events: what each agent step did, how long it took, what it cost."""

import json
import time
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import structlog

from rfp.llm.pricing import call_cost

log = structlog.get_logger()


class Step:
    def __init__(self, run_id: str, node: str, detail: dict[str, Any]):
        self.event: dict[str, Any] = {"run_id": run_id, "node": node, **detail,
                                      "llm_calls": [], "error": None}

    def set(self, **values: Any) -> None:
        self.event.update(values)

    def add_usage(self, usage) -> None:
        if usage is not None:
            self.event["llm_calls"].append(usage.model_dump() if hasattr(usage, "model_dump") else dict(usage))


def _cost(calls: list[dict]) -> float | None:
    costs = [call_cost(c.get("model", ""), c.get("input_tokens", 0), c.get("output_tokens", 0),
                       c.get("cache_read_tokens", 0), c.get("cache_write_tokens", 0)) for c in calls]
    known = [c for c in costs if c is not None]
    return round(sum(known), 6) if known else None


@contextmanager
def trace_step(run_id: str, node: str, **detail: Any):
    """Time a graph node and record a structured event (logged + returned into the state)."""
    step = Step(run_id, node, detail)
    start = time.perf_counter()
    try:
        yield step
    finally:
        calls = step.event["llm_calls"]
        step.event["latency_ms"] = int((time.perf_counter() - start) * 1000)
        step.event["input_tokens"] = sum(c.get("input_tokens", 0) for c in calls)
        step.event["output_tokens"] = sum(c.get("output_tokens", 0) for c in calls)
        step.event["cost_usd"] = _cost(calls)
        log.info("agent_step", **{k: v for k, v in step.event.items() if k != "llm_calls"})


def summarize_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Totals plus where the time, tokens and money went (per agent node and per model)."""
    latency, cost = defaultdict(int), defaultdict(float)
    by_model: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for e in events:
        latency[e["node"]] += e.get("latency_ms", 0)
        cost[e["node"]] += e.get("cost_usd") or 0.0
        for c in e.get("llm_calls", []):
            m = by_model[c.get("model", "?")]
            m["calls"] += 1
            for key in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens"):
                m[key] += c.get(key, 0)
    return {
        "steps": len(events),
        "llm_calls": sum(len(e.get("llm_calls", [])) for e in events),
        "input_tokens": sum(e.get("input_tokens", 0) for e in events),
        "output_tokens": sum(e.get("output_tokens", 0) for e in events),
        "cost_usd": round(sum(cost.values()), 4),
        "latency_by_node_ms": dict(latency),
        "cost_by_node_usd": {k: round(v, 4) for k, v in cost.items()},
        "tokens_by_model": {k: dict(v) for k, v in by_model.items()},
        "errors": [e["error"] for e in events if e.get("error")],
    }


def write_trace(run_dir: Path, events: list[dict[str, Any]], meta: dict[str, Any]) -> None:
    """runs/<run_id>/trace.jsonl (one event per line) + summary.json (totals and breakdowns)."""
    run_dir.mkdir(parents=True, exist_ok=True)
    with (run_dir / "trace.jsonl").open("w") as f:
        for event in events:
            f.write(json.dumps(event, default=str) + "\n")
    summary = {**meta, **summarize_events(events)}
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
