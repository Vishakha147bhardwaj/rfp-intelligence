import json

import streamlit as st
from assets import art
from common import OUTPUTS, api, as_text, bid_ids, confidence_tone, first_source
from theme import card, empty_state, page_header, stat_grid

page_header(
    "Extraction",
    "The bid",
    "record",
    "20 fields per bid, extracted by agents, reconciled with addendums, validated against the source.",
    art("checklist"),
)
bids = bid_ids()
if not bids:
    empty_state(art("checklist"), "No bids indexed", "Index a bid folder first.")
    st.stop()

bid = st.selectbox("Bid", bids)
if st.button("Run extraction (a few minutes)", use_container_width=True):
    with st.spinner(
        "Agents at work: retrieving, extracting, reconciling, validating..."
    ):
        result = api("POST", "/extract", json={"bid_id": bid}, timeout=1800)
    st.success(f"Done. Trace saved to {result['trace_dir']}")

path = OUTPUTS / f"{bid}.json"
if not path.exists():
    empty_state(art("checklist"), "No extraction yet", "Run it with the button above.")
    st.stop()

record = json.loads(path.read_text())
v = record["validation"]
stat_grid(
    [
        ("Passed", v["passed"]),
        ("Failed", v["failed"]),
        ("Not found", v["not_found"]),
        ("Addendum changes", len(record["addendum_changes"])),
    ]
)

for change in record["addendum_changes"]:
    card(
        f"Changed by Addendum {change['addendum_number'] or ''}: {change['field']}",
        f"Before: {as_text(change['old_value'])}\nAfter:  {as_text(change['new_value'])}",
        chips=[("addendum", "peach")],
        meta=f"{change['source']['file']}, p.{change['source']['page']}",
    )

fields = record["fields"]
if st.toggle("Table view"):
    st.dataframe(
        [
            {
                "Field": n,
                "Value": as_text(f["value"]),
                "Confidence": round(f["confidence"], 2),
                "Source": first_source(f) or "",
            }
            for n, f in fields.items()
        ],
        hide_index=True,
    )
else:
    for i, (name, f) in enumerate(fields.items()):
        chips = [
            (f"{f['confidence']:.0%} confidence", confidence_tone(f["confidence"]))
        ]
        if "Validation failed" in f["notes"]:
            chips.append(("check source", "rose"))
        card(
            name,
            as_text(f["value"]),
            chips=chips,
            meta=first_source(f),
            delay=min(i, 10) * 50,
        )

st.download_button(
    "Download JSON",
    path.read_text(),
    file_name=path.name,
    mime="application/json",
    use_container_width=True,
)
