from fastapi.testclient import TestClient

from rfp.api.app import create_app
from rfp.search.store import ChunkStore
from rfp.settings import SearchConfig


def client_for(tmp_path) -> TestClient:
    app = create_app(lambda: ChunkStore(SearchConfig(qdrant_path=str(tmp_path / "q"))))
    return TestClient(app)


def test_health_on_empty_index(tmp_path):
    with client_for(tmp_path) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "chunks_indexed": 0}


def test_index_rejects_folder_outside_bids_dir(tmp_path):
    with client_for(tmp_path) as client:
        response = client.post("/index", json={"folder": "src"})
    assert response.status_code == 400


def test_index_missing_folder_is_404(tmp_path):
    with client_for(tmp_path) as client:
        response = client.post("/index", json={"folder": "data/bids/NoSuchBid"})
    assert response.status_code == 404


def test_search_rejects_unknown_mode(tmp_path):
    with client_for(tmp_path) as client:
        response = client.get("/search", params={"q": "due date", "mode": "magic"})
    assert response.status_code == 422


def test_ask_without_llm_returns_503(tmp_path):
    from rfp.llm.client import LLMError

    def no_llm():
        raise LLMError("ANTHROPIC_API_KEY is not set")

    app = create_app(
        lambda: ChunkStore(SearchConfig(qdrant_path=str(tmp_path / "q"))), no_llm
    )
    with TestClient(app) as client:
        response = client.post("/ask", json={"question": "What is the due date?"})
    assert (
        response.status_code == 503 and "LLM unavailable" in response.json()["detail"]
    )
