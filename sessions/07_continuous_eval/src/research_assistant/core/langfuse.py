"""The service's Langfuse client (Session 07): traces of every run, the prompt, user feedback scores.

One client per process, created at start-up. Later code calls `get_client()` and gets the same client.
https://langfuse.com/docs/observability/sdk/overview
"""
from importlib.metadata import version

from langfuse import Langfuse

from research_assistant.core.config import Settings


def init_langfuse(settings: Settings) -> Langfuse:
    """Without keys (tests, offline runs) tracing is off and nothing is sent."""
    enabled = bool(settings.langfuse_public_key.get_secret_value())
    return Langfuse(public_key=settings.langfuse_public_key.get_secret_value() or None,
                    secret_key=settings.langfuse_secret_key.get_secret_value() or None,
                    base_url=settings.langfuse_base_url,
                    environment=settings.langfuse_tracing_environment,  # production | staging | development
                    release=version("research-assistant"),             # the app release on every trace
                    tracing_enabled=enabled)
