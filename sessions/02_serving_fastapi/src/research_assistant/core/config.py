"""Settings read from environment variables, then from the session's `.env` (pydantic-settings).

12-factor config: the code is identical in dev, staging and prod; only the environment changes.
A real environment variable wins over the same key in `.env`.
"""
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# src/research_assistant/core/config.py -> the session folder. `.env` is found from there, so the server
# starts the same way whatever the current directory is (Session 01 read a cwd-relative ".env").
PROJECT_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_DIR / ".env", extra="ignore")

    app_env: Literal["dev", "staging", "prod"] = "dev"
    openai_api_key: SecretStr = Field(min_length=1)  # required: the app stops at start-up without it
    tavily_api_key: SecretStr = Field(min_length=1)
    model: str = "openai:gpt-6-luna"  # listed as a snapshot on the model page (no dated variant)
    max_search_results: int = 3
    log_level: str = "INFO"
    # USD per 1M tokens for gpt-6-luna, https://developers.openai.com/api/docs/models/gpt-6-luna
    price_input_per_mtok: float = 0.10
    price_output_per_mtok: float = 0.50
    # ── Serving (new in Session 02) ──
    run_timeout_s: int = 120  # one run took 24-47 s in our tests (4-9 model calls)
    users_file: Path = PROJECT_DIR / "data" / "users.json"  # demo bearer tokens
    cors_origins: list[str] = []  # browser origins allowed to call the API, e.g. ["http://localhost:5500"]


@lru_cache  # read .env once per process, not on every request
def get_settings() -> Settings:
    return Settings()
