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

# A form: the box and a compact button on one line; pressing Enter submits too.
with st.form("search", border=False):
    box, button = st.columns([5, 1], vertical_alignment="center")
    query = box.text_input(
        "Search the bids",
        label_visibility="collapsed",
        placeholder="Search: bid bond requirement, WD22TB4, pre-bid meeting...",
    )
    submitted = button.form_submit_button(
        "Search", type="primary", icon=":material/search:", use_container_width=True
    )
    f1, f2, f3, f4 = st.columns(4)
    bid = f1.selectbox("Bid", ["All", *bid_ids()])
    doc_type = f2.selectbox(
        "Document", ["All", "rfp", "addendum", "bid_page", "specs", "affidavit"]
    )
    mode = f3.selectbox("Mode", ["hybrid_rerank", "hybrid", "dense", "sparse"])
    top_k = f4.number_input("Results", min_value=1, max_value=20, value=5)

if submitted and query:
    params = {"q": query, "top_k": int(top_k), "mode": mode}
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
