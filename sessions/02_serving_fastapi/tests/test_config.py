"""Offline tests: no API key and no network needed."""
import pytest
from pydantic import ValidationError

from research_assistant.agent.agent import load_prompt
from research_assistant.core.config import Settings


def test_env_var_overrides_and_key_is_masked(monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")
    settings = Settings(_env_file=None, openai_api_key="test-key", tavily_api_key="test-key")
    assert settings.app_env == "staging"
    assert "test-key" not in str(settings.model_dump())  # SecretStr never prints the value


def test_missing_key_fails_at_startup(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValidationError, match="openai_api_key"):
        Settings(_env_file=None, tavily_api_key="test-key")


def test_unknown_environment_is_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="production", openai_api_key="k", tavily_api_key="k")


PINNED_SNAPSHOTS = {"openai:gpt-6-luna"}  # IDs listed under "Snapshots" on the provider's model page


def test_model_is_a_pinned_snapshot():
    model = Settings(_env_file=None, openai_api_key="k", tavily_api_key="k").model
    assert model in PINNED_SNAPSHOTS  # not an alias such as "gpt-5.4-mini"


def test_prompt_file_is_packaged():
    assert "research assistant" in load_prompt()
