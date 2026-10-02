"""Extraction agent: fills one group of fields using ONLY the retrieved evidence."""

import re

import structlog
from pydantic import BaseModel

from rfp.agents.retrieval import EvidenceBundle
from rfp.llm.client import LLMClient, LLMUsage
from rfp.schemas.agents import Evidence, FieldDraft, FieldResult, FieldSpec, FieldValueT, Source

log = structlog.get_logger()

NOT_FOUND = "Not found in documents"
EMPTY_VALUES = {"", "null", "none found", "n/a", "not found", "unknown", "not specified"}

EXTRACTION_RULES = """You are a procurement analyst extracting fields from bid documents \
(RFPs, addendums, bid portal pages, specification sheets, affidavits).

Rules:
1. Use ONLY the evidence passages provided. Never use outside knowledge and never guess.
2. For every field, cite the evidence IDs (e.g. "E3") of the passages that directly support the value.
3. If the evidence does not contain the value, return value null and an empty evidence_ids list.
4. Copy identifiers, part numbers, model numbers, dates, times, time zones, amounts and emails
   exactly as written.
5. For [list] fields return a JSON list of strings, one item per entry. For all other fields return
   a single string.
6. If passages disagree (for example an addendum changes a date), choose the most authoritative,
   most recent statement and mention the other values in reasoning. A later step re-checks addendums.
7. Confidence: 0.9 or higher only when a passage states the value explicitly; lower when you had
   to combine passages or interpret.
"""


class GroupExtraction(BaseModel):
    fields: list[FieldDraft]


def _field_block(specs: list[FieldSpec]) -> str:
    lines = []
    for s in specs:
        line = f"- {s.name} [{s.format}]: {s.description}"
        if s.hints:
            line += f" Hint: {s.hints}"
        lines.append(line)
    return "\n".join(lines)


def _evidence_block(bundle: EvidenceBundle, names: list[str]) -> str:
    parts = []
    for e in bundle.for_fields(names):
        label = e.doc_type + (f" #{e.addendum_number}" if e.addendum_number else "")
        parts.append(f"[{e.evidence_id}] {e.file_name} | page {e.page_number} | {label}\n{e.text}")
    return "\n\n".join(parts)


def normalize_value(value: FieldValueT, spec: FieldSpec) -> FieldValueT:
    """Turn empty/placeholder answers into None; consistent list/text shapes; no duplicate items."""
    if value is None:
        return None
    if isinstance(value, list):
        items = [v.strip() for v in value if v and v.strip().lower() not in EMPTY_VALUES]
        items = list(dict.fromkeys(items))                      # dedupe, keep order
        if not items:
            return None
        return items if spec.format == "list" else "; ".join(items)
    text = value.strip()
    if text.lower() in EMPTY_VALUES:
        return None
    return [text] if spec.format == "list" else text


def complete_ids(value: list[str], spec: FieldSpec, cited: list[Evidence],
                 bundle: EvidenceBundle) -> tuple[list[str], list[Evidence], list[str]]:
    """Add identifiers matching spec.id_patterns that appear in the cited files' evidence.

    The LLM locates the list (its citations tell us which files); code copies it exactly.
    Returns (completed value, evidence used, identifiers added).
    """
    cited_files = {e.file_name for e in cited}
    pool = [e for eid in bundle.by_field.get(spec.name, [])
            if (e := bundle.get(eid)) and e.file_name in cited_files]
    pool += [e for e in cited if e not in pool]

    result, used, added = list(value), list(cited), []
    for evidence in pool:
        for pattern in spec.id_patterns:
            for token in re.findall(pattern, evidence.text):
                if token not in result:
                    result.append(token)
                    added.append(token)
                    if evidence not in used:
                        used.append(evidence)
    return result, used, added


def finalize_drafts(specs: list[FieldSpec], drafts: list[FieldDraft],
                    bundle: EvidenceBundle) -> dict[str, FieldResult]:
    """Apply guardrails: valid citations only; no citation -> no value; missing fields -> null."""
    by_name = {d.field: d for d in drafts}
    results: dict[str, FieldResult] = {}

    for spec in specs:
        draft = by_name.get(spec.name)
        if draft is None:
            results[spec.name] = FieldResult(value=None, confidence=0.0,
                                             notes=f"{NOT_FOUND} (field not returned by extractor)")
            continue

        evidence = [e for eid in dict.fromkeys(draft.evidence_ids) if (e := bundle.get(eid))]
        value = normalize_value(draft.value, spec)
        notes = draft.reasoning

        if value is not None and not evidence:
            log.warning("guardrail_no_citation", field=spec.name, value=str(draft.value)[:100])
            results[spec.name] = FieldResult(
                value=None, confidence=0.0,
                notes=f"Rejected: value had no valid citation (model proposed {draft.value!r})",
            )
            continue
        if value is None:
            results[spec.name] = FieldResult(value=None, confidence=round(draft.confidence, 2),
                                             notes=f"{NOT_FOUND}. {draft.reasoning}".strip())
            continue

        if spec.id_patterns and isinstance(value, list):
            value, evidence, added = complete_ids(value, spec, evidence, bundle)
            if added:
                log.info("id_pattern_completion", field=spec.name, added=len(added))
                notes += f" [Pattern check added {len(added)} item(s) from cited evidence: {', '.join(added)}]"

        results[spec.name] = FieldResult(
            value=value,
            sources=[Source(file=e.file_name, page=e.page_number, chunk_id=e.chunk_id) for e in evidence],
            confidence=round(draft.confidence, 2),
            notes=notes,
        )
    return results


class ExtractionAgent:
    """One specialist per field group."""

    def __init__(self, llm: LLMClient, group: str, group_description: str, tier: str = "fast"):
        self.llm = llm
        self.group = group
        self.group_description = group_description
        self.tier = tier

    def run(self, bid_id: str, specs: list[FieldSpec], bundle: EvidenceBundle,
            feedback: dict[str, str] | None = None
            ) -> tuple[dict[str, FieldResult], LLMUsage | None]:
        names = [s.name for s in specs]
        evidence_text = _evidence_block(bundle, names)
        if not evidence_text:
            return {n: FieldResult(value=None, confidence=0.0,
                                   notes=f"{NOT_FOUND} (no evidence retrieved)") for n in names}, None

        system = (f"{EXTRACTION_RULES}\nYou are the '{self.group}' specialist "
                  f"({self.group_description}).\n\nFields:\n{_field_block(specs)}")
        user = (f"Bid: {bid_id}\nExtract these fields: {', '.join(names)}\n\n"
                f"Evidence:\n\n{evidence_text}\n\nReturn exactly one entry per field, in the order listed.")
        if feedback:
            problems = "\n".join(f"- {name}: {reason}" for name, reason in feedback.items())
            user += (f"\n\nA previous answer was REJECTED by the validator:\n{problems}\n"
                     "Fix these problems. If the evidence does not support a value, return null.")

        output, usage = self.llm.structured(
            agent=f"extract:{self.group}", system=system, user=user,
            response_model=GroupExtraction, tier=self.tier, max_tokens=4096,
        )
        return finalize_drafts(specs, output.fields, bundle), usage