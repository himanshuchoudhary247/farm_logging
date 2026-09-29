"""Shared pytest fixtures."""
import pytest

_FALLBACK_ENV_VARS = (
    "LLM_PROVIDER",
    "FREELLM_BASE_URL",
    "FREELLM_API_KEY",
    "FREELLM_MODEL",
    "FREELLM_MODEL_EXTRACTION",
    "FREELLM_MODEL_GENERATION",
    "FREELLM_MODEL_LONG_FORM",
    "FREELLM_MODEL_LEGACY",
    "FREELLM_EXTRA_BODY",
)


@pytest.fixture(autouse=True)
def _default_llm_provider(monkeypatch):
    """The suite assumes the default Bedrock backend. Clear the optional
    LLM_PROVIDER=freellmapi fallback settings for every test so running
    pytest from a shell that has them set gives the same result as CI.
    Tests that exercise the fallback set these again themselves."""
    for name in _FALLBACK_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
        