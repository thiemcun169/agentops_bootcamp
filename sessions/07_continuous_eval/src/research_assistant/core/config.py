"""Settings read from environment variables, then from the session's `.env` (pydantic-settings).

12-factor config: the code is identical in dev, staging and prod; only the environment changes.
A real environment variable wins over the same key in `.env`.
"""
from functools import lru_cache
from pathlib import Path
from typing import Literal

from psycopg.conninfo import make_conninfo
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
    run_timeout_s: int = 120  # one run normally takes 5-20 s
    users_file: Path = PROJECT_DIR / "data" / "users.json"  # demo bearer tokens
    cors_origins: list[str] = []  # browser origins allowed to call the API, e.g. ["http://localhost:5500"]
    # ── Storage (new in Session 03) ──
    # memory: conversations live in the process (lost on restart; tests and `fastapi dev` without a database)
    # postgres: conversations and sessions are stored in PostgreSQL and survive a container restart
    checkpointer: Literal["memory", "postgres"] = "memory"
    db_host: str = "localhost"  # Compose: the service name "postgres"; Cloud Run + Cloud SQL: /cloudsql/PROJECT:REGION:INSTANCE (a Unix socket directory)
    db_port: int = 5432
    postgres_user: str = "agent"  # same variable names as the postgres image (.env.db is shared by both services)
    postgres_password: SecretStr = SecretStr("")
    postgres_db: str = "agent"
    # ── Langfuse (new in Session 07): traces, the prompt, scores and experiments ──
    # Empty keys: no tracing, and the agent uses the fallback prompt file (tests, offline runs).
    langfuse_public_key: SecretStr = SecretStr("")
    langfuse_secret_key: SecretStr = SecretStr("")
    langfuse_base_url: str = "https://cloud.langfuse.com"  # EU region; US: https://us.cloud.langfuse.com
    # The Langfuse environment of every trace: production traffic is what the online evaluators score.
    # Experiments (CI gate) are always recorded under "sdk-experiment", so they never mix with production.
    langfuse_tracing_environment: str = "development"
    # The prompt version this release uses is pinned in git (agent/prompt.toml); PROMPT_VERSION overrides it.
    prompt_version: int | None = None

    @property
    def db_url(self) -> str:
        """libpq connection string (make_conninfo quotes special characters); never log it: it holds the password."""
        return make_conninfo(host=self.db_host, port=self.db_port, user=self.postgres_user,
                             password=self.postgres_password.get_secret_value(), dbname=self.postgres_db)


@lru_cache  # read .env once per process, not on every request
def get_settings() -> Settings:
    return Settings()
