"""Data models for parsed bid documents (output of the ingestion stage)."""

from datetime import date
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class DocType(str, Enum):
    """What role a file plays in a bid. Drives metadata filtering in search."""

    BID_PAGE = "bid_page"  # portal web page (HTML)
    RFP = "rfp"  # main solicitation document
    ADDENDUM = "addendum"  # changes to the RFP, numbered
    SPECS = "specs"  # product specification sheet
    AFFIDAVIT = "affidavit"  # forms the bidder must sign
    OTHER = "other"  # anything we can't classify


class Table(BaseModel):
    """A table extracted from a page, stored as markdown so the LLM can read it."""

    page_number: int
    markdown: str
    n_rows: int
    n_cols: int


class Page(BaseModel):
    """One page of a document (an HTML file counts as a single page)."""

    page_number: int  # 1-based, used in citations
    text: str  # cleaned text, tables removed
    tables: list[Table] = Field(default_factory=list)
    headings: list[str] = Field(default_factory=list)  # detected section titles
    ocr_used: bool = False
    is_empty: bool = False


class ParsedDocument(BaseModel):
    """One input file after parsing, with all metadata attached."""

    bid_id: str  # folder name, e.g. "Bid1"
    file_name: str
    file_path: str
    file_hash: str  # sha256, for incremental indexing
    file_type: Literal["pdf", "html"]
    doc_type: DocType
    addendum_number: int | None = None
    doc_date: date | None = None
    title: str | None = None
    pages: list[Page]
    errors: list[str] = Field(default_factory=list)  # non-fatal problems, logged

    @property
    def page_count(self) -> int:
        return len(self.pages)


class FileReport(BaseModel):
    """What happened to one input file during ingestion."""

    file_name: str
    status: Literal["ok", "partial", "failed", "skipped"]
    doc_type: DocType | None = None
    pages: int = 0
    empty_pages: list[int] = Field(default_factory=list)
    removed_boilerplate: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class IngestionReport(BaseModel):
    """Summary of ingesting one bid folder."""

    bid_id: str
    files: list[FileReport]

    @property
    def ok(self) -> bool:
        return all(f.status in ("ok", "partial", "skipped") for f in self.files)
