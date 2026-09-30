"""Tests for Bedrock prompt caching wiring (task #32).

Live cache-hit measurement is not possible from tests -- it requires
Bedrock to actually be reachable (blocked account-wide as of the branch
was cut). What CAN be tested here without touching AWS:

1. _supports_prompt_cache picks the right model whitelist.
2. When a supported model is used, the request body sent to boto3's
   client.converse contains a `cachePoint` block after the system text.
3. When an unsupported model is used, the request body has no
   cachePoint (so we don't crash on models that reject it).
4. When BEDROCK_PROMPT_CACHE=0, no cachePoint appears regardless of
   model support.
5. When the response reports cacheReadInputTokens > 0, the telemetry
   log line's cache_hit field is True.

All request/response boundaries mocked via a fake boto3 client.
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _reset_bedrock_state():
    """Force the module to rebuild its cached client per test so a fake
    can be swapped in cleanly."""
    import services.llm_service.bedrock_adapter as adapter
    adapter._bedrock_client = None
    adapter._bedrock_model = None
    adapter._llm_config_cache = None
    yield
    adapter._bedrock_client = None
    adapter._bedrock_model = None
    adapter._llm_config_cache = None


def test_supports_prompt_cache_whitelist():
    from services.llm_service.bedrock_adapter import _supports_prompt_cache
    # Cache-capable models (from the whitelist)
    assert _supports_prompt_cache("anthropic.claude-3-5-sonnet-20240620-v1:0")
    assert _supports_prompt_cache("anthropic.claude-sonnet-4-5-20250929-v1:0")
    assert _supports_prompt_cache("anthropic.claude-haiku-4-5-20251001")
    assert _supports_prompt_cache("us.anthropic.claude-3-5-haiku-20241022-v1:0"), (
        "cross-region inference profile prefixes must be recognized"
    )
    assert _supports_prompt_cache("amazon.nova-micro-v1:0")
    # Non-capable
    assert not _supports_prompt_cache("deepseek.v3-v1:0")
    assert not _supports_prompt_cache("mistral.mistral-large-3-675b-instruct")
    assert not _supports_prompt_cache("random.made-up-model")


def test_supports_prompt_cache_env_disables(monkeypatch):
    from services.llm_service.bedrock_adapter import _supports_prompt_cache
    monkeypatch.setenv("BEDROCK_PROMPT_CACHE", "0")
    assert not _supports_prompt_cache("anthropic.claude-3-5-sonnet-20240620-v1:0"), (
        "env override must win over model whitelist"
    )
    monkeypatch.setenv("BEDROCK_PROMPT_CACHE", "1")
    assert _supports_prompt_cache("anthropic.claude-3-5-sonnet-20240620-v1:0")


def test_complete_adds_cache_point_for_supported_model(monkeypatch):
    """complete() with a cache-capable model sends `system: [{"text": ...},
    {"cachePoint": {"type": "default"}}]` -- the marker Bedrock uses to
    define what to cache."""
    monkeypatch.setenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20240620-v1:0")
    fake_client = MagicMock()
    fake_client.converse.return_value = {
        "output": {"message": {"content": [{"text": "hi"}]}},
        "usage": {"inputTokens": 10, "outputTokens": 5},
    }
    monkeypatch.setattr(
        "services.llm_service.bedrock_adapter._get_client",
        lambda: (fake_client, "anthropic.claude-3-5-sonnet-20240620-v1:0"),
    )
    from services.llm_service.bedrock_adapter import BedrockTextAdapter
    a = BedrockTextAdapter()
    a.complete(messages=[{"role": "user", "content": "hello"}], system="You are helpful.")
    call_req = fake_client.converse.call_args.kwargs
    system = call_req["system"]
    assert system[0] == {"text": "You are helpful."}
    assert system[-1] == {"cachePoint": {"type": "default"}}, (
        f"expected cachePoint marker on cache-capable model; got system={system}"
    )


def test_complete_omits_cache_point_for_unsupported_model(monkeypatch):
    """Non-capable models must NOT receive the marker -- Bedrock would
    return ValidationException."""
    monkeypatch.setenv("BEDROCK_MODEL_ID", "deepseek.v3-v1:0")
    fake_client = MagicMock()
    fake_client.converse.return_value = {
        "output": {"message": {"content": [{"text": "hi"}]}},
        "usage": {"inputTokens": 10, "outputTokens": 5},
    }
    monkeypatch.setattr(
        "services.llm_service.bedrock_adapter._get_client",
        lambda: (fake_client, "deepseek.v3-v1:0"),
    )
    from services.llm_service.bedrock_adapter import BedrockTextAdapter
    a = BedrockTextAdapter()
    a.complete(messages=[{"role": "user", "content": "hello"}], system="You are helpful.")
    system = fake_client.converse.call_args.kwargs["system"]
    assert system == [{"text": "You are helpful."}], (
        f"non-capable model must NOT receive cachePoint; got {system}"
    )


def test_complete_omits_cache_point_when_env_disabled(monkeypatch):
    """BEDROCK_PROMPT_CACHE=0 kills the marker even on a whitelisted model."""
    monkeypatch.setenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20240620-v1:0")
    monkeypatch.setenv("BEDROCK_PROMPT_CACHE", "0")
    fake_client = MagicMock()
    fake_client.converse.return_value = {
        "output": {"message": {"content": [{"text": "hi"}]}},
        "usage": {"inputTokens": 10, "outputTokens": 5},
    }
    monkeypatch.setattr(
        "services.llm_service.bedrock_adapter._get_client",
        lambda: (fake_client, "anthropic.claude-3-5-sonnet-20240620-v1:0"),
    )
    from services.llm_service.bedrock_adapter import BedrockTextAdapter
    a = BedrockTextAdapter()
    a.complete(messages=[{"role": "user", "content": "hello"}], system="You are helpful.")
    system = fake_client.converse.call_args.kwargs["system"]
    assert system == [{"text": "You are helpful."}]


def test_converse_with_tool_adds_cache_point_for_supported_model(monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20240620-v1:0")
    fake_client = MagicMock()
    fake_client.converse.return_value = {
        "output": {"message": {"content": [{"toolUse": {"name": "t", "input": {}}}]}},
        "usage": {"inputTokens": 20, "outputTokens": 5},
        "stopReason": "tool_use",
    }
    monkeypatch.setattr(
        "services.llm_service.bedrock_adapter._get_client",
        lambda: (fake_client, "anthropic.claude-3-5-sonnet-20240620-v1:0"),
    )
    from services.llm_service.bedrock_adapter import BedrockTextAdapter
    a = BedrockTextAdapter()
    a.converse_with_tool(
        messages=[{"role": "user", "content": "extract"}],
        tool_spec={"name": "t", "description": "", "inputSchema": {"json": {}}},
        system="Extraction instructions.",
        tool_choice_name="t",
    )
    system = fake_client.converse.call_args.kwargs["system"]
    assert system[-1] == {"cachePoint": {"type": "default"}}


def test_cache_hit_reported_in_telemetry(monkeypatch, caplog):
    """When Bedrock's usage response includes cacheReadInputTokens > 0,
    the log_llm_call telemetry line's cache_hit field is True."""
    monkeypatch.setenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20240620-v1:0")
    fake_client = MagicMock()
    fake_client.converse.return_value = {
        "output": {"message": {"content": [{"text": "hi"}]}},
        "usage": {"inputTokens": 50, "outputTokens": 5, "cacheReadInputTokens": 40},
    }
    monkeypatch.setattr(
        "services.llm_service.bedrock_adapter._get_client",
        lambda: (fake_client, "anthropic.claude-3-5-sonnet-20240620-v1:0"),
    )
    from services.llm_service.bedrock_adapter import BedrockTextAdapter
    with caplog.at_level(logging.INFO, logger="llm_telemetry"):
        BedrockTextAdapter().complete(
            messages=[{"role": "user", "content": "hi"}], system="You are helpful.",
        )
    msg = [r.message for r in caplog.records if r.name == "llm_telemetry"][0]
    assert "cache_hit=True" in msg, f"missing cache_hit in telemetry: {msg}"


def test_cache_hit_none_when_response_omits_field(monkeypatch, caplog):
    """No cacheReadInputTokens in the response -> cache_hit stays None
    (which is 'unknown'/'not reported'), not False."""
    monkeypatch.setenv("BEDROCK_MODEL_ID", "deepseek.v3-v1:0")
    fake_client = MagicMock()
    fake_client.converse.return_value = {
        "output": {"message": {"content": [{"text": "hi"}]}},
        "usage": {"inputTokens": 50, "outputTokens": 5},
    }
    monkeypatch.setattr(
        "services.llm_service.bedrock_adapter._get_client",
        lambda: (fake_client, "deepseek.v3-v1:0"),
    )
    from services.llm_service.bedrock_adapter import BedrockTextAdapter
    with caplog.at_level(logging.INFO, logger="llm_telemetry"):
        BedrockTextAdapter().complete(
            messages=[{"role": "user", "content": "hi"}], system="You are helpful.",
        )
    msg = [r.message for r in caplog.records if r.name == "llm_telemetry"][0]
    assert "cache_hit=" not in msg, (
        f"cache_hit must be omitted (not False) when response doesn't report it; got: {msg}"
    )


def test_freellmapi_reports_cache_hit_when_cached_tokens_present(monkeypatch, caplog):
    """OpenAI-compat providers (OpenAI, DeepInfra) report cache hits via
    usage.prompt_tokens_details.cached_tokens. Groq doesn't today, but
    if the field is present it should surface in telemetry."""
    from types import SimpleNamespace
    def fake_post(url, json, headers, timeout):
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {
                "choices": [{"message": {"content": "hi"}}],
                "usage": {
                    "prompt_tokens": 100, "completion_tokens": 5,
                    "prompt_tokens_details": {"cached_tokens": 80},
                },
            },
        )
    monkeypatch.setattr("services.llm_service.freellmapi_adapter.requests.post", fake_post)
    monkeypatch.setenv("FREELLM_BASE_URL", "http://localhost:3001/v1")
    monkeypatch.setenv("FREELLM_MODEL", "gpt-4o")
    from services.llm_service import freellmapi_adapter as adapter
    with caplog.at_level(logging.INFO, logger="llm_telemetry"):
        adapter.complete(
            task="extraction", messages=[{"role": "user", "content": "hi"}],
            system=None, max_tokens=64, temperature=0,
        )
    msg = [r.message for r in caplog.records if r.name == "llm_telemetry"][0]
    assert "cache_hit=True" in msg
