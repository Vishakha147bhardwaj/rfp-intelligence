"""Trace events: what each agent step did, how long it took, what it cost."""

import json
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import structlog

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
        log.info("agent_step", **{k: v for k, v in step.event.items() if k != "llm_calls"})


def write_trace(run_dir: Path, events: list[dict[str, Any]], meta: dict[str, Any]) -> None:
    """runs/<run_id>/trace.jsonl (one event per line) + summary.json (totals)."""
    run_dir.mkdir(parents=True, exist_ok=True)
    with (run_dir / "trace.jsonl").open("w") as f:
        for event in events:
            f.write(json.dumps(event, default=str) + "\n")
    summary = {
        **meta,
        "steps": len(events),
        "llm_calls": sum(len(e.get("llm_calls", [])) for e in events),
        "input_tokens": sum(e.get("input_tokens", 0) for e in events),
        "output_tokens": sum(e.get("output_tokens", 0) for e in events),
        "errors": [e["error"] for e in events if e.get("error")],
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str))