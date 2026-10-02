"""Project settings: tunables from config/config.yaml, secrets from .env."""

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]   # settings.py -> rfp -> src -> root
CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"


class ChunkingConfig(BaseModel):
    target_tokens: int = 500
    max_tokens: int = 650
    min_tokens: int = 80
    overlap_tokens: int = 80
class SearchConfig(BaseModel):
    dense_model: str = "BAAI/bge-small-en-v1.5"
    dense_dim: int = 384
    sparse_model: str = "Qdrant/bm25"
    qdrant_path: str = "data/index/qdrant"
    collection: str = "rfp_chunks"
    manifest_path: str = "data/index/manifest.json"
    rerank_model: str = "Xenova/ms-marco-MiniLM-L-6-v2"
    retrieve_k: int = 30
    rrf_k: int = 60
    sparse_weight: float = 1.0
    identifier_sparse_weight: float = 2.0
    rerank_include_header: bool = False

class LLMConfig(BaseModel):
    timeout_s: float = 60
    max_tokens: int = 2048
    temperature: float | None = None
    validation_retries: int = 2
class AgentsConfig(BaseModel):
    per_query_k: int = 5
    per_field_k: int = 5
    extraction_tier: str = "fast"
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    # from .env
    anthropic_api_key: str = ""
    llm_provider: str = "anthropic"
    llm_model_smart: str = "claude-sonnet-5-5"
    llm_model_fast: str = "claude-haiku-4-5-20251001"
        # paths (relative to the project root)
    bids_dir: str = "data/bids"
    processed_dir: str = "data/processed"
    # from config.yaml
    chunking: ChunkingConfig = ChunkingConfig()
    search: SearchConfig = SearchConfig()
    llm: LLMConfig = LLMConfig()
    agents: AgentsConfig = AgentsConfig()

@lru_cache
def get_settings() -> Settings:
    """Load once and reuse. Values in config.yaml override the defaults above."""
    data = yaml.safe_load(CONFIG_PATH.read_text()) if CONFIG_PATH.exists() else {}
    return Settings(**(data or {}))