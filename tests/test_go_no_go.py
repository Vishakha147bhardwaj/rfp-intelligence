from datetime import date
from types import SimpleNamespace

import pytest

from rfp.agents.go_no_go import (
    CriterionAssessment,
    CriterionResult,
    GoNoGoAgent,
    LLMAssessment,
    check_deadline,
    decide,
)
from rfp.schemas.agents import BidRecord, FieldResult

CAPABILITIES = """
company:
  name: Test Co
  min_days_to_prepare: 7
criteria:
  - {id: deadline, must_have: true, question: q}
  - {id: services, must_have: true, question: q}
  - {id: quantity, must_have: false, question: q}
"""


def record(due: str | None) -> BidRecord:
    fields = {"Due Date": FieldResult(value=due, confidence=0.9)} if due else {}
    return BidRecord(bid_id="B", fields=fields)


def result(status: str, must: bool = True) -> CriterionResult:
    return CriterionResult(id="x", status=status, reason="r", must_have=must)


def test_decision_rules():
    assert decide([result("pass"), result("fail", must=False)]) == "GO"
    assert decide([result("pass"), result("unknown")]) == "REVIEW"
    assert decide([result("unknown"), result("fail")]) == "NO-GO"


def test_deadline_checked_by_code():
    assert (
        check_deadline(record("July 9, 2024 2:00 PM"), date(2024, 6, 1), 7).status
        == "pass"
    )
    assert (
        check_deadline(record("July 9, 2024 2:00 PM"), date(2024, 7, 5), 7).status
        == "fail"
    )
    assert (
        check_deadline(record("July 9, 2024 2:00 PM"), date(2026, 1, 1), 7).status
        == "fail"
    )
    assert check_deadline(record(None), date(2024, 6, 1), 7).status == "unknown"


class FakeLLM:
    def __init__(self, assessments):
        self.assessments = assessments

    def structured(self, **kwargs):
        return LLMAssessment(
            assessments=self.assessments, summary="s"
        ), SimpleNamespace()


@pytest.fixture
def setup(tmp_path):
    caps = tmp_path / "capabilities.yaml"
    caps.write_text(CAPABILITIES)
    (tmp_path / "B.json").write_text(record("July 9, 2024 2:00 PM").model_dump_json())
    return caps, tmp_path


def test_llm_cannot_add_criteria_and_skipped_ones_are_unknown(setup):
    caps, outputs = setup
    llm = FakeLLM(
        [
            CriterionAssessment(id="services", status="pass", reason="ok"),
            CriterionAssessment(
                id="invented", status="fail", reason="should be ignored"
            ),
        ]
    )
    report, _ = GoNoGoAgent(llm, caps).run("B", date(2024, 6, 1), outputs)
    by_id = {c.id: c for c in report.criteria}
    assert set(by_id) == {"deadline", "services", "quantity"}
    assert by_id["quantity"].status == "unknown"  # skipped by the LLM
    assert report.decision == "GO"  # quantity is not a must-have


def test_must_have_fail_means_no_go(setup):
    caps, outputs = setup
    llm = FakeLLM(
        [
            CriterionAssessment(
                id="services", status="fail", reason="etching not offered"
            )
        ]
    )
    report, _ = GoNoGoAgent(llm, caps).run("B", date(2024, 6, 1), outputs)
    assert report.decision == "NO-GO"
