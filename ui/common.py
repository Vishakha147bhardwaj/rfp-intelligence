"""Shared helpers: REST API client and small formatting functions."""

import os
from pathlib import Path

import httpx
import streamlit as st

API = os.getenv("RFP_API_URL", "http://127.0.0.1:8000")
ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
RUNS = ROOT / "runs"


def api(method: str, path: str, timeout: float = 120, **kwargs):
    """Call the REST API; show a clear message and stop the page on failure."""
    try:
        response = httpx.request(method, f"{API}{path}", timeout=timeout, **kwargs)
    except httpx.ConnectError:
        st.error(
            f"Cannot reach the API at {API}. Start it with: uv run python main.py serve"
        )
        st.stop()
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        st.error(f"API error {response.status_code}: {detail}")
        st.stop()
    return response.json()


@st.cache_data(ttl=30, show_spinner=False)
def health() -> dict:
    return api("GET", "/health")


@st.cache_data(ttl=30, show_spinner=False)
def bid_ids() -> list[str]:
    return [b["bid_id"] for b in api("GET", "/bids")]


def md(text: str) -> str:
    """Escape '$' so Streamlit doesn't render dollar amounts as LaTeX."""
    return text.replace("$", "\\$")


def as_text(value) -> str:
    if value is None:
        return "Not stated in the documents"
    return "\n".join(f"• {v}" for v in value) if isinstance(value, list) else str(value)


def confidence_tone(confidence: float) -> str:
    return "mint" if confidence >= 0.8 else "peach" if confidence >= 0.5 else "rose"


def first_source(field: dict) -> str | None:
    if not field.get("sources"):
        return None
    s = field["sources"][0]
    return f"{s['file']}, p.{s['page']}"
