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


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    # from .env
    anthropic_api_key: str = ""
    llm_provider: str = "anthropic"
    llm_model_smart: str = "claude-sonnet-5-5"
    llm_model_fast: str = "claude-haiku-4-5-20251001"

    # from config.yaml
    chunking: ChunkingConfig = ChunkingConfig()


@lru_cache
def get_settings() -> Settings:
    """Load once and reuse. Values in config.yaml override the defaults above."""
    data = yaml.safe_load(CONFIG_PATH.read_text()) if CONFIG_PATH.exists() else {}
    return Settings(**(data or {}))