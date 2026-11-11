"""Settings read from environment variables, then from `.env` in the working folder (pydantic-settings).

12-factor config: the code is identical in dev, staging and prod; only the environment changes.
A real environment variable wins over the same key in `.env`.
"""
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROMPT_FILE = Path(__file__).parent / "prompts" / "system_prompt.md"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["dev", "staging", "prod"] = "dev"
    openai_api_key: SecretStr = Field(min_length=1)  # required: the app stops at start-up without it
    tavily_api_key: SecretStr = Field(min_length=1)
    model: str = "openai:gpt-6-luna"  # listed as a snapshot on the model page (no dated variant)
    max_search_results: int = 3
    log_level: str = "INFO"
    # USD per 1M tokens for gpt-6-luna, https://developers.openai.com/api/docs/models/gpt-6-luna
    price_input_per_mtok: float = 0.10
    price_output_per_mtok: float = 0.50


@lru_cache
def get_settings() -> Settings:
    return Settings()


def load_prompt() -> str:
    return PROMPT_FILE.read_text(encoding="utf-8").strip()
