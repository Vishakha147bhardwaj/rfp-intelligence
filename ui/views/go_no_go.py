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
c1, c2 = st.columns(2)
bid = c1.selectbox("Bid", bids) if bids else None
as_of = c2.date_input("Evaluate as of", value=date(2024, 6, 1))
if bid and st.button("Evaluate", type="primary"):
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
