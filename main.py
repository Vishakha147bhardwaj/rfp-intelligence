"""RFP Intelligence Platform - command-line entry point."""

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from rfp.ingestion.pipeline import ingest_folder

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


if __name__ == "__main__":
    app()