"""Go / no-go agent: checks a bid against a company profile.

- Deadline: checked by code (date arithmetic).
- Other criteria: assessed by the LLM using ONLY the profile and the bid's validated fields.
- The decision: computed by code from fixed rules (any must-have fail -> NO-GO, any must-have
  unknown -> REVIEW, otherwise GO). The LLM never decides the verdict.
"""

from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from rfp.agents.comparison import OUTPUTS, full_value, load_record
from rfp.agents.registry import load_registry
from rfp.agents.validator import _date_spans
from rfp.llm.client import LLMClient, LLMUsage
from rfp.schemas.agents import BidRecord
from rfp.settings import PROJECT_ROOT

CAPABILITIES_PATH = PROJECT_ROOT / "config" / "capabilities.yaml"
Status = Literal["pass", "fail", "unknown"]
Decision = Literal["GO", "NO-GO", "REVIEW"]

GO_RULES = """You assess whether a company can respond to a bid, one criterion at a time.
Use ONLY the company profile and the extracted bid fields provided.
- pass: the bid's requirement is clearly met by the profile, or the bid has no such requirement.
- fail: the bid states a requirement the profile clearly does not meet.
- unknown: the information needed is missing or ambiguous - never guess.
Give a one-sentence reason that names the bid fields you used."""


class Criterion(BaseModel):
    id: str
    must_have: bool
    question: str


class CriterionAssessment(BaseModel):
    id: str
    status: Status
    reason: str
    fields_used: list[str] = Field(default_factory=list)


class LLMAssessment(BaseModel):
    assessments: list[CriterionAssessment]
    summary: str = Field(description="2-3 sentences explaining the overall picture")


class CriterionResult(CriterionAssessment):
    must_have: bool


class GoNoGoReport(BaseModel):
    bid_id: str
    as_of: date
    company: str
    decision: Decision
    criteria: list[CriterionResult]
    summary: str = ""


def load_capabilities(path: Path = CAPABILITIES_PATH) -> tuple[dict, list[Criterion]]:
    data = yaml.safe_load(path.read_text())
    return data["company"], [Criterion(**c) for c in data["criteria"]]


def check_deadline(
    record: BidRecord, as_of: date, min_days: int
) -> CriterionAssessment:
    due = record.fields.get("Due Date")
    text = full_value(due) if due else ""
    dates = [d for *_, d in _date_spans(text)]
    if not dates:
        return CriterionAssessment(
            id="deadline", status="unknown", reason="Due date not stated."
        )
    due_date = max(dates)
    days_left = (due_date - as_of).days
    if days_left < 0:
        status, reason = (
            "fail",
            f"Due date {due_date} has already passed (as of {as_of}).",
        )
    elif days_left < min_days:
        status, reason = (
            "fail",
            f"Only {days_left} days left until {due_date}; we need {min_days}.",
        )
    else:
        status, reason = (
            "pass",
            f"{days_left} days left until {due_date} (need {min_days}).",
        )
    return CriterionAssessment(
        id="deadline", status=status, reason=reason, fields_used=["Due Date"]
    )


def decide(results: list[CriterionResult]) -> Decision:
    must = [r for r in results if r.must_have]
    if any(r.status == "fail" for r in must):
        return "NO-GO"
    if any(r.status == "unknown" for r in must):
        return "REVIEW"
    return "GO"


def to_markdown(report: GoNoGoReport) -> str:
    icon = {"pass": "✅ pass", "fail": "❌ fail", "unknown": "❔ unknown"}
    lines = [
        f"# Go / No-Go: {report.bid_id} - **{report.decision}**",
        "",
        f"Company: {report.company} | Evaluated as of {report.as_of}",
        "",
    ]
    if report.summary:
        lines += ["## Summary", "", report.summary, ""]
    lines += [
        "## Criteria",
        "",
        "| Criterion | Must-have | Status | Reason |",
        "|---|---|---|---|",
    ]
    for r in report.criteria:
        reason = r.reason.replace("|", "\\|")
        lines.append(
            f"| {r.id} | {'yes' if r.must_have else 'no'} | {icon[r.status]} | {reason} |"
        )
    lines += [
        "",
        (
            "_Decision rule: any must-have fail = NO-GO; any must-have unknown = REVIEW; "
            "otherwise GO. The deadline is checked by code; other criteria by the LLM using only "
            "the company profile and the bid's validated fields._"
        ),
    ]
    return "\n".join(lines) + "\n"


def save_report(report: GoNoGoReport, outputs: Path = OUTPUTS) -> Path:
    name = f"go_no_go_{report.bid_id}"
    (outputs / f"{name}.json").write_text(report.model_dump_json(indent=2))
    path = outputs / f"{name}.md"
    path.write_text(to_markdown(report))
    return path


class GoNoGoAgent:
    def __init__(
        self,
        llm: LLMClient | None,
        capabilities_path: Path = CAPABILITIES_PATH,
        tier: str = "smart",
    ):
        self.llm = llm
        self.company, self.criteria = load_capabilities(capabilities_path)
        self.tier = tier

    def run(
        self, bid_id: str, as_of: date, outputs: Path = OUTPUTS
    ) -> tuple[GoNoGoReport, LLMUsage | None]:
        record = load_record(bid_id, outputs)
        found: dict[str, CriterionAssessment] = {
            "deadline": check_deadline(
                record, as_of, int(self.company.get("min_days_to_prepare", 0))
            )
        }
        summary, usage = "", None
        llm_criteria = [c for c in self.criteria if c.id != "deadline"]
        if self.llm is not None and llm_criteria:
            facts = "\n".join(
                f"- {s.name}: {full_value(record.fields.get(s.name))}"
                for s in load_registry()[1]
            )
            questions = "\n".join(f"- {c.id}: {c.question}" for c in llm_criteria)
            output, usage = self.llm.structured(
                agent="go_no_go",
                system=GO_RULES,
                user=(
                    f"Company profile:\n{yaml.safe_dump(self.company, sort_keys=False)}\n"
                    f"Bid {bid_id} - extracted fields:\n{facts}\n\nCriteria to assess:\n{questions}"
                ),
                response_model=LLMAssessment,
                tier=self.tier,
                max_tokens=3000,
            )
            known = {c.id for c in llm_criteria}
            found.update({a.id: a for a in output.assessments if a.id in known})
            summary = output.summary

        results = []
        for c in self.criteria:
            a = found.get(c.id) or CriterionAssessment(
                id=c.id, status="unknown", reason="Not assessed."
            )
            results.append(CriterionResult(**a.model_dump(), must_have=c.must_have))
        report = GoNoGoReport(
            bid_id=bid_id,
            as_of=as_of,
            company=self.company.get("name", ""),
            decision=decide(results),
            criteria=results,
            summary=summary,
        )
        return report, usage
