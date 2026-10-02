"""Clean parsed pages: drop repeating headers/footers and page labels, fix wrapped lines."""

import math
import re
import unicodedata
from collections import Counter

from rfp.schemas.documents import Page

PAGE_LABEL_LINE = re.compile(r"^(page\s*)?\d+(\s*(of|/|\|)\s*\d+)?$", re.IGNORECASE)
HYPHEN_BREAK = re.compile(r"(\w)-\n(\w)")
LIST_START = re.compile(r"^(\d+[.)]|[•▪\-–])\s")
SENTENCE_END = (".", ":", ";", "!", "?")
COLUMN_SEP = "   "            # three spaces = column break from the PDF parser
EDGE_LINES = 3                # how many lines at the top/bottom of a page to inspect
MAX_BOILERPLATE_LEN = 120     # long lines are content, never headers/footers


def _norm(line: str) -> str:
    """Normalise a line for comparison: lowercase, digits -> '#', single spaces."""
    return re.sub(r"\s+", " ", re.sub(r"\d+", "#", line.lower())).strip()


def _edge_lines(text: str) -> list[str]:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return lines[:EDGE_LINES] + lines[-EDGE_LINES:]


def find_boilerplate(pages: list[Page], min_ratio: float = 0.5) -> set[str]:
    """Normalised lines that appear at the top/bottom of at least min_ratio of pages."""
    if len(pages) < 2:
        return set()
    counts: Counter = Counter()
    for page in pages:
        counts.update({_norm(l) for l in _edge_lines(page.text) if len(l) <= MAX_BOILERPLATE_LEN})
    threshold = max(2, math.ceil(len(pages) * min_ratio))
    return {line for line, n in counts.items() if n >= threshold}


def _join_wrapped_lines(text: str) -> str:
    out: list[str] = []
    for line in text.split("\n"):
        prev = out[-1] if out else ""
        if (
            prev
            and line
            and not prev.endswith(SENTENCE_END)
            and COLUMN_SEP not in prev
            and COLUMN_SEP not in line
            and line[0].islower()
            and not LIST_START.match(line)
        ):
            out[-1] = prev + " " + line
        else:
            out.append(line)
    return "\n".join(out)


def clean_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).replace("\u00a0", " ")
    text = HYPHEN_BREAK.sub(r"\1-\2", text)  
    text = re.sub(r"[ \t]*•[ \t]*", "\n• ", text)            # one bullet per line               # "pre-\nproposal" -> "pre-proposal"
    text = "\n".join(line.rstrip() for line in text.splitlines())
    text = _join_wrapped_lines(text)
    text = re.sub(r" {4,}", COLUMN_SEP, text)               # keep column breaks at 3 spaces
    text = re.sub(r"\n{3,}", "\n\n", text)                  # at most one blank line
    return text.strip()


def clean_pages(pages: list[Page]) -> tuple[list[Page], list[str]]:
    """Return (cleaned pages, boilerplate lines that were removed)."""
    boilerplate = find_boilerplate(pages)
    cleaned = []
    for page in pages:
        kept = [
            line for line in page.text.splitlines()
            if _norm(line) not in boilerplate and not PAGE_LABEL_LINE.match(line.strip())
        ]
        text = clean_text("\n".join(kept))
        headings = [h for h in page.headings if _norm(h) not in boilerplate]
        cleaned.append(
            page.model_copy(update={
                "text": text,
                "headings": headings,
                "is_empty": not text and not page.tables,
            })
        )
    return cleaned, sorted(boilerplate)