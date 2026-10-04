import streamlit as st
from assets import art
from common import api, bid_ids
from theme import card, empty_state, page_header

page_header(
    "Compare",
    "Weigh the",
    "bids",
    "Side by side, from the validated extraction, with an AI analysis.",
    art("scales"),
)
bids = bid_ids()
chosen = st.multiselect("Bids", bids, default=bids[:2])
if st.button("Compare", type="primary") and len(chosen) >= 2:
    with st.spinner("Comparing..."):
        report = api("POST", "/compare", json={"bid_ids": chosen}, timeout=300)
    if report.get("analysis"):
        a = report["analysis"]
        card("Summary", a["summary"], chips=[("AI analysis", "violet")])
        for i, d in enumerate(a["differences"]):
            card(d["topic"], d["detail"], chips=[("difference", "peach")], delay=i * 60)
        if a.get("considerations"):
            card(
                "Considerations for a bidder",
                "\n".join(f"• {c}" for c in a["considerations"]),
                chips=[("risk", "rose")],
            )
    st.markdown("#### Field by field")
    for i, row in enumerate(report["table"]):
        card(
            row["field"],
            "\n".join(f"{b}: {row[b]}" for b in chosen),
            delay=min(i, 10) * 40,
        )
else:
    empty_state(art("scales"), "Pick two or more bids", "Then press Compare.")
