"""Semantic cache for Q&A: a question with the same meaning returns the stored cited answer.

Safeguards against wrong hits:
- guard tokens: every token containing a digit (bid1, 2, ja-207652) must match exactly;
- index fingerprint: entries are ignored once the indexed documents change.
"""

import hashlib
import json
import re
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import structlog

from rfp.search.indexer import load_manifest
from rfp.settings import PROJECT_ROOT, CacheConfig, get_settings

log = structlog.get_logger()
GUARD = re.compile(r"[\w-]*\d[\w-]*")


def index_fingerprint() -> str:
    """Changes whenever any indexed file is added, changed or removed."""
    return hashlib.sha256(
        json.dumps(load_manifest(), sort_keys=True).encode()
    ).hexdigest()[:16]


def guard_tokens(text: str) -> list[str]:
    return sorted(set(GUARD.findall(text.lower())))


def _unit(vector) -> np.ndarray:
    v = np.asarray(vector, dtype=float)
    norm = np.linalg.norm(v)
    return v / norm if norm else v


class SemanticCache:
    def __init__(
        self,
        cfg: CacheConfig | None = None,
        path: Path | None = None,
        embed: Callable[[str], list[float]] | None = None,
    ):
        self.cfg = cfg or get_settings().cache
        self.path = path or PROJECT_ROOT / self.cfg.path
        if embed is None:
            from rfp.search.embeddings import (
                embed_dense_query,  # loads the model only when used
            )

            embed = embed_dense_query
        self.embed = embed
        self._lock = threading.Lock()

    def _load(self) -> list[dict]:
        return json.loads(self.path.read_text()) if self.path.exists() else []

    def lookup(self, question: str, fingerprint: str) -> tuple[dict | None, float]:
        """Return (stored answer, similarity) for the best match, or (None, best similarity)."""
        guards = guard_tokens(question)
        candidates = [
            e
            for e in self._load()
            if e["fingerprint"] == fingerprint and e["guards"] == guards
        ]
        if not candidates:
            return None, 0.0
        q = _unit(self.embed(question))
        best, best_sim = None, 0.0
        for entry in candidates:
            sim = float(q @ _unit(entry["embedding"]))
            if sim > best_sim:
                best, best_sim = entry, sim
        if best is not None and best_sim >= self.cfg.similarity_threshold:
            log.info(
                "semantic_cache_hit",
                similarity=round(best_sim, 4),
                cached_question=best["question"],
            )
            return best["answer"], best_sim
        return None, best_sim

    def store(self, question: str, answer: dict, fingerprint: str) -> None:
        entry = {
            "question": question,
            "embedding": [float(x) for x in self.embed(question)],
            "guards": guard_tokens(question),
            "fingerprint": fingerprint,
            "answer": answer,
            "created": datetime.now(UTC).isoformat(),
        }
        with self._lock:
            entries = self._load() + [entry]
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(entries[-self.cfg.max_entries :]))

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)
