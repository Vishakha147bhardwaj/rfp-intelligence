"""LangGraph orchestration: plan -> parallel extraction -> reconcile -> validate <-> retry -> report."""

import uuid
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import structlog
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from rfp.agents.extraction import ExtractionAgent
from rfp.agents.reconciliation import ReconciliationAgent
from rfp.agents.registry import extractable_fields, fields_by_group, load_registry
from rfp.agents.report import ReportAgent, build_record
from rfp.agents.retrieval import RetrievalAgent
from rfp.agents.state import BidState, GroupTask
from rfp.agents.tracing import trace_step, write_trace
from rfp.agents.validator import ValidatorAgent, apply_validation
from rfp.llm.client import LLMClient
from rfp.schemas.agents import BidRecord, FieldResult
from rfp.search.engine import SearchEngine
from rfp.search.store import ChunkStore
from rfp.settings import PROJECT_ROOT, get_settings

log = structlog.get_logger()


class Deps:
    """Shared services. Kept OUT of the graph state (state holds only data)."""

    def __init__(self, store: ChunkStore, llm: LLMClient):
        self.store = store
        self.llm = llm
        self.cfg = get_settings().agents
        self.retrieval = RetrievalAgent(SearchEngine(store))
        self.groups, _ = load_registry()
        self.specs = {s.name: s for s in extractable_fields()}


def _nulls(names, reason: str) -> dict[str, FieldResult]:
    return {n: FieldResult(value=None, confidence=0.0, notes=reason) for n in names}


def build_graph(deps: Deps):
    cfg = deps.cfg

    # ---- orchestrator / planner ----
    def plan(state: BidState) -> dict:
        with trace_step(state["run_id"], "plan", bid=state["bid_id"]) as step:
            indexed = deps.store.count(bid_id=state["bid_id"])
            groups = list(fields_by_group()) if indexed else []
            step.set(chunks_indexed=indexed, groups=groups)
        errors = (
            []
            if indexed
            else [
                f"Bid {state['bid_id']} has no indexed chunks - run ingest/index first"
            ]
        )
        return {
            "groups": groups,
            "retry_counts": {},
            "to_validate": None,
            "trace": [step.event],
            "errors": errors,
        }

    def fan_out(state: BidState):
        if not state.get("groups"):
            return "report"
        return [
            Send(
                "extract_group",
                {"run_id": state["run_id"], "bid_id": state["bid_id"], "group": g},
            )
            for g in state["groups"]
        ]

    # ---- retrieval + extraction specialists (run in parallel) ----
    def extract_group(task: GroupTask) -> dict:
        group = task["group"]
        specs = fields_by_group()[group]
        with trace_step(task["run_id"], "extract", group=group) as step:
            try:
                bundle = deps.retrieval.gather(task["bid_id"], specs)
                step.set(searches=bundle.queries_run, evidence=len(bundle.evidence))
                agent = ExtractionAgent(
                    deps.llm, group, deps.groups[group], tier=cfg.extraction_tier
                )
                results, usage = agent.run(task["bid_id"], specs, bundle)
                step.add_usage(usage)
            except Exception as exc:
                log.exception("extract_failed", group=group)
                step.set(error=f"{type(exc).__name__}: {exc}")
                results = _nulls([s.name for s in specs], f"Extraction failed: {exc}")
            step.set(
                fields=len(specs),
                found=sum(r.value is not None for r in results.values()),
            )
        return {
            "results": results,
            "trace": [step.event],
            "errors": [step.event["error"]] if step.event["error"] else [],
        }

    # ---- addendum reconciliation ----
    def reconcile(state: BidState) -> dict:
        with trace_step(state["run_id"], "reconcile") as step:
            try:
                agent = ReconciliationAgent(deps.llm, deps.retrieval)
                updated, changes, usage = agent.run(
                    state["bid_id"], list(deps.specs.values()), state["results"]
                )
                step.add_usage(usage)
                step.set(changes=[c.field for c in changes])
            except Exception as exc:
                log.exception("reconcile_failed")
                step.set(error=f"{type(exc).__name__}: {exc}")
                updated, changes = {}, []
        return {
            "results": updated,
            "addendum_changes": {c.field: c for c in changes},
            "trace": [step.event],
            "errors": [step.event["error"]] if step.event["error"] else [],
        }

    # ---- validator / critic ----
    def validate(state: BidState) -> dict:
        names = state.get("to_validate") or list(deps.specs)
        specs = [deps.specs[n] for n in names]
        with trace_step(state["run_id"], "validate", fields=len(specs)) as step:
            chunk_ids = [
                s.chunk_id
                for n in names
                for s in state["results"]
                .get(n, FieldResult(value=None, confidence=0))
                .sources
            ]
            texts = deps.store.get_texts(chunk_ids)
            validations, usage = ValidatorAgent(deps.llm, tier=cfg.validator_tier).run(
                state["bid_id"], specs, state["results"], texts
            )
            step.add_usage(usage)
            step.set(failed=[n for n, v in validations.items() if v.status == "failed"])
        return {"validations": validations, "trace": [step.event]}

    def retryable(state: BidState) -> list[str]:
        return [
            n
            for n, v in state.get("validations", {}).items()
            if v.status == "failed"
            and state.get("retry_counts", {}).get(n, 0) < cfg.max_field_retries
        ]

    def after_validate(state: BidState) -> str:
        return "retry" if retryable(state) else "report"

    # ---- feedback loop: re-retrieve + re-extract only the failed fields ----
    def retry(state: BidState) -> dict:
        failed = retryable(state)
        counts = {n: state.get("retry_counts", {}).get(n, 0) + 1 for n in failed}
        results: dict[str, FieldResult] = {}
        changes = {}
        with trace_step(
            state["run_id"], "retry", fields=failed, attempts=counts
        ) as step:
            try:
                by_group = defaultdict(list)
                for name in failed:
                    by_group[deps.specs[name].group].append(deps.specs[name])
                searches = 0
                for group, specs in by_group.items():
                    vals = {s.name: state["validations"][s.name] for s in specs}
                    extra = {n: v.retry_queries for n, v in vals.items()}
                    feedback = {n: "; ".join(v.reasons) for n, v in vals.items()}
                    bundle = deps.retrieval.gather(
                        state["bid_id"], specs, extra_queries=extra
                    )
                    searches += bundle.queries_run
                    agent = ExtractionAgent(
                        deps.llm, group, deps.groups[group], tier=cfg.extraction_tier
                    )
                    out, usage = agent.run(
                        state["bid_id"], specs, bundle, feedback=feedback
                    )
                    step.add_usage(usage)
                    results.update(out)
                    for (
                        name,
                        new,
                    ) in out.items():  # a failed attempt must not erase an answer
                        old = state["results"].get(name)
                        if (
                            new.value is None
                            and new.notes.startswith("Rejected")
                            and old is not None
                            and old.value is not None
                        ):
                            results[name] = old
                            log.info(
                                "retry_kept_previous",
                                field=name,
                                reason="retry output rejected",
                            )
                sensitive = [
                    deps.specs[n] for n in failed if deps.specs[n].addendum_sensitive
                ]
                if sensitive:
                    merged = {**state["results"], **results}
                    updated, recon_changes, usage = ReconciliationAgent(
                        deps.llm, deps.retrieval
                    ).run(state["bid_id"], sensitive, merged)
                    step.add_usage(usage)
                    results.update({s.name: updated[s.name] for s in sensitive})
                    changes = {c.field: c for c in recon_changes}
                step.set(searches=searches)
            except Exception as exc:
                log.exception("retry_failed")
                step.set(error=f"{type(exc).__name__}: {exc}")
        return {
            "results": results,
            "retry_counts": counts,
            "to_validate": failed,
            "addendum_changes": changes,
            "trace": [step.event],
            "errors": [step.event["error"]] if step.event["error"] else [],
        }

    # ---- report ----
    def report(state: BidState) -> dict:
        with trace_step(state["run_id"], "report") as step:
            results = apply_validation(
                state.get("results", {}), state.get("validations", {})
            )
            changes = list(state.get("addendum_changes", {}).values())
            summary = None
            if any(r.value is not None for r in results.values()):
                try:
                    summary, usage = ReportAgent(
                        deps.llm, tier=cfg.extraction_tier
                    ).summarize(state["bid_id"], results, changes)
                    step.add_usage(usage)
                except Exception as exc:
                    step.set(error=f"summary failed: {exc}")
            record = build_record(
                state["bid_id"], results, summary, changes, state.get("validations", {})
            )
            step.set(
                validation=record.validation.model_dump(), addendum_changes=len(changes)
            )
        return {"record": record, "trace": [step.event]}

    graph = StateGraph(BidState)
    graph.add_node("plan", plan)
    graph.add_node("extract_group", extract_group)
    graph.add_node("reconcile", reconcile)
    graph.add_node("validate", validate)
    graph.add_node("retry", retry)
    graph.add_node("report", report)

    graph.add_edge(START, "plan")
    graph.add_conditional_edges("plan", fan_out, ["extract_group", "report"])
    graph.add_edge("extract_group", "reconcile")  # waits for all parallel branches
    graph.add_edge("reconcile", "validate")
    graph.add_conditional_edges(
        "validate", after_validate, {"retry": "retry", "report": "report"}
    )
    graph.add_edge("retry", "validate")
    graph.add_edge("report", END)
    return graph.compile()


def run_extraction(
    bid_id: str,
    store: ChunkStore,
    llm: LLMClient | None = None,
    out_dir: Path | None = None,
) -> tuple[BidRecord, Path, list[str]]:
    """Run the full graph for one bid. Writes outputs/<bid>.json and runs/<run_id>/trace."""
    run_id = f"{datetime.now(UTC):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
    started = datetime.now(UTC)
    graph = build_graph(Deps(store, llm or LLMClient()))
    final = graph.invoke({"run_id": run_id, "bid_id": bid_id}, {"recursion_limit": 50})

    record: BidRecord = final["record"]
    out_dir = out_dir or PROJECT_ROOT / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{bid_id}.json").write_text(record.model_dump_json(indent=2))

    run_dir = PROJECT_ROOT / "runs" / run_id
    write_trace(
        run_dir,
        final.get("trace", []),
        meta={
            "run_id": run_id,
            "bid_id": bid_id,
            "started": started.isoformat(),
            "duration_s": round((datetime.now(UTC) - started).total_seconds(), 1),
            "validation": record.validation.model_dump(),
        },
    )
    return record, run_dir, final.get("errors", [])
