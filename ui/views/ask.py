import streamlit as st
from assets import art
from common import api, md
from theme import card, chip, empty_state, page_header


def render_answer(answer: dict) -> None:
    st.markdown(md(answer["answer"]))
    if answer.get("cached"):
        st.markdown(
            chip("⚡ from semantic cache - no LLM calls", "mint"),
            unsafe_allow_html=True,
        )
    if answer.get("citations"):
        with st.expander(f"Sources ({len(answer['citations'])})"):
            for i, c in enumerate(answer["citations"]):
                card(
                    f"[{c['n']}] {c['file']}, p.{c['page']}",
                    c["snippet"],
                    chips=[(c["bid_id"], "violet")],
                    delay=i * 60,
                )


page_header(
    "Ask",
    "Ask the",
    "bids",
    "Questions in plain English. Every answer cites the page it came from.",
    art("chat"),
)
st.session_state.setdefault("chat", [])
if not st.session_state.chat:
    empty_state(
        art("chat"),
        "Start a conversation",
        "Try: What changed in Addendum 2? · Which affidavits are required for the Dell bid?",
    )
for turn in st.session_state.chat:
    with st.chat_message("user"):
        st.write(turn["question"])
    with st.chat_message("assistant", avatar="✦"):
        render_answer(turn["answer"])
question = st.chat_input("Ask about deadlines, requirements, products...")
if question:
    with st.chat_message("user"):
        st.write(question)
    with (
        st.chat_message("assistant", avatar="✦"),
        st.spinner("Reading the documents..."),
    ):
        answer = api("POST", "/ask", json={"question": question}, timeout=300)
        render_answer(answer)
    st.session_state.chat.append({"question": question, "answer": answer})
