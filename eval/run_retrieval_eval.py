"""Retrieval evaluation: Recall@k, MRR and nDCG@10 for several search configurations."""

import json
import math
from pathlib import Path

from rfp.search.engine import SearchEngine, SearchResult
from rfp.search.store import ChunkStore
from rfp.settings import get_settings

EVAL_SET = Path("eval/retrieval_eval_set.jsonl")
RESULTS_DIR = Path("eval/results")
KS = (1, 3, 5, 10)

# (name, mode, settings overrides)
CONFIGS = [
    ("A. BM25 only", "sparse", {}),
    ("B. Dense only", "dense", {}),
    ("C. Hybrid (RRF)", "hybrid", {}),
    ("D. Hybrid + MiniLM rerank", "hybrid_rerank", {"rerank_model": "Xenova/ms-marco-MiniLM-L-6-v2"}),
    ("E. Hybrid + bge rerank", "hybrid_rerank", {"rerank_model": "BAAI/bge-reranker-base"}),
]


def is_hit(result: SearchResult, gold: list[dict]) -> bool:
    return any(
        g["file"].lower() in result.file_name.lower()
        and result.page_number == g["page"]
        and g["contains"].lower() in result.text.lower()
        for g in gold
    )


def evaluate(engine: SearchEngine, questions: list[dict], mode: str) -> tuple[dict, list[dict]]:
    rows = []
    for q in questions:
        results = engine.search(q["question"], top_k=10, mode=mode, bid_id=q.get("bid_id"))
        first = next((i for i, r in enumerate(results, start=1) if is_hit(r, q["gold"])), None)
        rows.append({"id": q["id"], "question": q["question"], "first_hit": first,
                     "top3": [r.citation for r in results[:3]]})
    n = len(rows)
    hits = [r["first_hit"] for r in rows if r["first_hit"]]
    metrics = {f"R@{k}": sum(1 for h in hits if h <= k) / n for k in KS}
    metrics["MRR"] = sum(1 / h for h in hits) / n
    metrics["nDCG@10"] = sum(1 / math.log2(h + 1) for h in hits) / n
    return metrics, rows


def main() -> None:
    questions = [json.loads(line) for line in EVAL_SET.read_text().splitlines() if line.strip()]
    base = get_settings().search
    store = ChunkStore()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    table = ["| Config | " + " | ".join([f"R@{k}" for k in KS] + ["MRR", "nDCG@10"]) + " |",
             "|---|" + "---|" * (len(KS) + 2)]
    details = {}
    try:
        for name, mode, overrides in CONFIGS:
            engine = SearchEngine(store, base.model_copy(update=overrides))
            metrics, rows = evaluate(engine, questions, mode)
            table.append(f"| {name} | " + " | ".join(f"{v:.2f}" for v in metrics.values()) + " |")
            details[name] = rows
            print(table[-1], flush=True)
    finally:
        store.close()

    report = f"Questions: {len(questions)}\n\n" + "\n".join(table) + "\n"
    (RESULTS_DIR / "retrieval_results.md").write_text(report)
    (RESULTS_DIR / "retrieval_details.json").write_text(json.dumps(details, indent=2))
    print("\n" + report)
    print(f"Per-question details (misses = first_hit null): {RESULTS_DIR / 'retrieval_details.json'}")


if __name__ == "__main__":
    main()