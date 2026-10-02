"""Structured messages exchanged between agents, and the final per-bid output."""

from typing import Literal

from pydantic import BaseModel, Field, computed_field

FieldFormat = Literal["datetime", "date", "text", "list", "contact"]
FieldValueT = str | list[str] | None


class FieldSpec(BaseModel):
    """One field from config/fields.yaml."""

    name: str
    group: str
    format: FieldFormat
    description: str
    hints: str = ""
    queries: list[str] = Field(default_factory=list)
    addendum_sensitive: bool = False
    generated: bool = False
    evidence_k: int | None = None   # override agents.per_field_k for this field
    expand_neighbors: bool = False
    id_patterns: list[str] = Field(default_factory=list)  # regexes for IDs that code copies exactly 

class Evidence(BaseModel):
    """A retrieved passage given to an agent. Agents cite it only by evidence_id."""

    evidence_id: str               # "E1", "E2", ... (unique within one agent call)
    chunk_id: str
    bid_id: str
    file_name: str
    page_number: int
    doc_type: str
    addendum_number: int | None = None
    text: str
    score: float

    @computed_field
    @property
    def citation(self) -> str:
        return f"{self.file_name}, p.{self.page_number}"


class Source(BaseModel):
    """A citation in the final output. Built by code from evidence, never written by the LLM."""

    file: str
    page: int
    chunk_id: str | None = None


class FieldDraft(BaseModel):
    """One field as returned by an extraction agent (this exact shape goes to the LLM)."""

    field: str
    value: FieldValueT = Field(description='The value, or null if not found. "None"/"Not required" only if stated.')
    evidence_ids: list[str] = Field(default_factory=list, description="IDs of the passages that support the value")
    confidence: float = Field(ge=0, le=1, description="0-1, how sure you are the value is correct and complete")
    reasoning: str = Field(description="One or two sentences: where the value came from")


class AddendumChange(BaseModel):
    field: str
    old_value: FieldValueT
    new_value: FieldValueT
    addendum_number: int | None
    source: Source


class FieldValidation(BaseModel):
    field: str
    status: Literal["passed", "failed", "not_found"]
    reasons: list[str] = Field(default_factory=list)


class FieldResult(BaseModel):
    """One field in the final JSON (the format the assignment asks for)."""

    value: FieldValueT
    sources: list[Source] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    notes: str = ""


class ValidationSummary(BaseModel):
    passed: int = 0
    failed: int = 0
    not_found: int = 0


class BidRecord(BaseModel):
    """The final output for one bid: outputs/<bid_id>.json"""

    bid_id: str
    fields: dict[str, FieldResult]
    addendum_changes: list[AddendumChange] = Field(default_factory=list)
    validation: ValidationSummary = Field(default_factory=ValidationSummary)