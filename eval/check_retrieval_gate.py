"""CI quality gate: fail the build if retrieval quality drops below the thresholds."""

import json
import sys
from pathlib import Path

CONFIG = "D. Hybrid + MiniLM rerank"   # the production search configuration
MIN_RECALL_AT_5 = 0.90
MIN_MRR = 0.75


def main() -> None:
    details = json.loads(Path("eval/results/retrieval_details.json").read_text())
    rows = details[CONFIG]
    hits = [r["first_hit"] for r in rows if r["first_hit"]]
    recall5 = sum(1 for h in hits if h <= 5) / len(rows)
    mrr = sum(1 / h for h in hits) / len(rows)
    print(f"{CONFIG}: R@5={recall5:.2f} (min {MIN_RECALL_AT_5}), MRR={mrr:.2f} (min {MIN_MRR})")
    if recall5 < MIN_RECALL_AT_5 or mrr < MIN_MRR:
        print("FAIL: retrieval quality is below the gate")
        sys.exit(1)
    print("PASS")


if __name__ == "__main__":
    main()
