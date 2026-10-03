import streamlit as st
from assets import art
from common import api, bid_ids
from theme import card, empty_state, page_header

page_header(
    "Search",
    "Search the",
    "archive",
    "Hybrid search: meaning (dense) and exact words (BM25), fused and reranked.",
    art("docs"),
)
query = st.text_input(
    "Query", placeholder="e.g. bid bond requirement, WD22TB4, pre-bid meeting"
)
c1, c2, c3 = st.columns(3)
bid = c1.selectbox("Bid", ["All", *bid_ids()])
doc_type = c2.selectbox(
    "Document", ["All", "rfp", "addendum", "bid_page", "specs", "affidavit"]
)
mode = c3.selectbox("Mode", ["hybrid_rerank", "hybrid", "dense", "sparse"])
top_k = st.slider("Results", 1, 20, 5)

if st.button("Search", type="primary", use_container_width=True) and query:
    params = {"q": query, "top_k": top_k, "mode": mode}
    if bid != "All":
        params["bid_id"] = bid
    if doc_type != "All":
        params["doc_type"] = doc_type
    results = api("GET", "/search", params=params)["results"]
    if not results:
        empty_state(
            art("docs"), "No results", "Try different words or remove a filter."
        )
    for i, r in enumerate(results):
        card(
            r["citation"],
            r["text"][:700] + ("…" if len(r["text"]) > 700 else ""),
            chips=[
                (f"score {r['score']:.2f}", "violet"),
                (f"dense #{r['dense_rank'] or '-'}", "sky"),
                (f"BM25 #{r['sparse_rank'] or '-'}", "peach"),
            ],
            meta=f"Section: {r['section']}" if r.get("section") else None,
            delay=i * 70,
        )
else:
    empty_state(
        art("docs"),
        "Search the bids",
        "A requirement, a product code like WD22TB4, or a date.",
    )
