"""RFP Intelligence Platform - command-line entry point."""

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from rfp.ingestion.pipeline import ingest_folder, load_processed
from rfp.search.chunker import chunk_document
from rfp.search.indexer import index_documents
from rfp.search.store import ChunkStore

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
if __name__ == "__main__":
    app()