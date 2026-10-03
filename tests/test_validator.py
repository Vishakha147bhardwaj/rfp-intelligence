from types import SimpleNamespace

from rfp.agents.validator import (
    FieldJudgement,
    JudgeOutput,
    ValidatorAgent,
    consistency_problems,
    format_problems,
    grounding_problems,
)
from rfp.llm.client import LLMError
from rfp.schemas.agents import FieldResult, FieldSpec, Source

DUE = FieldSpec(
    name="Due Date", group="g", format="datetime", description="d", queries=["q"]
)
CONTACT = FieldSpec(
    name="contact_info", group="g", format="contact", description="d", queries=["q"]
)
PAY = FieldSpec(
    name="Payment Terms", group="g", format="text", description="d", queries=["q"]
)
TEXTS = {
    "c1": "Invoices shall be submitted within 10 days of delivering the equipment."
}


def pay_results(value="Invoices within 10 days"):
    return {
        "Payment Terms": FieldResult(
            value=value,
            confidence=0.9,
            sources=[Source(file="p.pdf", page=2, chunk_id="c1")],
        )
    }


class FakeLLM:
    def __init__(self, output=None, error=None):
        self.output, self.error = output, error

    def structured(self, **kwargs):
        if self.error:
            raise self.error
        return self.output, SimpleNamespace(input_tokens=1, output_tokens=1)


def test_datetime_needs_a_time_and_warns_without_zone():
    problems, _ = format_problems(DUE, "July 9, 2024")
    assert "no time of day" in problems
    problems, warnings = format_problems(DUE, "July 9, 2024 at 2:00 PM")
    assert problems == [] and warnings == ["no time zone"]


def test_contact_needs_email_or_phone():
    assert format_problems(CONTACT, "Jasmine Alzate")[0]
    assert format_problems(CONTACT, "Jasmine Alzate | JALZATE@dallasisd.org")[0] == []


def test_grounding_catches_the_net_30_case():
    assert grounding_problems("Net 30; invoices within 10 days", TEXTS["c1"]) == [
        "number '30' not in cited passages"
    ]


def test_grounding_accepts_reformatted_dates_and_times():
    assert (
        grounding_problems(
            "June 27, 2024 at 2:00 PM", "Solicitation Due   27-JUN-2024 14:00:00"
        )
        == []
    )


def test_grounding_catches_wrong_email():
    assert grounding_problems("a@x.org", "contact b@x.org") == [
        "email 'a@x.org' not in cited passages"
    ]


def test_prebid_after_due_date_is_inconsistent():
    results = {
        "Due Date": FieldResult(value="June 1, 2024 2:00 PM", confidence=0.9),
        "Pre Bid Meeting": FieldResult(value="June 10, 2024", confidence=0.9),
    }
    assert "Pre Bid Meeting" in consistency_problems(results)


def test_net_30_fails_deterministically_before_any_llm_call():
    llm = FakeLLM(error=AssertionError("judge must not be called for failed fields"))
    v, _ = ValidatorAgent(llm).run(
        "B1", [PAY], pay_results("Net 30; invoices within 10 days"), TEXTS
    )
    assert v["Payment Terms"].status == "failed"


def test_fact_check_failure_returns_retry_queries():
    judge = JudgeOutput(
        judgements=[
            FieldJudgement(
                field="Payment Terms",
                supported=False,
                reason="no payment term stated",
                retry_queries=["net payment days"],
            )
        ]
    )
    v, _ = ValidatorAgent(FakeLLM(judge)).run("B1", [PAY], pay_results(), TEXTS)
    assert v["Payment Terms"].status == "failed"
    assert v["Payment Terms"].retry_queries == ["net payment days"]


def test_llm_outage_falls_back_to_deterministic_checks():
    v, usage = ValidatorAgent(FakeLLM(error=LLMError("timeout"))).run(
        "B1", [PAY], pay_results(), TEXTS
    )
    assert v["Payment Terms"].status == "passed" and usage is None
    assert "LLM fact-check unavailable" in v["Payment Terms"].warnings


def test_missing_value_is_not_found():
    results = {
        "Payment Terms": FieldResult(
            value=None, confidence=0.5, notes="Not found in documents"
        )
    }
    v, _ = ValidatorAgent().run("B1", [PAY], results, {})
    assert v["Payment Terms"].status == "not_found"
