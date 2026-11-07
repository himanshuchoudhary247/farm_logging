"""Shared pytest fixtures."""
import atexit
import os
import shutil
import tempfile
from pathlib import Path

import pytest

# Tests must never write into the repo's tracked data/*.json (seen: a local
# test run left synthetic rows there). The whole run works on a copy of
# data/ in a temp folder instead, so tests still read the same seed data.
# Set here, at import, before any test module (or a module-level path such
# as services/cache_refresh's CACHE_ROOT) reads it. Tests that set their own
# FARMER_CHAT_DATA_DIR with monkeypatch keep doing so.
_REPO_DATA = Path(__file__).resolve().parent.parent / "data"
_TEST_DATA_ROOT = Path(tempfile.mkdtemp(prefix="farm_logging_tests_"))
_TEST_DATA = _TEST_DATA_ROOT / "data"
if _REPO_DATA.is_dir():
    shutil.copytree(_REPO_DATA, _TEST_DATA, ignore=shutil.ignore_patterns("voice_sessions", "cache", "*.lock"))
else:
    _TEST_DATA.mkdir(parents=True)
os.environ["FARMER_CHAT_DATA_DIR"] = str(_TEST_DATA)
atexit.register(shutil.rmtree, _TEST_DATA_ROOT, True)

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
        