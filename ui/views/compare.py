import streamlit as st
from assets import art
from common import api, bid_ids
from theme import card, empty_state, field_label, page_header

page_header(
    "Compare",
    "Weigh the",
    "bids",
    "Side by side, from the validated extraction, with an AI analysis.",
    art("scales"),
)
bids = bid_ids()

# One selection bar: bid chips on the left, the Compare button on the right.
with st.container(border=True):
    field_label("Select two or more bids")
    left, right = st.columns([3, 1], vertical_alignment="center")
    chosen = (
        left.pills(
            "Bids to compare",
            bids,
            selection_mode="multi",
            default=bids[:2],
            label_visibility="collapsed",
        )
        or []
    )
    clicked = right.button(
        "Compare",
        type="primary",
        icon=":material/compare_arrows:",
        disabled=len(chosen) < 2,
        use_container_width=True,
    )

if clicked:
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
