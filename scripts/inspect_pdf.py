"""Parse one PDF and print a per-page summary; also saves full JSON for eyeballing."""

import json
import sys
from pathlib import Path

from rfp.ingestion.cleaner import clean_pages
from rfp.ingestion.pdf_parser import parse_pdf

path = Path(sys.argv[1])
pages, errors = parse_pdf(path)
pages, removed = clean_pages(pages)
print("removed boilerplate:", removed)

print(f"{path.name}: {len(pages)} pages, errors={errors}")
for p in pages:
    print(
        f"\n--- page {p.page_number} | {len(p.text)} chars | {len(p.tables)} tables | empty={p.is_empty}"
    )
    print("headings:", p.headings[:6])
    print("text start:", p.text[:200].replace("\n", " / "))
    for t in p.tables[:1]:
        print("first table:\n" + "\n".join(t.markdown.splitlines()[:5]))

out = Path("data/processed") / f"{path.stem}.json"
out.write_text(json.dumps([p.model_dump() for p in pages], indent=2))
print(f"\nFull output saved to {out}")
