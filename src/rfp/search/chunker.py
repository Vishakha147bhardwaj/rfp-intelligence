"""Split ParsedDocuments into section-aware, page-bounded chunks with context headers."""

import re
import uuid
from pathlib import Path

import tiktoken

from rfp.schemas.chunks import Chunk
from rfp.schemas.documents import Page, ParsedDocument, Table
from rfp.settings import ChunkingConfig, get_settings

_ENCODER = tiktoken.get_encoding("cl100k_base")

NUMBERED_HEADING = re.compile(r"^\d+(\.\d+)*\.?\s+[A-Z][^.]{2,70}$")  # "1.2 Terms"
MD_HEADING = re.compile(r"^#{1,3}\s+(.+)$")  # "## Dates" (HTML)
LEADING_CAPS = re.compile(
    r"^([A-Z][A-Z0-9 ,&()/'\-]{6,80}?)\s+(?=[A-Z][a-z])"
)  # "PURPOSE OF ... This"
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9•(])")
SECTION_WORD = re.compile(
    r"^(section|article|part|attachment|exhibit)\s+([0-9]+|[IVX]+)\b.{0,80}$",
    re.IGNORECASE,
)  # "Section 2 – Contact"
COLUMN_SEP = "   "  # three spaces = column break from the PDF parser


def count_tokens(text: str) -> int:
    return len(_ENCODER.encode(text))


# ---------- section detection ----------


def detect_heading(line: str, known: set[str]) -> str | None:
    """Return the section title if this line starts a section, else None."""
    if line in known:
        return line
    if match := MD_HEADING.match(line):
        return match.group(1).strip()
    if COLUMN_SEP in line:  # a table row is never a heading
        return None
    if SECTION_WORD.match(line) and not line.endswith("."):
        return line
    if (
        NUMBERED_HEADING.match(line) and ":" not in line
    ):  # "1.2 Terms", not "16 GB: ..."
        return line
    words = line.split()
    if (
        line.isupper()
        and 2 <= len(words) <= 10
        and len(line) <= 80
        and not line.endswith((".", ",", ";"))
        and sum(c.isalpha() for c in line) >= 4
    ):
        return line
    if match := LEADING_CAPS.match(line):  # heading glued to its paragraph
        candidate = match.group(1).strip()
        if len(candidate.split()) >= 3 and "," not in candidate:  # not "NTSC, FHD"
            return candidate
    return None


def _page_units(
    page: Page, known: set[str], section: str | None
) -> tuple[list[tuple], str | None]:
    """Split a page into (section, paragraph) units. Returns the section still open at page end."""
    units: list[tuple[str | None, str]] = []
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            units.append((section, "\n".join(buffer)))
            buffer.clear()

    for raw in page.text.splitlines():
        line = raw.strip()
        if not line:
            flush()
            continue
        heading = detect_heading(line, known)
        if heading:
            flush()
            section = heading
        buffer.append(
            line
        )  # the heading line stays in the text too - it helps retrieval
    flush()
    return units, section


# ---------- size control ----------


def _split_long(text: str, limit: int) -> list[str]:
    """Split text over `limit` tokens: by lines, then sentences, then raw tokens as last resort."""
    if count_tokens(text) <= limit:
        return [text]
    units: list[tuple[str, str]] = []  # (piece, separator before it)
    for line in text.split("\n"):
        if count_tokens(line) <= limit:
            units.append((line, "\n"))
            continue
        for sentence in SENTENCE_SPLIT.split(line):
            if count_tokens(sentence) <= limit:
                units.append((sentence, " "))
            else:
                tokens = _ENCODER.encode(sentence)
                units += [
                    (_ENCODER.decode(tokens[i : i + limit]), " ")
                    for i in range(0, len(tokens), limit)
                ]

    pieces, current = [], ""
    for piece, sep in units:
        candidate = current + sep + piece if current else piece
        if current and count_tokens(candidate) > limit:
            pieces.append(current)
            current = piece
        else:
            current = candidate
    if current:
        pieces.append(current)
    return pieces


def _overlap_tail(paragraphs: list[str], limit: int) -> str | None:
    """Last sentences of the previous chunk, up to `limit` tokens."""
    sentences = SENTENCE_SPLIT.split(paragraphs[-1])
    tail: list[str] = []
    for sentence in reversed(sentences):
        if count_tokens(" ".join([sentence, *tail])) > limit:
            break
        tail.insert(0, sentence)
    return " ".join(tail) if tail else None


def _assemble(units: list[tuple], cfg: ChunkingConfig) -> list[tuple[str | None, str]]:
    """Pack one page's units into (section, text) chunks."""
    chunks: list[tuple[str | None, str]] = []
    current: list[str] = []
    current_section: str | None = None
    current_tokens = 0

    for section, paragraph in units:
        for piece in _split_long(paragraph, cfg.target_tokens):
            n = count_tokens(piece)
            new_section = section != current_section
            too_big = current_tokens + n > cfg.target_tokens
            section_break = new_section and current_tokens >= cfg.min_tokens
            if current and (section_break or too_big):
                tail = (
                    None if new_section else _overlap_tail(current, cfg.overlap_tokens)
                )
                chunks.append((current_section, "\n\n".join(current)))
                current, current_tokens = [], 0
                if tail:
                    current, current_tokens = [tail], count_tokens(tail)
            if not current:
                current_section = section
            current.append(piece)
            current_tokens += n

    if current:
        chunks.append((current_section, "\n\n".join(current)))
    return chunks


def _table_pieces(table: Table, limit: int) -> list[str]:
    """Split a big markdown table by rows, repeating the header row in every piece."""
    if count_tokens(table.markdown) <= limit:
        return [table.markdown]
    lines = table.markdown.split("\n")
    header, rows = lines[:2], lines[2:]
    pieces, current = [], []
    for row in rows:
        if current and count_tokens("\n".join([*header, *current, row])) > limit:
            pieces.append("\n".join([*header, *current]))
            current = []
        current.append(row)
    if current:
        pieces.append("\n".join([*header, *current]))
    return pieces


# ---------- public ----------


def context_header(doc: ParsedDocument, page_number: int, section: str | None) -> str:
    kind = doc.doc_type.value.replace("_", " ")
    if doc.addendum_number:
        kind += f" #{doc.addendum_number}"
    name = Path(doc.file_name).stem.replace("_", " ")
    parts = [f"Bid: {doc.bid_id}", f"Doc: {name} ({kind})", f"Page {page_number}"]
    if section:
        parts.append(f"Section: {section}")
    return "[" + " | ".join(parts) + "]"


def chunk_document(
    doc: ParsedDocument, cfg: ChunkingConfig | None = None
) -> list[Chunk]:
    cfg = cfg or get_settings().chunking
    known = {h.strip() for page in doc.pages for h in page.headings}
    chunks: list[Chunk] = []
    section: str | None = None  # sections carry over page breaks

    for page in doc.pages:
        if page.is_empty:
            continue
        units, end_section = _page_units(page, known, section)
        pieces = [(sec, text, False) for sec, text in _assemble(units, cfg)]
        pieces += [
            (end_section, text, True)
            for table in page.tables
            for text in _table_pieces(table, cfg.max_tokens)
        ]
        section = end_section

        for sec, text, is_table in pieces:
            index = len(chunks)
            chunks.append(
                Chunk(
                    chunk_id=str(
                        uuid.uuid5(
                            uuid.NAMESPACE_URL,
                            f"{doc.bid_id}/{doc.file_name}/{page.page_number}/{index}",
                        )
                    ),
                    bid_id=doc.bid_id,
                    file_name=doc.file_name,
                    file_hash=doc.file_hash,
                    doc_type=doc.doc_type,
                    addendum_number=doc.addendum_number,
                    doc_date=doc.doc_date,
                    page_number=page.page_number,
                    chunk_index=index,
                    section=sec,
                    is_table=is_table,
                    text=text,
                    context_header=context_header(doc, page.page_number, sec),
                    n_tokens=count_tokens(text),
                )
            )
    return chunks
