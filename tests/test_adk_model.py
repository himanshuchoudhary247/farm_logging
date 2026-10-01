"""build_adk_model picks Bedrock by default and the OpenAI-compatible
fallback endpoint when LLM_PROVIDER=freellmapi; FREELLM_EXTRA_BODY is
passed through to both the ADK agents and the adapter requests."""
from types import SimpleNamespace

import pytest

from services.llm_service import adk_model, freellmapi_adapter


class _FakeLiteLlm:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def _clear_env(monkeypatch):
    for name in ("LLM_PROVIDER", "FREELLM_BASE_URL", "FREELLM_API_KEY", "FREELLM_MODEL",
                 "FREELLM_MODEL_EXTRACTION", "FREELLM_MODEL_GENERATION", "FREELLM_EXTRA_BODY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(adk_model, "LiteLlm", _FakeLiteLlm)


def test_default_uses_bedrock_unchanged(monkeypatch):
    _clear_env(monkeypatch)
    m = adk_model.build_adk_model("extraction", "mistral.x", temperature=0)
    assert m.kwargs == {"model": "bedrock/mistral.x", "temperature": 0}


def test_fallback_uses_openai_compatible_endpoint(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "freellmapi")
    monkeypatch.setenv("FREELLM_BASE_URL", "https://example.test/v1/")
    monkeypatch.setenv("FREELLM_API_KEY", "test-key")
    monkeypatch.setenv("FREELLM_MODEL", "some-model")
    m = adk_model.build_adk_model("extraction", "mistral.x", temperature=0)
    assert m.kwargs == {
        "model": "openai/some-model",
        "api_base": "https://example.test/v1",
        "api_key": "test-key",
        "temperature": 0,
    }


def test_fallback_per_tier_override_and_enum_value(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "freellmapi")
    monkeypatch.setenv("FREELLM_MODEL", "default-model")
    monkeypatch.setenv("FREELLM_MODEL_GENERATION", "gen-model")
    tier = SimpleNamespace(value="generation")
    m = adk_model.build_adk_model(tier, "mistral.x", temperature=0.3)
    assert m.kwargs["model"] == "openai/gen-model"
    assert m.kwargs["temperature"] == 0.3


def test_fallback_without_key_uses_placeholder(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "freellmapi")
    monkeypatch.setenv("FREELLM_MODEL", "some-model")
    m = adk_model.build_adk_model("extraction", "mistral.x", temperature=0)
    assert m.kwargs["api_key"] == "unused"


def test_fallback_passes_extra_body_to_adk(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "freellmapi")
    monkeypatch.setenv("FREELLM_MODEL", "some-model")
    monkeypatch.setenv("FREELLM_EXTRA_BODY", '{"include_reasoning": false}')
    m = adk_model.build_adk_model("extraction", "mistral.x", temperature=0)
    assert m.kwargs["extra_body"] == {"include_reasoning": False}


def test_adapter_merges_extra_body_into_payload(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "freellmapi")
    monkeypatch.setenv("FREELLM_MODEL", "some-model")
    monkeypatch.setenv("FREELLM_EXTRA_BODY", '{"include_reasoning": false}')
    sent = {}

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    def _fake_post(url, json=None, headers=None, timeout=None):
        sent.update(json)
        return _Resp()

    monkeypatch.setattr(freellmapi_adapter.requests, "post", _fake_post)
    assert freellmapi_adapter.complete("extraction", [{"role": "user", "content": "hi"}], None, 10, 0) == "ok"
    assert sent["include_reasoning"] is False
    assert sent["model"] == "some-model"


def test_invalid_extra_body_raises_clear_error(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "freellmapi")
    monkeypatch.setenv("FREELLM_EXTRA_BODY", "not json")
    with pytest.raises(ValueError, match="FREELLM_EXTRA_BODY"):
        freellmapi_adapter.openai_compat_config("extraction")
