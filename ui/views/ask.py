import streamlit as st
from assets import art
from common import api, md
from theme import card, chip, empty_state, page_header

USER, BOT = ":material/person:", ":material/auto_awesome:"
PLACEHOLDER = "Ask about deadlines, requirements, products..."


def render_answer(answer: dict) -> None:
    st.markdown(md(answer["answer"]))
    if answer.get("cached"):
        st.markdown(
            chip("⚡ from semantic cache - no LLM calls", "mint"),
            unsafe_allow_html=True,
        )
    if answer.get("citations"):
        with st.expander(f"Sources ({len(answer['citations'])})"):
            for c in answer["citations"]:
                card(
                    f"[{c['n']}] {c['file']}, p.{c['page']}",
                    c["snippet"],
                    chips=[(c["bid_id"], "violet")],
                )


def ask(question: str) -> None:
    """Show the question, fetch the cited answer, and add both to the conversation."""
    with st.chat_message("user", avatar=USER):
        st.write(question)
    with (
        st.chat_message("assistant", avatar=BOT),
        st.spinner("Reading the documents..."),
    ):
        answer = api("POST", "/ask", json={"question": question}, timeout=300)
        render_answer(answer)
    st.session_state.chat.append({"question": question, "answer": answer})


st.session_state.setdefault("chat", [])
chat = st.session_state.chat

if not chat:
    # Landing screen: header, the box near the top (inline, inside a container), suggestions under it.
    page_header(
        "Ask",
        "Ask the",
        "bids",
        "Questions in plain English. Every answer cites the page it came from.",
        art("chat"),
    )
    with st.container():
        first = st.chat_input(PLACEHOLDER, key="first_question")
    if first:
        ask(first)
        st.rerun()  # switch to chat mode: the box moves to the bottom
    empty_state(
        art("chat"),
        "Start a conversation",
        "Try: What changed in Addendum 2? · Which affidavits are required for the Dell bid?",
    )
else:
    # Chat mode: conversation oldest to newest, box pinned to the bottom.
    title, action = st.columns([4, 1], vertical_alignment="center")
    title.markdown("#### Ask the bids")
    if action.button("New chat", icon=":material/add:"):
        chat.clear()
        st.rerun()
    for turn in chat:
        with st.chat_message("user", avatar=USER):
            st.write(turn["question"])
        with st.chat_message("assistant", avatar=BOT):
            render_answer(turn["answer"])
    follow_up = st.chat_input(PLACEHOLDER, key="follow_up")
    if follow_up:
        ask(follow_up)
