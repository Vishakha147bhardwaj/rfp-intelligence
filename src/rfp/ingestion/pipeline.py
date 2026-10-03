"""Ingest a bid folder: detect, parse, clean and tag every file -> ParsedDocuments + report."""

import hashlib
import re
from datetime import date
from pathlib import Path

import structlog
from dateutil import parser as date_parser

from rfp.ingestion.cleaner import clean_pages
from rfp.ingestion.detector import detect_doc_type, detect_file_type
from rfp.ingestion.html_parser import parse_html
from rfp.ingestion.pdf_parser import parse_pdf
from rfp.schemas.documents import FileReport, IngestionReport, ParsedDocument

log = structlog.get_logger()

MONTHS = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)"
DATE_PATTERNS = [
    rf"\b{MONTHS}[a-z]*\.?\s+\d{{1,2}},?\s+\d{{4}}\b",  # July 9, 2024
    r"\b\d{1,2}/\d{1,2}/\d{4}\b",  # 05/29/2024
    rf"\b\d{{1,2}}-{MONTHS}-\d{{4}}\b",  # 26-MAY-2024
]
DATE_KEYWORDS = re.compile(r"\b(issued?|dated?|publication|published)\b", re.IGNORECASE)
NOT_DOC_DATE = re.compile(r"\b(due|deadline|closing|expir\w*|opening)\b", re.IGNORECASE)
DATE_WINDOW = 40  # characters after a keyword to look for its date


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def find_doc_date(text: str) -> date | None:
    """First date right after an issue/publication keyword, unless 'due'/'closing' is nearby."""
    for line in text.splitlines():
        for keyword in DATE_KEYWORDS.finditer(line):
            before = line[
                max(0, keyword.start() - 15) : keyword.start()
            ]  # e.g. "new due " date
            window = line[keyword.end() : keyword.end() + DATE_WINDOW]
            if NOT_DOC_DATE.search(before):
                continue
            matches = [
                m for p in DATE_PATTERNS if (m := re.search(p, window, re.IGNORECASE))
            ]
            if not matches:
                continue
            first = min(matches, key=lambda m: m.start())
            if NOT_DOC_DATE.search(window[: first.start()]):  # e.g. "Date: due 6/10"
                continue
            try:
                return date_parser.parse(first.group(0)).date()
            except (ValueError, OverflowError):
                continue
    return None


def ingest_file(path: Path, bid_id: str) -> tuple[ParsedDocument | None, FileReport]:
    file_type = detect_file_type(path)
    if file_type is None:
        log.info("file_skipped", file=path.name, reason="unsupported type")
        return None, FileReport(
            file_name=path.name, status="skipped", errors=["Unsupported file type"]
        )

    removed: list[str] = []
    if file_type == "pdf":
        pages, errors = parse_pdf(path)
        pages, removed = clean_pages(pages)
    else:
        pages, errors = parse_html(path)

    if not pages:
        log.error("file_failed", file=path.name, errors=errors)
        return None, FileReport(file_name=path.name, status="failed", errors=errors)

    head = "\n".join(p.text for p in pages[:2])
    detection = detect_doc_type(path.name, file_type, head)
    doc = ParsedDocument(
        bid_id=bid_id,
        file_name=path.name,
        file_path=str(path),
        file_hash=file_sha256(path),
        file_type=file_type,
        doc_type=detection.doc_type,
        addendum_number=detection.addendum_number,
        doc_date=find_doc_date(head),
        title=next((h for p in pages for h in p.headings), None),
        pages=pages,
        errors=errors,
    )
    empty = [p.page_number for p in pages if p.is_empty]
    log.info(
        "file_ingested",
        file=path.name,
        doc_type=doc.doc_type.value,
        matched_by=detection.matched_by,
        pages=len(pages),
        empty_pages=len(empty),
    )
    return doc, FileReport(
        file_name=path.name,
        status="partial" if errors or empty else "ok",
        doc_type=doc.doc_type,
        pages=len(pages),
        empty_pages=empty,
        removed_boilerplate=removed,
        errors=errors,
    )


def save_outputs(
    docs: list[ParsedDocument], report: IngestionReport, out_dir: Path
) -> None:
    bid_dir = out_dir / report.bid_id
    bid_dir.mkdir(parents=True, exist_ok=True)
    for doc in docs:
        (bid_dir / f"{Path(doc.file_name).stem}.json").write_text(
            doc.model_dump_json(indent=2)
        )
    (bid_dir / "ingestion_report.json").write_text(report.model_dump_json(indent=2))


def ingest_folder(
    folder: Path, out_dir: Path | None = None
) -> tuple[list[ParsedDocument], IngestionReport]:
    """Ingest every file in a bid folder. The folder name is the bid_id. Never raises per file."""
    bid_id = folder.name
    docs: list[ParsedDocument] = []
    reports: list[FileReport] = []
    files = sorted(
        p for p in folder.iterdir() if p.is_file() and not p.name.startswith(".")
    )

    for path in files:
        try:
            doc, report = ingest_file(path, bid_id)
        except Exception as exc:  # last-resort guard: one bad file never stops the bid
            log.exception("file_crashed", file=path.name)
            doc, report = (
                None,
                FileReport(file_name=path.name, status="failed", errors=[str(exc)]),
            )
        reports.append(report)
        if doc:
            docs.append(doc)

    report = IngestionReport(bid_id=bid_id, files=reports)
    if out_dir:
        save_outputs(docs, report, out_dir)
    return docs, report


def load_processed(bid_dir: Path) -> list[ParsedDocument]:
    """Load ParsedDocuments saved by a previous ingest run."""
    return [
        ParsedDocument.model_validate_json(p.read_text())
        for p in sorted(bid_dir.glob("*.json"))
        if p.name != "ingestion_report.json"
    ]
