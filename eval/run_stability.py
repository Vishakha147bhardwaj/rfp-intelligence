"""Run the full extraction N times per bid; report how often each field is correct.

Usage: uv run python eval/run_stability.py [RUNS] [BID ...]     e.g.  3 Bid1 Bid2
"""

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from run_extraction_eval import evaluate_bid  # noqa: E402

from rfp.agents.graph import run_extraction  # noqa: E402
from rfp.search.store import ChunkStore  # noqa: E402

RUNS = int(sys.argv[1]) if len(sys.argv) > 1 else 3
BIDS = sys.argv[2:] or ["Bid1", "Bid2"]
OUT = Path("eval/results/stability")


def main() -> None:
    per_field: dict[tuple[str, str], list[bool]] = defaultdict(list)
    store = ChunkStore()
    try:
        for bid in BIDS:
            for i in range(1, RUNS + 1):
                out_dir = OUT / f"run{i}"
                print(f"--- {bid} run {i}/{RUNS}", flush=True)
                run_extraction(bid, store, out_dir=out_dir)
                for row in evaluate_bid(bid, out_dir / f"{bid}.json"):
                    per_field[(bid, row["field"])].append(row["category"] == "correct")
    finally:
        store.close()

    lines = ["| Bid | Field | Correct runs |", "|---|---|---|"]
    for (bid, field), oks in per_field.items():
        flag = "" if all(oks) else "  <- unstable"
        lines.append(f"| {bid} | {field} | {sum(oks)}/{len(oks)}{flag} |")
    correct = sum(sum(v) for v in per_field.values())
    total = sum(len(v) for v in per_field.values())
    unstable = sum(not all(v) for v in per_field.values())
    lines += ["", f"Overall: {correct}/{total} field-runs correct ({correct / total:.0%}); "
                  f"{unstable} field(s) were not correct in every run."]
    report = "\n".join(lines) + "\n"
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "stability_results.md").write_text(report)
    print(report)


if __name__ == "__main__":
    main()
