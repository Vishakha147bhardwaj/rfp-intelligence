import streamlit as st
from assets import art
from common import bid_ids, health
from theme import feature_card, page_header, stat_grid

page_header(
    "Bid intelligence",
    "RFP",
    "Intelligence",
    "Search bid documents, ask questions with cited answers, extract every key field "
    "and decide which bids to pursue.",
    art("docs"),
)
stat_grid(
    [
        ("Passages indexed", health()["chunks_indexed"]),
        ("Bids", len(bid_ids())),
        ("Fields per bid", 20),
        ("Answers", "Cited"),
    ]
)

st.markdown("#### What you can do")
FEATURES = [  # icon, name, description, page URL path, tone
    ("💬", "Ask", "Plain-English questions, answered with citations.", "ask", "violet"),
    (
        "🔎",
        "Search",
        "Hybrid search: meaning + exact words, reranked.",
        "search",
        "sky",
    ),
    (
        "📋",
        "Extract",
        "20 key fields per bid, validated, with sources.",
        "extract",
        "mint",
    ),
    ("⚖️", "Compare", "Bids side by side, with an AI analysis.", "compare", "peach"),
    (
        "🚦",
        "Go / No-Go",
        "Should we bid? Checked against your profile.",
        "go_no_go",
        "rose",
    ),
    ("📈", "Costs", "Latency, tokens and cost of every run.", "costs", "violet"),
]
for row in range(0, len(FEATURES), 2):
    columns = st.columns(2)
    for column, (icon, name, text, href, tone) in zip(
        columns, FEATURES[row : row + 2], strict=False
    ):
        with column:
            feature_card(icon, name, text, tone, href, delay=row * 60)
