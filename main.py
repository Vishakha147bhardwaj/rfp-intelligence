"""RFP Intelligence Platform - command-line entry point."""

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from rfp.ingestion.pipeline import ingest_folder, load_processed
from rfp.search.chunker import chunk_document
from rfp.search.indexer import index_documents
from rfp.search.store import ChunkStore
from rich.text import Text
from rfp.search.engine import SearchEngine

app = typer.Typer(help="RFP Intelligence Platform: search and extract bid documents.")
console = Console()


@app.callback()
def main() -> None:
    """RFP Intelligence Platform CLI."""


@app.command()
def ingest(
    folder: Path = typer.Argument(..., exists=True, file_okay=False, help="Bid folder, e.g. data/bids/Bid1"),
    out: Path = typer.Option(Path("data/processed"), help="Where to write parsed JSON"),
) -> None:
    """Parse and clean every file in a bid folder; save JSON and an ingestion report."""
    docs, report = ingest_folder(folder, out)
    by_name = {d.file_name: d for d in docs}

    table = Table(title=f"Ingestion report: {report.bid_id}")
    for column in ("file", "status", "doc_type", "add #", "pages", "empty", "doc_date"):
        table.add_column(column)
    for r in report.files:
        d = by_name.get(r.file_name)
        table.add_row(
            r.file_name[:48],
            r.status,
            r.doc_type.value if r.doc_type else "-",
            str(d.addendum_number) if d and d.addendum_number else "",
            str(r.pages),
            str(len(r.empty_pages)),
            str(d.doc_date) if d and d.doc_date else "",
        )
    console.print(table)
    console.print(f"Saved to {out / report.bid_id}")

@app.command()
def chunk(
    bid: str = typer.Argument(..., help="Bid id, e.g. Bid1 (run ingest first)"),
    processed: Path = typer.Option(Path("data/processed"), help="Folder with ingested JSON"),
    find: str = typer.Option("", help="Only show sample chunks containing this text"),
    show: int = typer.Option(3, help="How many sample chunks to print"),
) -> None:
    """Chunk an ingested bid; print stats and sample chunks; save chunks.jsonl."""
    bid_dir = processed / bid
    docs = load_processed(bid_dir)
    if not docs:
        console.print(f"No ingested documents in {bid_dir}. Run ingest first.", style="red")
        raise typer.Exit(1)

    all_chunks = []
    table = Table(title=f"Chunks: {bid}")
    for column in ("file", "chunks", "tables", "avg tok", "max tok", "sections"):
        table.add_column(column)
    for doc in docs:
        chunks = chunk_document(doc)
        all_chunks += chunks
        sizes = [c.n_tokens for c in chunks] or [0]
        table.add_row(doc.file_name[:48], str(len(chunks)), str(sum(c.is_table for c in chunks)),
                      str(sum(sizes) // len(sizes)), str(max(sizes)), str(len({c.section for c in chunks})))
    console.print(table)
    (bid_dir / "chunks.jsonl").write_text("\n".join(c.model_dump_json() for c in all_chunks))

    samples = [c for c in all_chunks if find.lower() in c.text.lower()] if find else all_chunks
    for c in samples[:show]:
        console.rule(f"{c.file_name[:40]} | p.{c.page_number} | {c.n_tokens} tokens")
        console.print(c.context_header, markup=False)
        console.print(c.text[:700], markup=False)

@app.command()
def index(
    folder: Path = typer.Argument(..., exists=True, file_okay=False, help="Bid folder, e.g. data/bids/Bid1"),
    out: Path = typer.Option(Path("data/processed"), help="Where to write parsed JSON"),
    force: bool = typer.Option(False, help="Re-index even unchanged files"),
) -> None:
    """Ingest a bid folder and add it to the search index (incremental)."""
    docs, _ = ingest_folder(folder, out)
    store = ChunkStore()
    try:
        report = index_documents(docs, store, force=force)
        console.print(f"Indexed: {report.indexed}")
        console.print(f"Skipped (unchanged): {report.skipped}")
        if report.removed:
            console.print(f"Removed: {report.removed}")
        console.print(f"Chunks in index for {folder.name}: {store.count(bid_id=folder.name)} "
                      f"| total: {store.count()}")
    finally:
        store.close()    
@app.command()
def search(
    query: str = typer.Argument(..., help="What to search for"),
    bid: str | None = typer.Option(None, help="Only this bid, e.g. Bid2"),
    doc_type: str | None = typer.Option(None, help="rfp | addendum | bid_page | specs | affidavit"),
    top_k: int = typer.Option(5, "--top-k", "-k"),
    mode: str = typer.Option("hybrid_rerank", help="dense | sparse | hybrid | hybrid_rerank"),
) -> None:
    """Search the indexed bids and show cited results."""
    store = ChunkStore()
    try:
        results = SearchEngine(store).search(query, top_k=top_k, mode=mode, bid_id=bid, doc_type=doc_type)
    finally:
        store.close()

    table = Table(title=f"{query}  [{mode}]", show_lines=True)
    for column in ("#", "score", "citation", "d/s rank", "snippet"):
        table.add_column(column)
    for i, r in enumerate(results, start=1):
        ranks = f"{r.dense_rank or '-'}/{r.sparse_rank or '-'}"
        snippet = " ".join(r.text.split())[:220]
        table.add_row(str(i), f"{r.score:.3f}", Text(r.citation), ranks, Text(snippet))
    console.print(table)
@app.command()
def serve(
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(8000),
    reload: bool = typer.Option(False, help="Auto-restart on code changes (development)"),
) -> None:
    """Start the REST API. Interactive docs at http://HOST:PORT/docs"""
    import uvicorn

    uvicorn.run("rfp.api.app:app", host=host, port=port, reload=reload)
@app.command("llm-check")
def llm_check() -> None:
    """Call Claude once per model tier with a tiny structured task to verify key and models."""
    from pydantic import BaseModel

    from rfp.llm.client import LLMClient

    class Check(BaseModel):
        bid_number: str | None
        due_date: str | None

    client = LLMClient()
    text = "ADDENDUM No. 2 to RFP JA-207652. The new due date for this RFP will be July 9, 2024 at 2:00 PM CST."
    for tier in ("fast", "smart"):
        result, usage = client.structured(
            agent="llm_check",
            system="Extract the requested fields from the text. Use null if a field is absent.",
            user=text,
            response_model=Check,
            tier=tier,
        )
        console.print(f"[{tier}] {result.model_dump()}  |  {usage.input_tokens} in, "
                      f"{usage.output_tokens} out, {usage.latency_ms} ms", markup=False)
@app.command("extract-group")
def extract_group(
    bid: str = typer.Argument(..., help="Bid id, e.g. Bid1"),
    group: str = typer.Option("dates_logistics", help="dates_logistics | commercial_legal | product_specs"),
) -> None:
    """Run retrieval + one extraction agent for one field group (development helper)."""
    from rfp.agents.extraction import ExtractionAgent
    from rfp.agents.registry import fields_by_group, load_registry
    from rfp.agents.retrieval import RetrievalAgent
    from rfp.llm.client import LLMClient
    from rfp.settings import get_settings

    groups, _ = load_registry()
    if group not in groups:
        console.print(f"Unknown group. Choose one of: {', '.join(groups)}", style="red")
        raise typer.Exit(1)
    specs = fields_by_group()[group]

    store = ChunkStore()
    try:
        bundle = RetrievalAgent(SearchEngine(store)).gather(bid, specs)
    finally:
        store.close()

    agent = ExtractionAgent(LLMClient(), group, groups[group], tier=get_settings().agents.extraction_tier)
    results, usage = agent.run(bid, specs, bundle)

    table = Table(title=f"{bid} - {group}", show_lines=True)
    for column in ("field", "value", "conf", "sources", "notes"):
        table.add_column(column)
    for name, r in results.items():
        value = "\n".join(r.value) if isinstance(r.value, list) else (r.value or "-")
        sources = "\n".join(f"{s.file[:35]} p.{s.page}" for s in r.sources)
        table.add_row(name, Text(value), f"{r.confidence:.2f}", Text(sources), Text(r.notes[:160]))
    console.print(table)
    if usage:
        console.print(f"{bundle.queries_run} searches, {len(bundle.evidence)} evidence passages | "
                      f"{usage.model}: {usage.input_tokens} in, {usage.output_tokens} out, "
                      f"{usage.latency_ms} ms", markup=False)
@app.command()
def reconcile(bid: str = typer.Argument(..., help="Bid id, e.g. Bid1")) -> None:
    """Extract the addendum-sensitive fields, then reconcile them against addendums (dev helper)."""
    from rfp.agents.extraction import ExtractionAgent
    from rfp.agents.reconciliation import ReconciliationAgent
    from rfp.agents.registry import extractable_fields
    from rfp.agents.retrieval import RetrievalAgent
    from rfp.llm.client import LLMClient
    from rfp.settings import get_settings

    specs = [s for s in extractable_fields() if s.addendum_sensitive]
    llm = LLMClient()
    store = ChunkStore()
    try:
        retrieval = RetrievalAgent(SearchEngine(store))
        bundle = retrieval.gather(bid, specs)
        extracted, _ = ExtractionAgent(llm, "addendum_sensitive", "fields that addendums may change",
                                       tier=get_settings().agents.extraction_tier).run(bid, specs, bundle)
        final, changes, usage = ReconciliationAgent(llm, retrieval).run(bid, specs, extracted)
    finally:
        store.close()

    def show(value) -> str:
        return "\n".join(value) if isinstance(value, list) else (value or "-")

    table = Table(title=f"{bid} - reconciliation", show_lines=True)
    for column in ("field", "extracted", "final", "notes"):
        table.add_column(column)
    for spec in specs:
        table.add_row(spec.name, Text(show(extracted[spec.name].value)),
                      Text(show(final[spec.name].value)), Text(final[spec.name].notes[:200]))
    console.print(table)

    log_table = Table(title="Addendum change log")
    for column in ("field", "original", "new", "addendum", "source"):
        log_table.add_column(column)
    for c in changes:
        log_table.add_row(c.field, Text(show(c.old_value)), Text(show(c.new_value)),
                          str(c.addendum_number), Text(f"{c.source.file[:40]} p.{c.source.page}"))
    console.print(log_table if changes else "No addendum changes.")
    if usage:
        console.print(f"reconcile: {usage.model}, {usage.input_tokens} in, {usage.output_tokens} out, "
                      f"{usage.latency_ms} ms", markup=False)
@app.command()
def validate(
    bid: str = typer.Argument(..., help="Bid id, e.g. Bid2"),
    group: str = typer.Option("commercial_legal", help="Field group to extract and validate"),
) -> None:
    """Extract one field group, then run the validator on it (development helper)."""
    from rfp.agents.extraction import ExtractionAgent
    from rfp.agents.registry import fields_by_group, load_registry
    from rfp.agents.retrieval import RetrievalAgent
    from rfp.agents.validator import ValidatorAgent
    from rfp.llm.client import LLMClient
    from rfp.settings import get_settings

    groups, _ = load_registry()
    specs = fields_by_group()[group]
    llm = LLMClient()
    store = ChunkStore()
    try:
        bundle = RetrievalAgent(SearchEngine(store)).gather(bid, specs)
    finally:
        store.close()

    cfg = get_settings().agents
    results, _ = ExtractionAgent(llm, group, groups[group], tier=cfg.extraction_tier).run(bid, specs, bundle)
    texts = {e.chunk_id: e.text for e in bundle.evidence}
    validations, usage = ValidatorAgent(llm, tier=cfg.validator_tier).run(bid, specs, results, texts)

    table = Table(title=f"{bid} - {group} - validation", show_lines=True)
    for column in ("field", "value", "status", "reasons / warnings", "retry queries"):
        table.add_column(column)
    for spec in specs:
        r, v = results[spec.name], validations[spec.name]
        value = "\n".join(r.value) if isinstance(r.value, list) else (r.value or "-")
        detail = "\n".join(v.reasons + [f"(warning) {w}" for w in v.warnings])
        table.add_row(spec.name, Text(value[:150]), v.status, Text(detail[:250]), Text("\n".join(v.retry_queries)))
    console.print(table)
    if usage:
        console.print(f"validate: {usage.model}, {usage.input_tokens} in, {usage.output_tokens} out, "
                      f"{usage.latency_ms} ms", markup=False)
@app.command()
def extract(
    folder: Path = typer.Argument(..., exists=True, file_okay=False, help="Bid folder, e.g. data/bids/Bid1"),
) -> None:
    """Full pipeline for one bid: ingest + index (incremental), then multi-agent extraction to JSON."""
    from rfp.agents.graph import run_extraction

    docs, _ = ingest_folder(folder, Path("data/processed"))
    store = ChunkStore()
    try:
        index_documents(docs, store)
        record, run_dir, errors = run_extraction(folder.name, store)
    finally:
        store.close()

    table = Table(title=f"{record.bid_id} - extracted fields", show_lines=True)
    for column in ("field", "value", "conf", "source"):
        table.add_column(column)
    for name, r in record.fields.items():
        if isinstance(r.value, list):
            more = f"\n... (+{len(r.value) - 8} more)" if len(r.value) > 8 else ""
            value = "\n".join(r.value[:8]) + more
        else:
            value = r.value or "-"
        source = f"{r.sources[0].file[:35]} p.{r.sources[0].page}" if r.sources else ""
        table.add_row(name, Text(value[:300]), f"{r.confidence:.2f}", Text(source))
    console.print(table)
    v = record.validation
    console.print(f"Validation: {v.passed} passed, {v.failed} failed, {v.not_found} not found | "
                  f"{len(record.addendum_changes)} addendum change(s)")
    for e in errors:
        console.print(f"error: {e}", style="red", markup=False)
    console.print(f"JSON: outputs/{record.bid_id}.json | Trace: {run_dir}", markup=False)

@app.command()
def ask(
    question: str = typer.Argument(..., help="A question about the bids"),
    log: bool = typer.Option(True, help="Append the answer to outputs/qa_log.md"),
) -> None:
    """Answer a question about the indexed bids, with citations (Q&A mode)."""
    from rfp.agents.qa import run_question

    store = ChunkStore()
    try:
        result = run_question(question, store, log_answer=log)
    finally:
        store.close()

    console.rule(f"Q: {question}")
    console.print(result.answer, markup=False)
    for c in result.citations:
        console.print(f"  [{c.n}] {c.file}, p.{c.page} ({c.bid_id})", markup=False, style="dim")
    console.print(f"bids: {', '.join(result.bid_ids)} | run: {result.run_id}", style="dim", markup=False)
if __name__ == "__main__":
    app()