"""Validator / critic agent: deterministic checks + LLM fact-check of every extracted value."""

import re
from datetime import date

import structlog
from dateutil import parser as date_parser
from pydantic import BaseModel, Field

from rfp.ingestion.pipeline import DATE_PATTERNS
from rfp.llm.client import LLMClient, LLMError, LLMUsage
from rfp.schemas.agents import (FieldResult, FieldSpec, FieldValidation, FieldValueT,
                                ValidationSummary)

log = structlog.get_logger()

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE = re.compile(r"\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}")
TIME_VALUE = re.compile(
    r"\b(\d{1,2}):(\d{2})(?::\d{2})?\s*([ap]\.?m\.?)?|\b(\d{1,2})\s*([ap]\.?m\.?)(?![a-z])",
    re.IGNORECASE,
)
TIME_ZONE = re.compile(r"\b(?:[ECMP][SD]?T|UTC|GMT)\b|\b(?:Eastern|Central|Mountain|Pacific)\b")
PASSAGE_CHARS = 2500   # per cited passage sent to the fact-checker

JUDGE_RULES = """You are a strict fact-checker for information extracted from bid documents.
For each field you get the extracted value and the exact passages it cites.

Decide whether the passages fully support the value:
- supported = true only if every fact in the value (names, numbers, dates, times, time zones,
  terms, list items, and which person a phone or email belongs to) is stated in, or directly
  follows from, the passages.
- Any addition the passages do not state (for example a payment term, a time zone, or a phone
  number belonging to a different office) makes the value unsupported.
- Also mark it unsupported if the value is true but does not answer the field's Meaning (for
  example a proposal-validity period given as the contract term, or a warranty given as delivery).
- If unsupported: give a one-sentence reason and up to 3 short search queries that could find
  the correct value in the documents.
Judge only support by the passages, not importance or style.
"""


class FieldJudgement(BaseModel):
    field: str
    supported: bool
    reason: str = ""
    retry_queries: list[str] = Field(default_factory=list)


class JudgeOutput(BaseModel):
    judgements: list[FieldJudgement]


# ---------- deterministic helpers ----------

def _text(value: FieldValueT) -> str:
    if value is None:
        return ""
    return "; ".join(value) if isinstance(value, list) else value


def _date_spans(text: str) -> list[tuple[int, int, date]]:
    spans = []
    for pattern in DATE_PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            try:
                spans.append((m.start(), m.end(), date_parser.parse(m.group(0)).date()))
            except (ValueError, OverflowError):
                continue
    return spans


def _time_spans(text: str) -> list[tuple[int, int, tuple[int, int]]]:
    spans = []
    for m in TIME_VALUE.finditer(text):
        if m.group(1):
            hour, minute, ampm = int(m.group(1)), int(m.group(2)), m.group(3)
        else:
            hour, minute, ampm = int(m.group(4)), 0, m.group(5)
        if ampm:
            pm = ampm.lower().startswith("p")
            hour = (hour % 12) + (12 if pm else 0)
        if hour < 24 and minute < 60:
            spans.append((m.start(), m.end(), (hour, minute)))
    return spans


def _remove(text: str, spans: list[tuple]) -> str:
    for start, end, *_ in sorted(spans, key=lambda s: s[0], reverse=True):
        text = text[:start] + " " + text[end:]
    return text


def _numbers(text: str) -> set[str]:
    return {n.lstrip("0") or "0" for n in re.findall(r"\d+", text)}


def grounding_problems(value_text: str, evidence_text: str) -> list[str]:
    """Every email, date, time and number in the value must appear in the cited text."""
    problems: list[str] = []
    evidence_lower = evidence_text.lower()

    emails = list(EMAIL.finditer(value_text))
    for m in emails:
        if m.group(0).lower() not in evidence_lower:
            problems.append(f"email '{m.group(0)}' not in cited passages")
    rest = _remove(value_text, [(m.start(), m.end()) for m in emails])

    date_spans = _date_spans(rest)
    evidence_dates = {d for *_, d in _date_spans(evidence_text)}
    for *_, d in date_spans:
        if d not in evidence_dates:
            problems.append(f"date {d.isoformat()} not in cited passages")
    rest = _remove(rest, date_spans)

    time_spans = _time_spans(rest)
    evidence_times = {t for *_, t in _time_spans(evidence_text)}
    for *_, (h, m) in time_spans:
        if (h, m) not in evidence_times:
            problems.append(f"time {h:02d}:{m:02d} not in cited passages")
    rest = _remove(rest, time_spans)

    evidence_numbers = _numbers(evidence_text)
    for n in re.findall(r"\d+", rest):
        if (n.lstrip("0") or "0") not in evidence_numbers:
            problems.append(f"number '{n}' not in cited passages")
    return list(dict.fromkeys(problems))


def format_problems(spec: FieldSpec, value: FieldValueT) -> tuple[list[str], list[str]]:
    """Return (problems, warnings) for the field's declared format."""
    problems: list[str] = []
    warnings: list[str] = []
    text = _text(value)
    if spec.format == "datetime":
        if not _date_spans(text):
            problems.append("no recognisable date")
        if not _time_spans(text):
            problems.append("no time of day")
        elif not TIME_ZONE.search(text):
            warnings.append("no time zone")
    elif spec.format == "date" and not _date_spans(text):
        problems.append("no recognisable date")
    elif spec.format == "contact" and not (EMAIL.search(text) or PHONE.search(text)):
        problems.append("contact has neither an email nor a phone number")
    elif spec.format == "list" and not isinstance(value, list):
        problems.append("expected a list")
    return problems, warnings


def consistency_problems(results: dict[str, FieldResult]) -> dict[str, list[str]]:
    """Cross-field rules. Currently: the pre-bid meeting cannot be after the due date."""
    out: dict[str, list[str]] = {}
    due, pre = results.get("Due Date"), results.get("Pre Bid Meeting")
    if due and pre and due.value and pre.value:
        pre_dates = [d for *_, d in _date_spans(_text(pre.value))]
        due_dates = [d for *_, d in _date_spans(_text(due.value))]
        if pre_dates and due_dates and min(pre_dates) > max(due_dates):
            out["Pre Bid Meeting"] = [f"pre-bid date {min(pre_dates)} is after the due date {max(due_dates)}"]
    return out


def summarize(validations: dict[str, FieldValidation]) -> ValidationSummary:
    statuses = [v.status for v in validations.values()]
    return ValidationSummary(passed=statuses.count("passed"), failed=statuses.count("failed"),
                             not_found=statuses.count("not_found"))


def apply_validation(results: dict[str, FieldResult],
                     validations: dict[str, FieldValidation]) -> dict[str, FieldResult]:
    """Lower confidence and annotate fields that are still failing after all retries."""
    out = dict(results)
    for name, v in validations.items():
        r = results.get(name)
        if r is not None and v.status == "failed":
            out[name] = r.model_copy(update={
                "confidence": min(r.confidence, 0.4),
                "notes": f"{r.notes} [Validation failed: {'; '.join(v.reasons)}]".strip(),
            })
    return out


# ---------- the agent ----------

class ValidatorAgent:
    def __init__(self, llm: LLMClient | None = None, tier: str = "smart"):
        self.llm = llm
        self.tier = tier

    def run(self, bid_id: str, specs: list[FieldSpec], results: dict[str, FieldResult],
            texts: dict[str, str]) -> tuple[dict[str, FieldValidation], LLMUsage | None]:
        """texts maps chunk_id -> chunk text for every cited source."""
        validations: dict[str, FieldValidation] = {}
        consistency = consistency_problems(results)

        for spec in specs:
            r = results.get(spec.name)
            if r is None or r.value is None:
                note = r.notes if r else "field missing from results"
                validations[spec.name] = FieldValidation(field=spec.name, status="not_found",
                                                         reasons=[note[:200]])
                continue
            problems, warnings = format_problems(spec, r.value)
            cited = "\n\n".join(texts.get(s.chunk_id or "", "") for s in r.sources)
            if not r.sources:
                problems.append("no citation")
            elif not cited.strip():
                warnings.append("cited text unavailable; grounding not checked")
            else:
                problems += grounding_problems(_text(r.value), cited)
            problems += consistency.get(spec.name, [])
            validations[spec.name] = FieldValidation(
                field=spec.name, status="failed" if problems else "passed",
                reasons=problems, warnings=warnings,
            )

        usage = None
        to_judge = [s for s in specs if validations[s.name].status == "passed"]
        if self.llm and to_judge:
            try:
                usage = self._judge(bid_id, to_judge, results, texts, validations)
            except LLMError as exc:
                log.warning("validator_llm_unavailable", error=str(exc)[:200])
                for s in to_judge:
                    validations[s.name].warnings.append("LLM fact-check unavailable")

        log.info("validation_done", bid=bid_id, **summarize(validations).model_dump())
        return validations, usage

    def _judge(self, bid_id: str, specs: list[FieldSpec], results: dict[str, FieldResult],
               texts: dict[str, str], validations: dict[str, FieldValidation]) -> LLMUsage:
        blocks = []
        for spec in specs:
            r = results[spec.name]
            passages = "\n\n".join(
                f"[{s.file}, page {s.page}]\n{texts.get(s.chunk_id or '', '')[:PASSAGE_CHARS]}"
                for s in r.sources
            )
            blocks.append(f"### Field: {spec.name}\nMeaning: {spec.description} {spec.hints}\n"
                          f"Value: {_text(r.value)}\nPassages:\n{passages}")
        user = (f"Bid: {bid_id}\n\n" + "\n\n".join(blocks)
                + "\n\nReturn exactly one judgement per field.")
        output, usage = self.llm.structured(agent="validate", system=JUDGE_RULES, user=user,
                                            response_model=JudgeOutput, tier=self.tier,
                                            max_tokens=4096)
        for j in output.judgements:
            v = validations.get(j.field)
            if v is not None and v.status == "passed" and not j.supported:
                v.status = "failed"
                v.reasons.append(f"fact-check: {j.reason}")
                v.retry_queries = j.retry_queries[:3]
        return usage
