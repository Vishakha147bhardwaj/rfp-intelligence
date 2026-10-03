import json

import streamlit as st
from assets import art
from common import RUNS
from theme import empty_state, page_header, stat_grid

page_header(
    "Observability",
    "Runs &",
    "cost",
    "Every run's duration, model calls, tokens and cost.",
    art("chart"),
)
summaries = sorted(
    RUNS.glob("*/summary.json"), key=lambda p: p.stat().st_mtime, reverse=True
)[:50]
runs = [json.loads(p.read_text()) for p in summaries]
if not runs:
    empty_state(art("chart"), "No runs yet", "Ask a question or run an extraction.")
    st.stop()

total = sum(r.get("cost_usd") or 0 for r in runs)
stat_grid(
    [
        ("Runs", len(runs)),
        ("Total cost", f"${total:.3f}"),
        ("LLM calls", sum(r.get("llm_calls", 0) for r in runs)),
        ("Cache hits", sum(1 for r in runs if r.get("cache_hit"))),
    ]
)
st.dataframe(
    [
        {
            "What": r.get("bid_id") or r.get("question", "")[:50],
            "Cached": "⚡" if r.get("cache_hit") else "",
            "Seconds": r.get("duration_s"),
            "LLM calls": r.get("llm_calls", 0),
            "Tokens in/out": f"{r.get('input_tokens', 0):,} / {r.get('output_tokens', 0):,}",
            "Cost (USD)": r.get("cost_usd"),
        }
        for r in runs
    ],
    hide_index=True,
)
