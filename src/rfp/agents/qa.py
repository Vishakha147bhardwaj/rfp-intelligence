"""Q&A mode: plan the question -> retrieve evidence per bid (parallel) -> cited answer -> citation check."""

import json
import operator
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, TypedDict

import structlog
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from pydantic import BaseModel, Field

from rfp.agents.reconciliation import BASE_TYPES
from rfp.agents.semantic_cache import SemanticCache, index_fingerprint
from rfp.agents.tracing import trace_step, write_trace
from rfp.llm.client import LLMClient
from rfp.search.engine import SearchEngine
from rfp.search.indexer import load_manifest
from rfp.search.store import ChunkStore
from rfp.settings import PROJECT_ROOT, get_settings

log = structlog.get_logger()

NOT_FOUND = "Not found in documents."
PER_QUERY_K = 4
PER_BID_EVIDENCE = 8
QA_CANDIDATES = 15  # rerank depth for Q&A searches (interactive search uses 30)
CITATION = re.compile(r"\[(\d+)\]")

CHANGE_CUE = re.compile(
    r"\b(?:new|revised|amended|updated|extend(?:ed|s)?|changed?|replaced?|instead)\b\s*",
    re.IGNORECASE,
)
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def change_sentences(text: str, limit: int = 3) -> list[str]:
    """Sentences that describe a change, with the change word removed so they read like the original."""
    sentences = SENTENCE_END.split(" ".join(text.split()))
    picked = [CHANGE_CUE.sub("", s).strip() for s in sentences if CHANGE_CUE.search(s)]
    return [s for s in picked if len(s) > 15][:limit]


PLAN_RULES = """You plan how to answer a question about bid / RFP documents.
You are given the available bids (id: title). Choose the bid ids the question is about - all of
them if the question compares bids or does not say which bid. Write 2-4 short, specific search
queries (keywords, not full sentences) that would find the answer in RFP documents. Set
addendum_only=true when the question asks what an addendum changed or added."""

ANSWER_RULES = """Answer the question using ONLY the numbered evidence passages.
- After every claim, cite passage numbers in square brackets, e.g. [2] or [1][3].
- If an addendum changes something, give the final (latest) value and say which addendum changed it.
- When comparing bids, cover each bid separately and name it.
- If the evidence does not contain the answer, set found=false and answer exactly: Not found in documents.
- Be concise (1-6 sentences). Never guess or use outside knowledge."""


class QuestionPlan(BaseModel):
    bid_ids: list[str] = Field(description="Ids of the bids the question is about")
    queries: list[str] = Field(description="2-4 short keyword search queries")
    addendum_only: bool = Field(
        default=False, description="True if asking what addendums changed"
    )


class AnswerDraft(BaseModel):
    found: bool = Field(description="False if the evidence does not contain the answer")
    answer: str = Field(
        description="1-6 sentences, citing passages like [1] after each claim"
    )


class Citation(BaseModel):
    n: int
    bid_id: str
    file: str
    page: int
    snippet: str


class QAAnswer(BaseModel):
    run_id: str
    question: str
    answer: str
    found: bool
    bid_ids: list[str]
    citations: list[Citation] = Field(default_factory=list)
    cached: bool = False


class QAState(TypedDict, total=False):
    run_id: str
    question: str
    plan: QuestionPlan
    evidence: Annotated[list[dict[str, Any]], operator.add]
    result: QAAnswer
    trace: Annotated[list[dict[str, Any]], operator.add]


# ---------- pure helpers (unit-tested) ----------


def bid_catalog() -> dict[str, str]:
    """bid_id -> readable title (from outputs/<bid>.json when available)."""
    catalog = {}
    for bid in load_manifest():
        title = bid
        path = PROJECT_ROOT / "outputs" / f"{bid}.json"
        if path.exists():
            fields = json.loads(path.read_text()).get("fields", {})
            name = (fields.get("Title") or {}).get("value")
            org = (fields.get("company_name") or {}).get("value")
            title = " - ".join(str(x) for x in (name, org) if x) or bid
        catalog[bid] = title
    return catalog


def resolve_bids(requested: list[str], known: list[str]) -> list[str]:
    """Keep only real bid ids; if none survive, use all bids."""
    chosen = [b for b in requested if b in known]
    return chosen or list(known)


def finalize_answer(
    draft: AnswerDraft, evidence: list[dict]
) -> tuple[str, list[Citation], bool]:
    """Remove citations to passages that don't exist; no valid citation -> Not found."""
    n_passages = len(evidence)
    text = CITATION.sub(
        lambda m: m.group(0) if 1 <= int(m.group(1)) <= n_passages else "", draft.answer
    )
    used = sorted({int(n) for n in CITATION.findall(text)})
    if not draft.found or not used:
        return NOT_FOUND, [], False
    citations = []
    for n in used:
        e = evidence[n - 1]
        citations.append(
            Citation(
                n=n,
                bid_id=e["bid_id"],
                file=e["file_name"],
                page=e["page_number"],
                snippet=" ".join(e["text"].split())[:200],
            )
        )
    return " ".join(text.split()), citations, True


def append_qa_log(result: QAAnswer, path: Path | None = None) -> Path:
    path = path or PROJECT_ROOT / "outputs" / "qa_log.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    sources = (
        "\n".join(
            f"  - [{c.n}] {c.file}, p.{c.page} ({c.bid_id})" for c in result.citations
        )
        or "  - none"
    )
    entry = (
        f"## Q: {result.question}\n\n**Answer:** {result.answer}\n\n**Sources:**\n{sources}\n\n"
        f"_run {result.run_id} | bids: {', '.join(result.bid_ids)}_\n\n---\n\n"
    )
    with path.open("a") as f:
        f.write(entry)
    return path


# ---------- the graph ----------


def build_qa_graph(store: ChunkStore, llm: LLMClient):
    engine = SearchEngine(store)

    def plan(state: QAState) -> dict:
        catalog = bid_catalog()
        with trace_step(state["run_id"], "qa_plan") as step:
            listing = "\n".join(f"- {bid}: {title}" for bid, title in catalog.items())
            output, usage = llm.structured(
                agent="qa_plan",
                system=PLAN_RULES,
                user=f"Available bids:\n{listing}\n\nQuestion: {state['question']}",
                response_model=QuestionPlan,
                tier="fast",
                max_tokens=400,
            )
            step.add_usage(usage)
            output.bid_ids = resolve_bids(output.bid_ids, list(catalog))
            output.queries = output.queries[:4]
            step.set(
                bids=output.bid_ids,
                queries=output.queries,
                addendum_only=output.addendum_only,
            )
        return {"plan": output, "trace": [step.event]}

    def fan_out(state: QAState):
        return [
            Send(
                "retrieve",
                {
                    "run_id": state["run_id"],
                    "question": state["question"],
                    "plan": state["plan"],
                    "bid_id": bid,
                },
            )
            for bid in state["plan"].bid_ids
        ]

    def retrieve(task: dict) -> dict:
        bid, plan_ = task["bid_id"], task["plan"]
        with trace_step(task["run_id"], "qa_retrieve", bid=bid) as step:
            if (
                plan_.addendum_only
                and store.count(bid_id=bid, doc_type="addendum") == 0
            ):
                step.set(skipped="bid has no addendums")
                return {"evidence": [], "trace": [step.event]}

            best: dict[str, dict] = {}
            followups: list[dict] = []

            def search(query: str, k: int, doc_type=None):
                return engine.search(
                    query,
                    top_k=k,
                    bid_id=bid,
                    doc_type=doc_type,
                    candidates=QA_CANDIDATES,
                )

            def add(results) -> None:
                for r in results:
                    item = r.model_dump()
                    if (
                        r.chunk_id not in best
                        or item["score"] > best[r.chunk_id]["score"]
                    ):
                        best[r.chunk_id] = item

            queries = [task["question"], *plan_.queries]
            searches = 0
            for q in queries:
                add(search(q, PER_QUERY_K))
                searches += 1

            if plan_.addendum_only:
                addendum_hits = []
                for q in queries:
                    hits = search(q, PER_QUERY_K, doc_type="addendum")
                    searches += 1
                    add(hits)
                    addendum_hits += hits
                # Hop 2: use each top addendum passage AS the query, to find the ORIGINAL text it changes
                top = sorted(
                    {h.chunk_id: h for h in addendum_hits}.values(),
                    key=lambda h: h.score,
                    reverse=True,
                )[:2]
                for hit in top:
                    for sentence in change_sentences(hit.text) or [hit.text[:400]]:
                        for r in search(sentence, 2, doc_type=BASE_TYPES):
                            followups.append(r.model_dump())
                        searches += 1

            ranked = sorted(best.values(), key=lambda e: e["score"], reverse=True)
            evidence, seen = [], set()
            for item in followups + ranked:  # follow-ups are guaranteed a place
                if item["chunk_id"] not in seen:
                    seen.add(item["chunk_id"])
                    evidence.append(item)
            evidence = evidence[: PER_BID_EVIDENCE + len(followups)]
            step.set(
                searches=searches, evidence=len(evidence), followups=len(followups)
            )
        return {"evidence": evidence, "trace": [step.event]}

    def answer(state: QAState) -> dict:
        evidence = sorted(
            state.get("evidence", []), key=lambda e: (e["bid_id"], -e["score"])
        )
        with trace_step(state["run_id"], "qa_answer", passages=len(evidence)) as step:
            if not evidence:
                text, citations, found = NOT_FOUND, [], False
            else:
                passages = "\n\n".join(
                    f"[{i}] {e['bid_id']} | {e['file_name']} | page {e['page_number']} | {e['doc_type']}"
                    + (f" #{e['addendum_number']}" if e.get("addendum_number") else "")
                    + f"\n{e['text']}"
                    for i, e in enumerate(evidence, start=1)
                )
                draft, usage = llm.structured(
                    agent="qa_answer",
                    system=ANSWER_RULES,
                    user=f"Question: {state['question']}\n\nEvidence:\n\n{passages}",
                    response_model=AnswerDraft,
                    tier="smart",
                    max_tokens=1200,
                )
                step.add_usage(usage)
                text, citations, found = finalize_answer(draft, evidence)
            step.set(found=found, citations=len(citations))
        result = QAAnswer(
            run_id=state["run_id"],
            question=state["question"],
            answer=text,
            found=found,
            bid_ids=state["plan"].bid_ids,
            citations=citations,
        )
        return {"result": result, "trace": [step.event]}

    graph = StateGraph(QAState)
    graph.add_node("plan", plan)
    graph.add_node("retrieve", retrieve)
    graph.add_node("answer", answer)
    graph.add_edge(START, "plan")
    graph.add_conditional_edges("plan", fan_out, ["retrieve"])
    graph.add_edge("retrieve", "answer")
    graph.add_edge("answer", END)
    return graph.compile()


def run_question(
    question: str,
    store: ChunkStore,
    llm: LLMClient | None = None,
    log_answer: bool = True,
    use_cache: bool = True,
) -> QAAnswer:
    run_id = f"qa-{datetime.now(UTC):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
    started = datetime.now(UTC)
    cache = SemanticCache() if use_cache and get_settings().cache.enabled else None
    fingerprint = index_fingerprint()

    if cache is not None:
        hit, similarity = cache.lookup(question, fingerprint)
        if hit is not None:
            result = QAAnswer(
                **{**hit, "run_id": run_id, "question": question, "cached": True}
            )
            write_trace(
                PROJECT_ROOT / "runs" / run_id,
                [],
                meta={
                    "run_id": run_id,
                    "mode": "qa",
                    "question": question,
                    "started": started.isoformat(),
                    "duration_s": round(
                        (datetime.now(UTC) - started).total_seconds(), 1
                    ),
                    "found": result.found,
                    "cache_hit": True,
                    "cache_similarity": round(similarity, 4),
                },
            )
            if log_answer:
                append_qa_log(result)
            return result

    graph = build_qa_graph(store, llm or LLMClient())
    final = graph.invoke({"run_id": run_id, "question": question})
    result: QAAnswer = final["result"]
    write_trace(
        PROJECT_ROOT / "runs" / run_id,
        final.get("trace", []),
        meta={
            "run_id": run_id,
            "mode": "qa",
            "question": question,
            "started": started.isoformat(),
            "duration_s": round((datetime.now(UTC) - started).total_seconds(), 1),
            "found": result.found,
            "cache_hit": False,
        },
    )
    if cache is not None:
        cache.store(
            question,
            result.model_dump(exclude={"run_id", "question", "cached"}),
            fingerprint,
        )
    if log_answer:
        append_qa_log(result)
    return result
