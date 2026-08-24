"""Application settings."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings

BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    # SQLite keeps the demo self-contained; point at PostgreSQL via env for
    # a production-style deployment (schema is plain SQLAlchemy).
    database_url: str = f"sqlite:///{BACKEND_DIR / 'chargelens.db'}"
    artifact_dir: Path = BACKEND_DIR / "artifacts"
    data_dir: Path = BACKEND_DIR / "data"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    auto_seed: bool = True  # seed demo data on first startup (off in tests)

    # Optional: polish generated responses with Claude. The system is fully
    # functional without it - the deterministic grounded generator is the
    # source of truth and the fallback on any API failure or refusal.
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5"

    model_config = {"env_prefix": "CHARGELENS_", "env_file": ".env"}


settings = Settings()
