from types import SimpleNamespace

import pytest

from rfp.agents.comparison import (
    ComparisonAgent,
    ComparisonAnalysis,
    Difference,
    available_bids,
    to_markdown,
)
from rfp.agents.registry import field_names
from rfp.schemas.agents import BidRecord, FieldResult, Source


def record(bid_id: str, **values) -> BidRecord:
    fields = {}
    for name, (value, notes) in values.items():
        fields[name.replace("_", " ")] = FieldResult(
            value=value,
            confidence=0.9,
            notes=notes,
            sources=[Source(file=f"{bid_id}.pdf", page=1)],
        )
    return BidRecord(bid_id=bid_id, fields=fields)


@pytest.fixture
def outputs(tmp_path):
    a = record(
        "A", Title=("Laptops", ""), Delivery_Date=("45 days", "[Validation failed: x]")
    )
    b = record("B", Title=("Tablets", ""))
    for r in (a, b):
        (tmp_path / f"{r.bid_id}.json").write_text(r.model_dump_json())
    (tmp_path / "comparison_old.json").write_text(
        '{"bid_ids": ["A"]}'
    )  # not a bid record
    return tmp_path


class FakeLLM:
    def structured(self, **kwargs):
        analysis = ComparisonAnalysis(
            summary="A buys laptops, B buys tablets.",
            differences=[Difference(topic="Products", detail="A: laptops; B: tablets")],
        )
        return analysis, SimpleNamespace(input_tokens=1, output_tokens=1)


def test_available_bids_ignores_other_json(outputs):
    assert available_bids(outputs) == ["A", "B"]


def test_table_has_every_field_with_citations_and_not_stated(outputs):
    report, usage = ComparisonAgent(None).run(["A", "B"], outputs)
    assert usage is None and report.analysis is None
    assert [r["field"] for r in report.table] == field_names()
    title = next(r for r in report.table if r["field"] == "Title")
    assert title == {
        "field": "Title",
        "A": "Laptops (A.pdf, p.1)",
        "B": "Tablets (B.pdf, p.1)",
    }
    due = next(r for r in report.table if r["field"] == "Due Date")
    assert due["A"] == due["B"] == "not stated"


def test_failed_validation_is_flagged(outputs):
    report, _ = ComparisonAgent(None).run(["A", "B"], outputs)
    delivery = next(r for r in report.table if r["field"] == "Delivery Date")
    assert delivery["A"].startswith("⚠ 45 days")


def test_markdown_has_analysis_and_table(outputs):
    report, _ = ComparisonAgent(FakeLLM()).run(["A", "B"], outputs)
    md = to_markdown(report)
    assert "## Key differences" in md and "**Products:**" in md
    assert "| Title | Laptops (A.pdf, p.1) | Tablets (B.pdf, p.1) |" in md


def test_missing_output_gives_clear_error(outputs):
    with pytest.raises(FileNotFoundError, match="python main.py extract"):
        ComparisonAgent(None).run(["A", "Z"], outputs)
