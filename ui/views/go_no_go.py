from datetime import date

import streamlit as st
from assets import art
from common import api, bid_ids
from theme import card, empty_state, page_header, verdict

page_header(
    "Decision",
    "Go /",
    "No-Go",
    "Each bid checked against your company profile (config/capabilities.yaml).",
    art("checklist"),
)
bids = bid_ids()

# One selection bar: bid chips, the date, and the Evaluate button on one line.
with st.container(border=True):
    pick, when, go = st.columns([2, 2, 1], vertical_alignment="bottom")
    with pick:
        st.caption("Bid")
        bid = st.pills(
            "Bid",
            bids,
            selection_mode="single",
            label_visibility="collapsed",
            default="Bid2" if "Bid2" in bids else (bids[0] if bids else None),
        )
    with when:
        st.caption("Evaluate as of")
        as_of = st.date_input(
            "Evaluate as of",
            value=date(2024, 6, 1),
            format="YYYY-MM-DD",
            label_visibility="collapsed",
        )
    clicked = go.button(
        "Evaluate",
        type="primary",
        icon=":material/verified:",
        disabled=not bid,
        use_container_width=True,
    )

if clicked:
    with st.spinner("Checking every criterion..."):
        report = api(
            "POST",
            "/go-no-go",
            json={"bid_id": bid, "as_of": as_of.isoformat()},
            timeout=300,
        )
    verdict(report["decision"])
    if report.get("summary"):
        card("Why", report["summary"])
    tone = {"pass": "mint", "fail": "rose", "unknown": "peach"}
    for i, c in enumerate(report["criteria"]):
        chips = [(c["status"], tone[c["status"]])] + (
            [("must-have", "violet")] if c["must_have"] else []
        )
        card(c["id"].replace("_", " "), c["reason"], chips=chips, delay=i * 60)
else:
    empty_state(
        art("checklist"),
        "Pick a bid to evaluate",
        "The deadline is checked by code, the rest by the AI.",
    )
