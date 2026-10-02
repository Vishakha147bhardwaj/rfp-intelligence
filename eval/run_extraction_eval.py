"""Extraction evaluation: compare outputs/<bid>.json with eval/extraction_gold/<bid>.json."""

import json
import sys
from pathlib import Path

from rapidfuzz import fuzz

from rfp.agents.validator import _date_spans, _time_spans

GOLD_DIR = Path("eval/extraction_gold")
OUTPUT_DIR = Path("outputs")
RESULTS = Path("eval/results/extraction_results.md")
LIST_THRESHOLD = 85      # fuzzy partial-match score for a list item to count
TEXT_THRESHOLD = 90


def norm(text: str) -> str:
    text = text.lower().replace("–", "-").replace("—", "-")
    return " ".join(text.split())


def as_text(value) -> str:
    if value is None:
        return ""
    return "; ".join(value) if isinstance(value, list) else str(value)


def has_alternative(alternatives: str, text: str) -> bool:
    """'a|b' -> True if any alternative appears in text."""
    return any(norm(a) in text for a in alternatives.split("|"))


def score_field(gold: dict, value) -> tuple[float, str]:
    """Return (score 0..1, detail)."""
    text = norm(as_text(value))
    if "keywords" in gold:
        found = [k for k in gold["keywords"] if has_alternative(k, text)]
        missing = [k for k in gold["keywords"] if k not in found]
        return len(found) / len(gold["keywords"]), (f"missing {missing}" if missing else "")
    if "datetime" in gold:
        want = {d for *_, d in _date_spans(gold["datetime"])} | {t for *_, t in _time_spans(gold["datetime"])}
        got = {d for *_, d in _date_spans(as_text(value))} | {t for *_, t in _time_spans(as_text(value))}
        missing = want - got
        return (len(want) - len(missing)) / len(want), (f"missing {sorted(map(str, missing))}" if missing else "")
    if "list" in gold:
        items = [norm(v) for v in (value if isinstance(value, list) else [as_text(value)])]
        matched = [g for g in gold["list"]
                   if any(fuzz.partial_ratio(norm(alt), item) >= LIST_THRESHOLD
                          for alt in g.split("|") for item in items)]
        missing = [g for g in gold["list"] if g not in matched]
        return len(matched) / len(gold["list"]), (f"missing {missing}" if missing else "")
    if "text" in gold:
        ratio = fuzz.token_set_ratio(norm(gold["text"]), text)
        return (1.0 if ratio >= TEXT_THRESHOLD else ratio / 100), f"similarity {ratio:.0f}"
    raise ValueError(f"unknown gold entry: {gold}")


def evaluate_bid(bid: str) -> list[dict]:
    gold = json.loads((GOLD_DIR / f"{bid}.json").read_text())
    fields = json.loads((OUTPUT_DIR / f"{bid}.json").read_text())["fields"]
    rows = []
    for name, g in gold.items():
        result = fields.get(name, {})
        value = result.get("value")
        sources = [s["file"] for s in result.get("sources", [])]
        if g.get("null"):
            category, score, detail = ("correct", 1.0, "") if value is None else ("false_positive", 0.0, "should be null")
        elif value is None:
            category, score, detail = ("correct", 1.0, "null accepted") if g.get("accept_null") else ("missed", 0.0, "")
        else:
            score, detail = score_field(g, value)
            category = "correct" if score >= 1.0 else ("partial" if score > 0 else "wrong")
        cite_ok = None
        if "source" in g and value is not None:
            cite_ok = any(has_alternative(g["source"], norm(f)) for f in sources)
        rows.append({"bid": bid, "field": name, "category": category, "score": score,
                     "cite_ok": cite_ok, "detail": detail})
    return rows


def main() -> None:
    bids = sys.argv[1:] or sorted(p.stem for p in GOLD_DIR.glob("*.json"))
    rows = [r for bid in bids for r in evaluate_bid(bid)]

    lines = ["| Bid | Field | Result | Score | Citation | Detail |", "|---|---|---|---|---|---|"]
    for r in rows:
        cite = "" if r["cite_ok"] is None else ("ok" if r["cite_ok"] else "WRONG")
        lines.append(f"| {r['bid']} | {r['field']} | {r['category']} | {r['score']:.2f} | {cite} | {r['detail']} |")

    summary = ["", "| Bid | Fields | Correct | Partial | Wrong | Missed | False positive | Accuracy | Avg score |",
               "|---|---|---|---|---|---|---|---|---|"]
    for bid in bids + ["ALL"]:
        sel = [r for r in rows if bid == "ALL" or r["bid"] == bid]
        count = {c: sum(r["category"] == c for r in sel)
                 for c in ("correct", "partial", "wrong", "missed", "false_positive")}
        summary.append(f"| {bid} | {len(sel)} | {count['correct']} | {count['partial']} | {count['wrong']} | "
                       f"{count['missed']} | {count['false_positive']} | {count['correct'] / len(sel):.0%} | "
                       f"{sum(r['score'] for r in sel) / len(sel):.2f} |")

    report = "\n".join(lines + summary) + "\n"
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(report)
    print(report)


if __name__ == "__main__":
    main()
