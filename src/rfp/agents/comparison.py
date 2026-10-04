"""Bid comparison agent: side-by-side table of validated fields + an LLM-written comparison.

The table is built by code from outputs/<bid>.json (every cell cites its first source).
The LLM only sees those values - it cannot add facts the validated extraction did not find.
"""

import json
from pathlib import Path

from pydantic import BaseModel, Field

from rfp.agents.registry import load_registry
from rfp.llm.client import LLMClient, LLMUsage
from rfp.schemas.agents import BidRecord, FieldResult
from rfp.settings import PROJECT_ROOT

OUTPUTS = PROJECT_ROOT / "outputs"
MAX_CELL = 160
NOT_STATED = "not stated"

COMPARE_RULES = """You compare bids for a sales team using ONLY the extracted field values provided.
- Refer to each bid by its id.
- Focus on what changes a bid / no-bid or pricing decision: deadlines, products and quantities,
  requirements (bonds, affidavits, manufacturer authorization, contract vehicle), services
  (installation, delivery), contract term, and risks.
- A value shown as "not stated" means the documents do not state it - never guess it.
- Values marked with a warning sign failed validation; mention that if you rely on them.
- Be concrete and concise.
- Never add up, total or estimate quantities; state them exactly as listed, item by item."""


class Difference(BaseModel):
    topic: str
    detail: str = Field(
        description="How the bids differ on this topic, naming each bid"
    )


class ComparisonAnalysis(BaseModel):
    summary: str = Field(description="3-5 sentence overview")
    differences: list[Difference]
    similarities: list[str] = Field(default_factory=list)
    considerations: list[str] = Field(
        default_factory=list, description="Risks or decision points for a bidder"
    )


class ComparisonReport(BaseModel):
    bid_ids: list[str]
    table: list[dict[str, str]]  # one row per field: {"field": name, bid_id: cell, ...}
    analysis: ComparisonAnalysis | None = None


def available_bids(outputs: Path = OUTPUTS) -> list[str]:
    """Bid ids that have an extraction output (a JSON with bid_id and fields)."""
    bids = []
    for path in sorted(outputs.glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and "bid_id" in data and "fields" in data:
            bids.append(data["bid_id"])
    return bids


def load_record(bid_id: str, outputs: Path = OUTPUTS) -> BidRecord:
    path = outputs / f"{bid_id}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"No extraction output for {bid_id} - run: python main.py extract data/bids/{bid_id}"
        )
    return BidRecord.model_validate_json(path.read_text())


def cell(result: FieldResult | None) -> str:
    """One table cell: value, first citation, and a warning sign if validation failed."""
    if result is None or result.value is None:
        return NOT_STATED
    text = (
        "; ".join(result.value) if isinstance(result.value, list) else str(result.value)
    )
    text = " ".join(text.split())
    if len(text) > MAX_CELL:
        text = text[: MAX_CELL - 1] + "…"
    if result.sources:
        text += f" ({result.sources[0].file}, p.{result.sources[0].page})"
    if "Validation failed" in result.notes:
        text = "⚠ " + text
    return text


def build_table(records: dict[str, BidRecord]) -> list[dict[str, str]]:
    rows = []
    for spec in load_registry()[1]:
        row = {"field": spec.name}
        for bid_id, record in records.items():
            row[bid_id] = cell(record.fields.get(spec.name))
        rows.append(row)
    return rows


def to_markdown(report: ComparisonReport) -> str:
    bids = report.bid_ids
    lines = [f"# Bid comparison: {' vs '.join(bids)}", ""]
    if report.analysis:
        a = report.analysis
        lines += ["## Summary", "", a.summary, "", "## Key differences", ""]
        lines += [f"- **{d.topic}:** {d.detail}" for d in a.differences]
        if a.similarities:
            lines += ["", "## Similarities", ""] + [f"- {s}" for s in a.similarities]
        if a.considerations:
            lines += ["", "## Considerations for a bidder", ""] + [
                f"- {c}" for c in a.considerations
            ]
        lines.append("")
    lines += [
        "## Side-by-side",
        "",
        "| Field | " + " | ".join(bids) + " |",
        "|---|" + "---|" * len(bids),
    ]
    for row in report.table:
        cells = [row[b].replace("|", "\\|") for b in bids]
        lines.append(f"| {row['field']} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "_Values come from the validated extraction outputs; each cell cites its first source. ⚠ = failed validation._",
    ]
    return "\n".join(lines) + "\n"


def save_report(report: ComparisonReport, outputs: Path = OUTPUTS) -> Path:
    name = "comparison_" + "_vs_".join(report.bid_ids)
    (outputs / f"{name}.json").write_text(report.model_dump_json(indent=2))
    md_path = outputs / f"{name}.md"
    md_path.write_text(to_markdown(report))
    return md_path


FACT_CHARS = 2500


def full_value(result: FieldResult | None) -> str:
    """Untruncated value for the LLM (the table keeps short cells for people)."""
    if result is None or result.value is None:
        return NOT_STATED
    text = (
        "; ".join(result.value) if isinstance(result.value, list) else str(result.value)
    )
    text = " ".join(text.split())[:FACT_CHARS]
    if "Validation failed" in result.notes:
        text = "(failed validation) " + text
    return text


class ComparisonAgent:
    def __init__(self, llm: LLMClient | None, tier: str = "smart"):
        self.llm = llm  # None -> table only, no analysis
        self.tier = tier

    def run(
        self, bid_ids: list[str], outputs: Path = OUTPUTS
    ) -> tuple[ComparisonReport, LLMUsage | None]:
        records = {b: load_record(b, outputs) for b in bid_ids}
        table = build_table(records)
        analysis, usage = None, None
        if self.llm is not None:
            facts = []
            for spec in load_registry()[1]:
                values = " || ".join(
                    f"{b}: {full_value(records[b].fields.get(spec.name))}"
                    for b in bid_ids
                )
                facts.append(f"- {spec.name}: {values}")
            analysis, usage = self.llm.structured(
                agent="compare",
                system=COMPARE_RULES,
                user=f"Bids: {', '.join(bid_ids)}\n\nExtracted fields:\n"
                + "\n".join(facts),
                response_model=ComparisonAnalysis,
                tier=self.tier,
                max_tokens=4000,
            )
        return ComparisonReport(bid_ids=bid_ids, table=table, analysis=analysis), usage
