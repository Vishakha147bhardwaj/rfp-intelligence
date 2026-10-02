"""Incremental indexing: only new or changed files are chunked, embedded and written."""

import json
from pathlib import Path

import structlog
from pydantic import BaseModel, Field

from rfp.schemas.documents import ParsedDocument
from rfp.search.chunker import chunk_document
from rfp.search.embeddings import embed_dense, embed_sparse
from rfp.search.store import ChunkStore
from rfp.settings import PROJECT_ROOT, get_settings

log = structlog.get_logger()


class IndexReport(BaseModel):
    indexed: dict[str, int] = Field(default_factory=dict)   # file -> chunks written
    skipped: list[str] = Field(default_factory=list)         # unchanged files
    removed: list[str] = Field(default_factory=list)         # files no longer in the folder


def load_manifest(path: Path | None = None) -> dict:
    path = path or PROJECT_ROOT / get_settings().search.manifest_path
    return json.loads(path.read_text()) if path.exists() else {}


def _save_manifest(path: Path, manifest: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2))


def index_documents(
    docs: list[ParsedDocument],
    store: ChunkStore,
    manifest_path: Path | None = None,
    force: bool = False,
) -> IndexReport:
    manifest_path = manifest_path or PROJECT_ROOT / get_settings().search.manifest_path
    manifest = load_manifest(manifest_path)
    report = IndexReport()

    for doc in docs:
        known = manifest.setdefault(doc.bid_id, {})
        if not force and known.get(doc.file_name) == doc.file_hash:
            report.skipped.append(doc.file_name)
            continue
        chunks = chunk_document(doc)
        store.delete_file(doc.bid_id, doc.file_name)          # clear any old version
        if chunks:
            texts = [c.embed_text for c in chunks]
            store.upsert(chunks, embed_dense(texts), embed_sparse(texts))
        known[doc.file_name] = doc.file_hash
        report.indexed[doc.file_name] = len(chunks)
        log.info("file_indexed", bid=doc.bid_id, file=doc.file_name, chunks=len(chunks))

    for bid_id in {d.bid_id for d in docs}:                    # files deleted from the folder
        current = {d.file_name for d in docs if d.bid_id == bid_id}
        for file_name in list(manifest.get(bid_id, {})):
            if file_name not in current:
                store.delete_file(bid_id, file_name)
                del manifest[bid_id][file_name]
                report.removed.append(file_name)
                log.info("file_removed_from_index", bid=bid_id, file=file_name)

    _save_manifest(manifest_path, manifest)
    return report