"""RFP Intelligence web UI: entry point with the top navigation bar.

A thin client of the REST API (start it with: uv run python main.py serve).
Run with: uv run python main.py ui
"""

from pathlib import Path

import streamlit as st
from theme import apply_theme, footer

HERE = Path(__file__).parent

st.set_page_config(page_title="RFP Intelligence", page_icon="✦", layout="centered")
apply_theme()
st.logo(str(HERE / "assets" / "logo.svg"), size="large")

pages = [
    st.Page("views/home.py", title="Home", icon=":material/home:", default=True),
    st.Page("views/ask.py", title="Ask", icon=":material/forum:"),
    st.Page("views/search.py", title="Search", icon=":material/search:"),
    st.Page("views/extract.py", title="Extract", icon=":material/fact_check:"),
    st.Page("views/compare.py", title="Compare", icon=":material/compare_arrows:"),
    st.Page("views/go_no_go.py", title="Go / No-Go", icon=":material/verified:"),
    st.Page("views/costs.py", title="Costs", icon=":material/monitoring:"),
]
st.navigation(pages, position="top").run()
footer()
