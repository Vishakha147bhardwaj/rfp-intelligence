"""Modern pastel theme: glass navbar, animated cards, pill buttons, floating illustrations.

Every dynamic string inserted into custom HTML goes through html.escape.
"""

from html import escape

import streamlit as st

TONES = {  # tone: (text colour, background)
    "violet": ("#2A2F45", "#EEF0F5"),
    "mint": ("#4F6F5F", "#EAF1EC"),
    "peach": ("#7A6A55", "#F3EEE6"),
    "rose": ("#8C4F5C", "#F6ECEE"),
    "sky": ("#4E6378", "#EBF0F4"),
    "gray": ("#6F6B66", "#F2F1EE"),
}
VERDICTS = {"GO": ("mint", "✓"), "NO-GO": ("rose", "✕"), "REVIEW": ("peach", "◇")}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Instrument+Serif:ital@1&display=swap');

:root {
  --bg: #FAF9F6; --ink: #1E2235; --muted: #6F6B66; --line: rgba(30, 34, 53, 0.14);
  --card: rgba(255, 255, 255, 0.8); --violet: #1E2235; --violet-soft: #F1F0EC;
  --shadow: 0 8px 28px rgba(30, 34, 53, 0.08); --shadow-hover: 0 18px 40px rgba(30, 34, 53, 0.16);
}

/* ---------- page + drifting pastel blobs ---------- */
.stApp { background: var(--bg); }
[data-testid="stAppViewContainer"], [data-testid="stMain"] { background: transparent !important; }
[data-testid="stAppViewContainer"] { position: relative; z-index: 1; }
.stApp::before, .stApp::after { content: ""; position: fixed; border-radius: 50%; pointer-events: none;
  z-index: 0; filter: blur(24px); animation: drift 22s ease-in-out infinite alternate; }
.stApp::before { width: 480px; height: 480px; top: -150px; left: -170px;
  background: radial-gradient(circle, rgba(236, 232, 224, 0.9), transparent 70%); }
.stApp::after { width: 540px; height: 540px; bottom: -200px; right: -190px; animation-duration: 28s;
  background: radial-gradient(circle, rgba(226, 230, 238, 0.85), transparent 70%); }
@keyframes drift { from { transform: translate(0, 0) scale(1); } to { transform: translate(70px, 50px) scale(1.12); } }

/* ---------- typography ---------- */
html, body, p, li, label, input, textarea, button, a, .stMarkdown, [data-testid="stCaptionContainer"] {
  font-family: 'Plus Jakarta Sans', system-ui, sans-serif !important; color: var(--ink); }
h1, h2, h3, h4 { font-family: 'Plus Jakarta Sans', system-ui, sans-serif !important; color: var(--ink) !important;
  font-weight: 700 !important; letter-spacing: -0.015em; }

/* ---------- glass top navbar ---------- */
header[data-testid="stHeader"] { background: rgba(255, 255, 255, 0.7) !important;
  backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px); border-bottom: 1px solid var(--line);
  box-shadow: 0 4px 20px rgba(30, 34, 53, 0.05); }
header[data-testid="stHeader"] a, header[data-testid="stHeader"] span { font-weight: 600 !important; }
[data-testid="stDecoration"] { display: none !important; }

/* ---------- mobile-first container ---------- */
.block-container { padding: 4.8rem 1rem 3rem !important; max-width: 980px; }
@media (min-width: 768px) { .block-container { padding: 5.6rem 2rem 4rem !important; } }

/* ---------- animations ---------- */
@keyframes rise { from { opacity: 0; translate: 0 16px; } to { opacity: 1; translate: 0 0; } }
@keyframes bob { 0%, 100% { translate: 0 0; } 50% { translate: 0 -9px; } }
@keyframes pop { 0% { opacity: 0; scale: 0.6; } 60% { scale: 1.07; } 100% { opacity: 1; scale: 1; } }
@keyframes sheen { 0%, 100% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } }

/* ---------- page header ---------- */
.page-head { position: relative; display: flex; flex-direction: column-reverse; gap: 0.4rem;
  padding: 1.4rem 1.4rem 1.2rem; margin-bottom: 1.3rem; border-radius: 26px; border: 1px solid var(--line);
  background: linear-gradient(135deg, rgba(255,255,255,0.94), rgba(250,249,246,0.96) 50%, rgba(243,241,236,0.94));
  box-shadow: var(--shadow); animation: rise 0.6s cubic-bezier(0.2, 0.7, 0.2, 1) both; }
.page-head img { width: 140px; align-self: center; animation: bob 6s ease-in-out infinite; }
.page-head .kicker { font-size: 0.72rem; font-weight: 700; letter-spacing: 0.18em; text-transform: uppercase;
  color: var(--violet); }
.page-head .title { font-size: 1.95rem; font-weight: 800; line-height: 1.1; margin: 0.35rem 0 0.45rem;
  letter-spacing: -0.02em; }
.page-head .title em { font-family: 'Instrument Serif', serif; font-weight: 400; color: var(--violet); }
.page-head .sub { color: var(--muted); font-size: 0.97rem; line-height: 1.55; max-width: 34rem; }
@media (min-width: 768px) {
  .page-head { flex-direction: row; align-items: center; justify-content: space-between; padding: 2rem 2.4rem; }
  .page-head .title { font-size: 2.6rem; }
  .page-head img { width: 185px; }
}

/* ---------- cards ---------- */
.card { background: var(--card); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
  border: 1px solid var(--line); border-radius: 20px; padding: 1rem 1.1rem; margin-bottom: 0.75rem;
  box-shadow: var(--shadow); animation: rise 0.55s cubic-bezier(0.2, 0.7, 0.2, 1) both;
  animation-delay: var(--d, 0ms); transition: transform 0.22s ease, box-shadow 0.22s ease, border-color 0.22s ease; }
.card:hover { transform: translateY(-3px); box-shadow: var(--shadow-hover); border-color: rgba(30, 34, 53, 0.32); }
.card .label { font-size: 0.74rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase;
  color: var(--muted); margin-bottom: 0.4rem; }
.card .body { font-size: 0.95rem; line-height: 1.6; white-space: pre-wrap; word-break: break-word; }
.card .meta { font-size: 0.8rem; color: var(--muted); margin-top: 0.55rem; word-break: break-word; }
.card .chips { margin-top: 0.6rem; }
.chip { display: inline-block; font-size: 0.74rem; font-weight: 600; padding: 0.24rem 0.65rem;
  border-radius: 999px; margin: 0 0.3rem 0.3rem 0; }

/* feature cards on Home */
.feature { display: flex; gap: 0.9rem; align-items: flex-start; }
.feature .ficon { width: 46px; height: 46px; flex: none; display: grid; place-items: center; font-size: 1.35rem;
  border-radius: 15px; transition: transform 0.25s ease; }
.card:hover .ficon { transform: rotate(-6deg) scale(1.08); }
.feature .fname { font-weight: 700; font-size: 1.05rem; margin-bottom: 0.15rem; }
.feature .ftext { color: var(--muted); font-size: 0.9rem; line-height: 1.5; }

/* ---------- stats ---------- */
.stats { display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.75rem; margin-bottom: 1rem; }
@media (min-width: 768px) { .stats { grid-template-columns: repeat(4, 1fr); } }
.stat { background: var(--card); border: 1px solid var(--line); border-radius: 20px; padding: 0.95rem 1.05rem;
  box-shadow: var(--shadow); animation: rise 0.55s ease both; transition: transform 0.2s ease; }
.stat:hover { transform: translateY(-2px); }
.stat:nth-child(2) { animation-delay: 70ms; } .stat:nth-child(3) { animation-delay: 140ms; }
.stat:nth-child(4) { animation-delay: 210ms; }
.stat .value { font-size: 1.6rem; font-weight: 800; color: var(--violet); letter-spacing: -0.02em; }
.stat .name { font-size: 0.8rem; color: var(--muted); font-weight: 600; }

/* ---------- buttons and links ---------- */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button, a[data-testid="stPageLink-NavLink"] {
  border-radius: 999px !important; font-weight: 600 !important; padding: 0.55rem 1.3rem !important;
  border: 1px solid var(--line) !important; background: rgba(255, 255, 255, 0.9) !important;
  transition: transform 0.15s ease, box-shadow 0.2s ease, border-color 0.2s ease !important; }
.stButton > button:hover, .stDownloadButton > button:hover, a[data-testid="stPageLink-NavLink"]:hover {
  transform: translateY(-2px); box-shadow: 0 10px 24px rgba(30, 34, 53, 0.18);
  border-color: rgba(30, 34, 53, 0.4) !important; }
.stButton > button:active { transform: translateY(0) scale(0.98); }
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"] {
  background: linear-gradient(120deg, #3A4060, #1E2235 45%, #4A5170) !important; background-size: 220% 220% !important;
  color: #fff !important; border: none !important; box-shadow: 0 8px 22px rgba(30, 34, 53, 0.32);
  animation: sheen 7s ease infinite; }
[data-testid="stBaseButton-primary"] p, [data-testid="stBaseButton-primaryFormSubmit"] p { color: #fff !important; }
a[data-testid="stPageLink-NavLink"] p { color: var(--violet) !important; font-weight: 600; }

/* ---------- inputs ---------- */
[data-baseweb="input"], [data-baseweb="select"] > div, [data-testid="stChatInput"] > div {
  border-radius: 14px !important; background: rgba(255, 255, 255, 0.9) !important; }

/* ---------- verdict, empty state, Streamlit pieces ---------- */
.verdict { display: inline-flex; align-items: center; gap: 0.55rem; font-size: 1.7rem; font-weight: 800;
  padding: 0.55rem 1.5rem; border-radius: 999px; margin: 0.3rem 0 1rem; box-shadow: var(--shadow);
  animation: pop 0.55s cubic-bezier(0.2, 0.8, 0.2, 1.2) both; }
.empty { text-align: center; padding: 1.6rem 1rem; animation: rise 0.6s ease both; }
.empty img { width: 150px; animation: bob 6s ease-in-out infinite; opacity: 0.95; }
.empty .etitle { font-weight: 700; font-size: 1.05rem; margin-top: 0.4rem; }
.empty .etext { color: var(--muted); font-size: 0.92rem; }
[data-testid="stChatMessage"] { background: var(--card); border: 1px solid var(--line); border-radius: 20px;
  animation: rise 0.45s ease both; }
[data-testid="stExpander"] { background: var(--card); border: 1px solid var(--line) !important; border-radius: 16px; }
[data-testid="stDataFrame"] { border-radius: 14px; overflow: hidden; }
.footer { text-align: center; color: var(--muted); font-size: 0.82rem; margin-top: 2.6rem; }

/* Respect users who prefer less motion */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; }
}

/* royal double frame */
.page-head::after { content: ""; position: absolute; inset: 8px; border: 1px solid rgba(30, 34, 53, 0.07);
  border-radius: 20px; pointer-events: none; }
/* whole feature card is a link */
a.card.feature .ftextwrap, a.card.feature .fname, a.card.feature .ftext { display: block; }
a.card.feature .ftextwrap { flex: 1; min-width: 0; }
a.card.feature { text-decoration: none !important; color: inherit !important; position: relative; }
a.card.feature .farrow { margin-left: auto; align-self: center; font-size: 1.2rem; color: var(--muted);
  transition: translate 0.2s ease, color 0.2s ease; }
a.card.feature:hover .farrow { translate: 5px 0; color: var(--ink); }

/* ---------- search bar: pill box + matching pill button ---------- */
[data-testid="InputInstructions"] { display: none !important; }
[data-testid="stForm"] [data-baseweb="input"] {
  min-height: 50px; border-radius: 999px !important; padding: 0 0.6rem;
  border: 1px solid var(--line) !important; background: #fff !important; box-shadow: var(--shadow); }
[data-testid="stForm"] [data-baseweb="input"]:focus-within { border-color: rgba(30, 34, 53, 0.45) !important; }
[data-testid="stForm"] [data-baseweb="input"] input { font-size: 1rem; padding: 0 0.4rem; }
.stFormSubmitButton > button { height: 50px; min-height: 50px; border-radius: 999px !important;
  padding: 0 1.4rem !important; }
[data-testid="stBaseButton-primaryFormSubmit"] {
  background: linear-gradient(120deg, #3A4060, #1E2235 45%, #4A5170) !important; background-size: 220% 220% !important;
  border: none !important; box-shadow: 0 8px 22px rgba(30, 34, 53, 0.28); animation: sheen 7s ease infinite; }
[data-testid="stBaseButton-primaryFormSubmit"], [data-testid="stBaseButton-primaryFormSubmit"] * {
  color: #fff !important; font-weight: 600 !important; }

/* search button: always navy with bright white text (beats the global p colour) */
.stFormSubmitButton > button {
  background: linear-gradient(120deg, #3A4060, #1E2235 45%, #4A5170) !important; background-size: 220% 220% !important;
  border: none !important; box-shadow: 0 8px 22px rgba(30, 34, 53, 0.28); }
.stFormSubmitButton > button p, .stFormSubmitButton > button span, .stFormSubmitButton > button div,
.stFormSubmitButton > button [data-testid="stMarkdownContainer"] {
  color: #FFFFFF !important; font-weight: 600 !important; }
.stFormSubmitButton > button:hover { box-shadow: 0 10px 26px rgba(30, 34, 53, 0.4); }


/* search bar: rectangular box + matching rectangular button */
.stTextInput [data-testid="stTextInputRootElement"] { height: 46px; min-height: 46px; border-radius: 10px !important; }
.stFormSubmitButton > button { height: 46px !important; min-height: 46px !important; border-radius: 10px !important;
  padding: 0 1.4rem !important; box-shadow: 0 4px 12px rgba(30, 34, 53, 0.18) !important; }

/* chat: even padding, content kept inside the bubble */
[data-testid="stChatMessage"] { padding: 1.1rem 1.4rem !important; gap: 0.9rem; }
[data-testid="stChatMessage"] [data-testid="stChatMessageContent"] { min-width: 0; padding-right: 0.2rem; }
/* sources expander: soft border, no heavy outline, fits inside the bubble */
[data-testid="stChatMessage"] [data-testid="stExpander"] { margin-top: 0.6rem; max-width: 100%; }
[data-testid="stExpander"] details { border: 1px solid var(--line) !important; border-radius: 14px !important;
  background: rgba(250, 249, 246, 0.7); box-shadow: none !important; }
[data-testid="stExpander"] summary { border: none !important; outline: none !important; box-shadow: none !important;
  background: transparent !important; border-radius: 14px; }
[data-testid="stExpander"] summary:focus-visible { box-shadow: 0 0 0 3px rgba(30, 34, 53, 0.12) !important; }
[data-testid="stExpander"] .card { box-shadow: none; margin-bottom: 0.6rem; }


/* chat box at the top of the page: a clean white card */
[data-testid="stChatInput"] { background: #FFFFFF !important; border: 1px solid rgba(30, 34, 53, 0.12) !important;
  border-radius: 14px !important; box-shadow: 0 8px 28px rgba(30, 34, 53, 0.10) !important; margin-bottom: 1rem; }
[data-testid="stChatInput"]:focus-within { border-color: rgba(30, 34, 53, 0.4) !important; }
/* smooth scrolling: no live blur while scrolling, no animated blurred background, no replayed chat animations */
.card, .stat, [data-testid="stChatMessage"] { backdrop-filter: none !important; -webkit-backdrop-filter: none !important; }
.stApp::before, .stApp::after { filter: none !important; animation: none !important; }
[data-testid="stChatMessage"], [data-testid="stChatMessage"] .card { animation: none !important; }

/* chat mode: bottom panel matches the page; content scrolls neatly behind it with a short fade */
[data-testid="stBottom"] > div { background: #FAF9F6 !important; }
[data-testid="stBottom"]::before { content: ""; position: absolute; left: 0; right: 0; top: -32px; height: 32px;
  background: linear-gradient(to top, #FAF9F6, rgba(250, 249, 246, 0)); pointer-events: none; }
[data-testid="stBottomBlockContainer"] { padding-top: 0.8rem !important; padding-bottom: 1.2rem !important; }
</style>
"""


def apply_theme() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def chip(text: str, tone: str = "gray") -> str:
    colour, background = TONES.get(tone, TONES["gray"])
    return f'<span class="chip" style="color:{colour};background:{background}">{escape(str(text))}</span>'


def page_header(
    kicker: str, title: str, accent: str, subtitle: str, art_uri: str
) -> None:
    st.markdown(
        f'<div class="page-head"><div><div class="kicker">{escape(kicker)}</div>'
        f'<div class="title">{escape(title)} <em>{escape(accent)}</em></div>'
        f'<div class="sub">{escape(subtitle)}</div></div><img src="{art_uri}" alt=""/></div>',
        unsafe_allow_html=True,
    )


def card(
    label: str,
    body: str,
    chips: list[tuple[str, str]] | None = None,
    meta: str | None = None,
    delay: int = 0,
) -> None:
    chips_html = "".join(chip(text, tone) for text, tone in chips or [])
    st.markdown(
        f'<div class="card" style="--d:{int(delay)}ms"><div class="label">{escape(label)}</div>'
        f'<div class="body">{escape(body)}</div>'
        + (f'<div class="chips">{chips_html}</div>' if chips_html else "")
        + (f'<div class="meta">{escape(meta)}</div>' if meta else "")
        + "</div>",
        unsafe_allow_html=True,
    )


def feature_card(
    icon: str, name: str, text: str, tone: str, href: str, delay: int = 0
) -> None:
    """A whole-card link to another page (href is the page's URL path, e.g. 'ask').

    Uses <span>s, not <div>s: block elements inside <a> make the HTML parser split the link apart.
    """
    colour, background = TONES.get(tone, TONES["violet"])
    st.markdown(
        f'<a class="card feature" href="{escape(href)}" target="_self" style="--d:{int(delay)}ms">'
        f'<span class="ficon" style="background:{background};color:{colour}">{escape(icon)}</span>'
        f'<span class="ftextwrap"><span class="fname">{escape(name)}</span>'
        f'<span class="ftext">{escape(text)}</span></span>'
        f'<span class="farrow">→</span></a>',
        unsafe_allow_html=True,
    )


def stat_grid(items: list[tuple[str, object]]) -> None:
    cells = "".join(
        f'<div class="stat"><div class="value">{escape(str(v))}</div>'
        f'<div class="name">{escape(n)}</div></div>'
        for n, v in items
    )
    st.markdown(f'<div class="stats">{cells}</div>', unsafe_allow_html=True)


def empty_state(art_uri: str, title: str, text: str) -> None:
    st.markdown(
        f'<div class="empty"><img src="{art_uri}" alt=""/><div class="etitle">{escape(title)}</div>'
        f'<div class="etext">{escape(text)}</div></div>',
        unsafe_allow_html=True,
    )


def verdict(decision: str) -> None:
    tone, symbol = VERDICTS.get(decision, ("gray", "◇"))
    colour, background = TONES[tone]
    st.markdown(
        f'<div class="verdict" style="color:{colour};background:{background}">'
        f"{symbol} {escape(decision)}</div>",
        unsafe_allow_html=True,
    )


def footer() -> None:
    st.markdown(
        '<div class="footer">Every answer is grounded in the bid documents and cites its source.</div>',
        unsafe_allow_html=True,
    )
