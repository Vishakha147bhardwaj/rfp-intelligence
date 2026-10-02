"""REST API for the RFP search engine. /ask and /extract are added with the agents (Part C)."""

import threading
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field

from rfp.ingestion.pipeline import ingest_folder
from rfp.search.engine import MODES, SearchEngine, SearchResult
from rfp.search.indexer import IndexReport, index_documents, load_manifest
from rfp.search.store import ChunkStore
from rfp.settings import PROJECT_ROOT, get_settings


class IndexRequest(BaseModel):
    folder: str = Field(..., examples=["data/bids/Bid1"])
    force: bool = False


class IndexResponse(BaseModel):
    bid_id: str
    report: IndexReport
    chunks_for_bid: int
    files_failed: list[str]


class SearchResponse(BaseModel):
    query: str
    mode: str
    count: int
    results: list[SearchResult]


def _resolve_bid_folder(folder: str) -> Path:
    """Only allow folders inside the configured bids_dir."""
    root = (PROJECT_ROOT / get_settings().bids_dir).resolve()
    path = (PROJECT_ROOT / folder).resolve()
    if not path.is_relative_to(root):
        raise HTTPException(400, f"Folder must be inside {get_settings().bids_dir}")
    if not path.is_dir():
        raise HTTPException(404, f"Folder not found: {folder}")
    return path


def create_app(store_factory: Callable[[], ChunkStore] = ChunkStore) -> FastAPI:
    """Build the app. Tests pass a factory that opens a temporary store."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.store = store_factory()
        app.state.lock = threading.Lock()   # embedded Qdrant: one operation at a time
        yield
        app.state.store.close()

    app = FastAPI(
        title="RFP Intelligence Platform",
        version="0.1.0",
        description="Hybrid search over bid documents (dense + BM25 + RRF + reranking).",
        lifespan=lifespan,
    )

    @app.get("/health")
    def health(request: Request) -> dict:
        with request.app.state.lock:
            total = request.app.state.store.count()
        return {"status": "ok", "chunks_indexed": total}

    @app.get("/bids")
    def bids(request: Request) -> list[dict]:
        store, lock = request.app.state.store, request.app.state.lock
        with lock:
            return [
                {"bid_id": bid, "files": sorted(files), "chunks": store.count(bid_id=bid)}
                for bid, files in load_manifest().items()
            ]

    @app.post("/index", response_model=IndexResponse)
    def index(req: IndexRequest, request: Request) -> IndexResponse:
        folder = _resolve_bid_folder(req.folder)
        docs, ingestion = ingest_folder(folder, PROJECT_ROOT / get_settings().processed_dir)
        store, lock = request.app.state.store, request.app.state.lock
        with lock:
            report = index_documents(docs, store, force=req.force)
            count = store.count(bid_id=folder.name)
        return IndexResponse(
            bid_id=folder.name,
            report=report,
            chunks_for_bid=count,
            files_failed=[f.file_name for f in ingestion.files if f.status == "failed"],
        )

    @app.get("/search", response_model=SearchResponse)
    def search(
        request: Request,
        q: str = Query(..., min_length=2, description="Search query"),
        bid_id: str | None = None,
        doc_type: str | None = Query(None, description="rfp | addendum | bid_page | specs | affidavit"),
        addendum_number: int | None = None,
        top_k: int = Query(5, ge=1, le=50),
        mode: str = Query("hybrid_rerank", description=" | ".join(MODES)),
    ) -> SearchResponse:
        if mode not in MODES:
            raise HTTPException(422, f"mode must be one of {MODES}")
        with request.app.state.lock:
            results = SearchEngine(request.app.state.store).search(
                q, top_k=top_k, mode=mode, bid_id=bid_id,
                doc_type=doc_type, addendum_number=addendum_number,
            )
        return SearchResponse(query=q, mode=mode, count=len(results), results=results)

    return app


app = create_app()