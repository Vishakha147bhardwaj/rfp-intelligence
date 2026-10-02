from rfp.agents.reconciliation import (FieldReconciliation, ReconciliationOutput,
                                       apply_reconciliation)
from rfp.schemas.agents import Evidence, FieldResult, FieldSpec

DUE = FieldSpec(name="Due Date", group="g", format="datetime", description="d",
                queries=["due"], addendum_sensitive=True)


def ev(eid: str, doc_type: str, addendum: int | None = None) -> Evidence:
    return Evidence(evidence_id=eid, chunk_id=eid.lower(), bid_id="B1", file_name=f"{eid}.pdf",
                    page_number=1, doc_type=doc_type, addendum_number=addendum, text="t", score=1.0)


LOOKUP = {e.evidence_id: e for e in [ev("B1", "rfp"), ev("A1", "addendum", 2)]}.get


def current() -> dict[str, FieldResult]:
    return {"Due Date": FieldResult(value="27-JUN-2024 14:00", confidence=0.9, notes="from RFP")}


def finding(**kwargs) -> ReconciliationOutput:
    return ReconciliationOutput(fields=[FieldReconciliation(field="Due Date", **kwargs)])


def test_addendum_change_is_applied_and_logged():
    out = finding(original_value="27-JUN-2024 14:00", original_evidence_ids=["B1"],
                  changed_by_addendum=True, addendum_number=2,
                  new_value="July 9, 2024 at 2:00 PM CST", new_evidence_ids=["A1"],
                  explanation="Addendum 2 extends the due date.")
    updated, changes = apply_reconciliation([DUE], current(), out, LOOKUP)

    assert updated["Due Date"].value == "July 9, 2024 at 2:00 PM CST"
    assert updated["Due Date"].sources[0].file == "A1.pdf"
    assert "original: 27-JUN-2024 14:00" in updated["Due Date"].notes
    assert (changes[0].old_value, changes[0].addendum_number) == ("27-JUN-2024 14:00", 2)


def test_change_citing_only_base_documents_is_ignored():
    out = finding(changed_by_addendum=True, addendum_number=2,
                  new_value="July 9, 2024", new_evidence_ids=["B1"])
    updated, changes = apply_reconciliation([DUE], current(), out, LOOKUP)

    assert updated["Due Date"].value == "27-JUN-2024 14:00"
    assert changes == [] and "ignored" in updated["Due Date"].notes


def test_unchanged_field_keeps_value():
    updated, changes = apply_reconciliation([DUE], current(), finding(changed_by_addendum=False), LOOKUP)
    assert updated["Due Date"].value == "27-JUN-2024 14:00" and changes == []
    assert "no addendum change" in updated["Due Date"].notes