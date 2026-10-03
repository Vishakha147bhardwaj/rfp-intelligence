"""Addendum reconciliation agent: original value vs. addendum changes -> final value + change log."""

from collections.abc import Callable

import structlog
from pydantic import BaseModel, Field

from rfp.agents.extraction import normalize_value
from rfp.agents.retrieval import EvidenceBundle, RetrievalAgent
from rfp.llm.client import LLMClient, LLMUsage
from rfp.schemas.agents import (
    AddendumChange,
    Evidence,
    FieldResult,
    FieldSpec,
    FieldValueT,
    Source,
)
from rfp.schemas.documents import DocType

log = structlog.get_logger()

BASE_TYPES = [t.value for t in DocType if t != DocType.ADDENDUM]

RECONCILIATION_RULES = """You reconcile bid information between an original solicitation and its \
addendums.

Evidence IDs starting with "B" come from BASE documents (the RFP, bid portal page, specs, forms).
Evidence IDs starting with "A" come from ADDENDUMS; a higher addendum number is more recent.

For each field:
1. original_value: what the original RFP states, citing B-evidence. Bid portal pages are often
   updated after addendums, so prefer the RFP document itself for the original. null if not stated.
2. changed_by_addendum: true only if an addendum explicitly changes, extends, adds to or clarifies
   this field. An addendum question-and-answer counts when the answer states a requirement.
3. If changed: new_value is the value after the MOST RECENT addendum that changes it,
   addendum_number is that addendum, and new_evidence_ids cite its A-evidence.
4. If not changed: new_value null and new_evidence_ids empty.
5. Use only the evidence. Copy dates, times and time zones exactly as written.
"""


class FieldReconciliation(BaseModel):
    field: str
    original_value: FieldValueT = None
    original_evidence_ids: list[str] = Field(default_factory=list)
    changed_by_addendum: bool = False
    addendum_number: int | None = None
    new_value: FieldValueT = None
    new_evidence_ids: list[str] = Field(default_factory=list)
    explanation: str = ""


class ReconciliationOutput(BaseModel):
    fields: list[FieldReconciliation]


def _fmt(value: FieldValueT) -> str:
    if value is None:
        return "null"
    return "; ".join(value) if isinstance(value, list) else value


def apply_reconciliation(
    specs: list[FieldSpec],
    results: dict[str, FieldResult],
    output: ReconciliationOutput,
    lookup: Callable[[str], Evidence | None],
) -> tuple[dict[str, FieldResult], list[AddendumChange]]:
    """Apply the agent's findings. A change counts only if it cites real addendum evidence."""
    updated = dict(results)
    changes: list[AddendumChange] = []
    findings = {f.field: f for f in output.fields}

    for spec in specs:
        finding, current = findings.get(spec.name), results.get(spec.name)
        if finding is None or current is None:
            continue
        if not finding.changed_by_addendum:
            updated[spec.name] = current.model_copy(
                update={
                    "notes": f"{current.notes} [Reconciliation: no addendum change.]".strip()
                }
            )
            continue

        new_value = normalize_value(finding.new_value, spec)
        evidence = [
            e
            for eid in finding.new_evidence_ids
            if (e := lookup(eid)) and e.doc_type == DocType.ADDENDUM.value
        ]
        if new_value is None or not evidence:
            log.warning(
                "reconciliation_rejected",
                field=spec.name,
                reason="change claimed without addendum evidence",
            )
            updated[spec.name] = current.model_copy(
                update={
                    "notes": (
                        f"{current.notes} [Reconciliation claimed an addendum change without addendum "
                        f"evidence - ignored.]"
                    ).strip()
                }
            )
            continue

        number = (
            finding.addendum_number
            or max((e.addendum_number or 0) for e in evidence)
            or None
        )
        original = normalize_value(finding.original_value, spec)
        sources = [
            Source(file=e.file_name, page=e.page_number, chunk_id=e.chunk_id)
            for e in evidence
        ]
        updated[spec.name] = FieldResult(
            value=new_value,
            sources=sources,
            confidence=max(current.confidence, 0.9),
            notes=f"Updated by Addendum {number} (original: {_fmt(original)}). {finding.explanation}",
        )
        changes.append(
            AddendumChange(
                field=spec.name,
                old_value=original,
                new_value=new_value,
                addendum_number=number,
                source=sources[0],
            )
        )
        log.info("addendum_change", field=spec.name, addendum=number)
    return updated, changes


def _evidence_text(bundle: EvidenceBundle) -> str:
    parts = []
    for e in bundle.evidence:
        label = f"addendum #{e.addendum_number}" if e.addendum_number else e.doc_type
        parts.append(
            f"[{e.evidence_id}] {e.file_name} | page {e.page_number} | {label}\n{e.text}"
        )
    return "\n\n".join(parts)


class ReconciliationAgent:
    def __init__(self, llm: LLMClient, retrieval: RetrievalAgent, tier: str = "smart"):
        self.llm = llm
        self.retrieval = retrieval
        self.tier = tier

    def run(
        self, bid_id: str, specs: list[FieldSpec], results: dict[str, FieldResult]
    ) -> tuple[dict[str, FieldResult], list[AddendumChange], LLMUsage | None]:
        sensitive = [s for s in specs if s.addendum_sensitive and s.name in results]
        if not sensitive:
            return results, [], None

        addenda = self.retrieval.gather(
            bid_id, sensitive, doc_type=DocType.ADDENDUM.value, id_prefix="A"
        )
        if not addenda.evidence:
            log.info(
                "reconciliation_skipped", bid=bid_id, reason="no addendum evidence"
            )
            return results, [], None
        base = self.retrieval.gather(
            bid_id, sensitive, doc_type=BASE_TYPES, id_prefix="B"
        )

        fields_text = "\n".join(
            f"- {s.name}: {s.description} Currently extracted: {_fmt(results[s.name].value)}"
            for s in sensitive
        )
        user = (
            f"Bid: {bid_id}\n\nFields to reconcile:\n{fields_text}\n\n"
            f"BASE evidence:\n\n{_evidence_text(base)}\n\n"
            f"ADDENDUM evidence:\n\n{_evidence_text(addenda)}\n\n"
            "Return exactly one entry per field."
        )
        output, usage = self.llm.structured(
            agent="reconcile",
            system=RECONCILIATION_RULES,
            user=user,
            response_model=ReconciliationOutput,
            tier=self.tier,
            max_tokens=4096,
        )
        updated, changes = apply_reconciliation(
            sensitive, results, output, lambda eid: base.get(eid) or addenda.get(eid)
        )
        return updated, changes, usage
