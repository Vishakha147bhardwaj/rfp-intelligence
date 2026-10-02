"""A chunk: the unit the search engine indexes and cites."""

from datetime import date

from pydantic import BaseModel

from rfp.schemas.documents import DocType


class Chunk(BaseModel):
    chunk_id: str                 # deterministic: same input -> same id (idempotent indexing)
    bid_id: str
    file_name: str
    file_hash: str
    doc_type: DocType
    addendum_number: int | None = None
    doc_date: date | None = None
    page_number: int              # exactly one page per chunk -> exact citations
    chunk_index: int
    section: str | None = None
    is_table: bool = False
    text: str                     # original text; this is what citations show
    context_header: str           # "[Bid: Bid1 | Doc: ... | Page 1 | Section: ...]"
    n_tokens: int

    @property
    def embed_text(self) -> str:
        """What gets embedded and keyword-indexed: header + text."""
        return f"{self.context_header}\n{self.text}"