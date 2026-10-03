from types import SimpleNamespace

from rfp.agents.registry import field_names
from rfp.agents.report import build_record
from rfp.agents.state import merge
from rfp.agents.tracing import trace_step
from rfp.schemas.agents import FieldResult, FieldValidation


def test_record_has_all_20_fields_in_registry_order():
    results = {"Title": FieldResult(value="Laptops", confidence=0.9)}
    validations = {
        "Title": FieldValidation(field="Title", status="passed"),
        "Bid Bond Requirement": FieldValidation(
            field="Bid Bond Requirement", status="not_found"
        ),
    }
    record = build_record("B1", results, None, [], validations)

    assert list(record.fields) == field_names()
    assert record.fields["Title"].value == "Laptops"
    assert (
        record.fields["Due Date"].value is None
        and "Not found" in record.fields["Due Date"].notes
    )
    assert (record.validation.passed, record.validation.not_found) == (1, 1)


def test_trace_step_records_latency_and_tokens():
    with trace_step("run1", "extract", group="g") as step:
        step.add_usage(
            SimpleNamespace(
                model_dump=lambda: {"input_tokens": 100, "output_tokens": 20}
            )
        )
        step.add_usage(
            SimpleNamespace(model_dump=lambda: {"input_tokens": 50, "output_tokens": 5})
        )
    event = step.event
    assert (event["node"], event["group"]) == ("extract", "g")
    assert (event["input_tokens"], event["output_tokens"]) == (150, 25)
    assert event["latency_ms"] >= 0 and event["error"] is None


def test_merge_reducer_combines_parallel_branches():
    a = {"Due Date": FieldResult(value="x", confidence=0.9)}
    b = {"Title": FieldResult(value="y", confidence=0.9)}
    assert set(merge(a, b)) == {"Due Date", "Title"}
    assert merge(None, b) == b
