"""Parse a PDF into pages: text, detected headings and tables (as markdown)."""

import re
from collections import Counter
from pathlib import Path

import pdfplumber
import pymupdf
import structlog

from rfp.schemas.documents import Page, Table

log = structlog.get_logger()

BOLD_FLAG = 16          # PyMuPDF span flag bit for bold text
LINE_TOLERANCE = 5.0    # points: words whose vertical centres are this close share a line
COLUMN_GAP = 15.0       # points: a horizontal gap wider than this separates table columns
LAYOUT_CELL_CHARS = 150 # avg cell length above which a 2-column table is "layout", not data
PAGE_LABEL = re.compile(r"^page\s+\d+", re.IGNORECASE)
URL_TAIL = re.compile(r"(@|https?://|www\.)\S*$")  # text currently ends inside an email/URL
LIST_START = re.compile(r"^(\d+[.)]|[•▪\-–])\s")  # next line begins a new list item
FORM_EMPTY_RATIO = 0.4  # tables with at least this share of empty cells are forms, not data

# ---------- tables ----------

def _join_cell_lines(cell: str | None) -> str:
    """Join a cell's wrapped lines with spaces, but never split an email or URL."""
    if not cell:
        return ""
    parts = [p.strip() for p in cell.split("\n") if p.strip()]
    if not parts:
        return ""
    out = parts[0]
    for part in parts[1:]:
        glue = URL_TAIL.search(out) and not LIST_START.match(part)
        out += part if glue else " " + part
    return out


def _normalise_rows(rows: list[list[str | None]]) -> list[list[str]]:
    """Join cell lines, drop empty rows, pad short rows, drop columns empty in every row."""
    clean = [[_join_cell_lines(cell) for cell in row] for row in rows]
    clean = [row for row in clean if any(row)]
    if not clean:
        return []
    width = max(len(row) for row in clean)
    clean = [row + [""] * (width - len(row)) for row in clean]
    keep = [i for i in range(width) if any(row[i] for row in clean)]
    return [[row[i] for i in keep] for row in clean]


def _is_layout_table(rows: list[list[str]]) -> bool:
    """True if the 'table' is boxed prose or a sparse form, not real tabular data."""
    n_cols = len(rows[0])
    cells = [c for row in rows for c in row]
    filled = [c for c in cells if c]
    avg_len = sum(len(c) for c in filled) / len(filled)
    empty_ratio = 1 - len(filled) / len(cells)
    return (
        n_cols == 1
        or (n_cols == 2 and avg_len > LAYOUT_CELL_CHARS)
        or empty_ratio >= FORM_EMPTY_RATIO
    )


def _rows_to_text(rows: list[list[str]]) -> str:
    """Render a layout/form table as text: 'label: value', or cells joined with ' | '."""
    paragraphs = []
    for row in rows:
        cells = [c for c in row if c]
        if len(cells) == 2 and len(cells[0]) < 60:
            sep = " " if cells[0].endswith(":") else ": "
            paragraphs.append(cells[0] + sep + cells[1])
        else:
            paragraphs.append(" | ".join(cells))
    return "\n\n".join(paragraphs)


def rows_to_markdown(rows: list[list[str]]) -> str:
    """Render a data table as markdown. First row is the header."""
    escaped = [[c.replace("|", "\\|") for c in row] for row in rows]
    width = len(escaped[0])
    header, body = escaped[0], escaped[1:]
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * width]
    lines += ["| " + " | ".join(row) + " |" for row in body]
    return "\n".join(lines)


def _extract_tables(plumber_page, page_number: int) -> tuple[list[Table], list[tuple], list[str]]:
    """Return (data tables, bounding boxes of everything captured, layout-table texts)."""
    tables, boxes, layout_texts = [], [], []
    for found in plumber_page.find_tables():
        rows = _normalise_rows(found.extract())
        if not rows:
            continue
        boxes.append(found.bbox)  # captured either way, so skip it in the page text
        if _is_layout_table(rows) or len(rows) < 2:
            layout_texts.append(_rows_to_text(rows))
        else:
            tables.append(
                Table(
                    page_number=page_number,
                    markdown=rows_to_markdown(rows),
                    n_rows=len(rows),
                    n_cols=len(rows[0]),
                )
            )
    return tables, boxes, layout_texts


# ---------- headings ----------

def _body_font_size(doc) -> float:
    """Most common font size in the document, weighted by characters = normal body text."""
    sizes: Counter = Counter()
    for page in doc:
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    sizes[round(span["size"], 1)] += len(span["text"].strip())
    return sizes.most_common(1)[0][0] if sizes else 10.0


def _center_inside(bbox, boxes) -> bool:
    cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    return any(b[0] <= cx <= b[2] and b[1] <= cy <= b[3] for b in boxes)


def _is_heading(spans: list[dict], text: str, body_size: float) -> bool:
    words = text.split()
    if not (3 <= len(text) <= 80) or len(words) > 10:
        return False
    if PAGE_LABEL.match(text):
        return False
    compact = text.replace(" ", "")
    if sum(c.isalpha() for c in compact) / len(compact) < 0.6:  # e.g. "210-BLYZ"
        return False

    visible = [s for s in spans if s["text"].strip()]
    size = max(s["size"] for s in visible)
    bold = all(s["flags"] & BOLD_FLAG or "bold" in s["font"].lower() for s in visible)
    ends_like_sentence = text.endswith((".", ",", ";"))

    if size >= body_size * 1.15:
        return True
    if bold and len(words) >= 2 and not ends_like_sentence:
        return True
    if text.isupper() and 2 <= len(words) <= 8 and not ends_like_sentence:
        return True
    return False


def _page_headings(page, table_boxes, body_size: float) -> list[str]:
    headings = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:  # 0 = text block, 1 = image block
            continue
        for line in block["lines"]:
            if _center_inside(line["bbox"], table_boxes):
                continue
            text = "".join(span["text"] for span in line["spans"]).strip()
            if text and _is_heading(line["spans"], text, body_size):
                headings.append(text)
    return headings


# ---------- text (row-by-row reconstruction) ----------

def _words_to_lines(words: list[tuple]) -> list[dict]:
    """Group words into visual lines by their vertical centre."""
    words = sorted(words, key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    lines: list[dict] = []
    for w in words:
        y = (w[1] + w[3]) / 2
        if lines and abs(y - lines[-1]["y"]) <= LINE_TOLERANCE:
            lines[-1]["words"].append(w)
        else:
            lines.append({"y": y, "words": [w]})
    return lines


def _line_text(words: list[tuple]) -> str:
    """Join a line's words left to right; wide gaps become 3 spaces (column break)."""
    words = sorted(words, key=lambda w: w[0])
    parts = [words[0][4]]
    for prev, cur in zip(words, words[1:]):
        parts.append("   " if cur[0] - prev[2] > COLUMN_GAP else " ")
        parts.append(cur[4])
    return "".join(parts)


def _page_text(page, table_boxes) -> str:
    """Rebuild page text row by row so borderless table rows stay together."""
    words = [w for w in page.get_text("words") if not _center_inside(w[:4], table_boxes)]
    if not words:
        return ""
    lines = _words_to_lines(words)
    heights = sorted(l["words"][0][3] - l["words"][0][1] for l in lines)
    line_height = heights[len(heights) // 2]  # median line height

    out: list[str] = []
    prev_y = None
    for line in lines:
        if prev_y is not None and line["y"] - prev_y > line_height * 1.8:
            out.append("")  # big vertical gap = new paragraph
        out.append(_line_text(line["words"]))
        prev_y = line["y"]
    return "\n".join(out)


# ---------- public entry point ----------

def parse_pdf(path: Path) -> tuple[list[Page], list[str]]:
    """Return (pages, errors). Never raises: problems are recorded in errors."""
    errors: list[str] = []
    try:
        doc = pymupdf.open(path)
        plumber = pdfplumber.open(path)
    except Exception as exc:  # corrupt / unreadable file
        log.error("pdf_open_failed", file=path.name, error=str(exc))
        return [], [f"Could not open PDF: {exc}"]

    pages: list[Page] = []
    with doc, plumber:
        if doc.needs_pass:
            log.error("pdf_encrypted", file=path.name)
            return [], ["PDF is password-protected"]

        body_size = _body_font_size(doc)
        for index, page in enumerate(doc):
            number = index + 1
            try:
                tables, boxes, layout_texts = _extract_tables(plumber.pages[index], number)
            except Exception as exc:
                tables, boxes, layout_texts = [], [], []
                errors.append(f"page {number}: table extraction failed: {exc}")

            try:
                text = _page_text(page, boxes)
                headings = _page_headings(page, boxes, body_size)
                if layout_texts:
                    text = "\n\n".join([text, *layout_texts]).strip()
            except Exception as exc:
                text, headings = "", []
                errors.append(f"page {number}: text extraction failed: {exc}")

            is_empty = not text.strip() and not tables
            if is_empty:
                log.warning("empty_page", file=path.name, page=number)  # OCR candidate later

            pages.append(
                Page(page_number=number, text=text, tables=tables,
                     headings=headings, is_empty=is_empty)
            )
    return pages, errors