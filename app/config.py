"""Application configuration loaded from environment variables."""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Core services ---
    database_url: str = "postgresql+psycopg2://postgres:postgres@postgres:5432/knowledge"
    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/1"
    redis_url: str = "redis://redis:6379/0"

    # --- Storage ---
    upload_dir: str = "/data/uploads"
    max_upload_mb: int = 50

    # --- Embeddings ---
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dim: int = 384

    # --- Chunking ---
    chunk_size_tokens: int = 500
    chunk_overlap_tokens: int = 50
    ocr_min_chars: int = 20  # below this per page -> treat page as scanned, run OCR
    ocr_dpi: int = 200

    # --- Retrieval ---
    default_top_k: int = 5
    max_top_k: int = 50

    # --- AI Gateway / LLM ---
    llm_provider: str = "none"  # none | ollama
    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "llama3.2"
    llm_timeout_seconds: int = 120

    # --- OCR binary (override on Windows/local if needed) ---
    tesseract_cmd: Optional[str] = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
