"""Unit tests for the freellmapi fallback bridge.

Mocks the HTTP boundary (requests.post) rather than hitting a real server --
the point here is verifying the Bedrock <-> OpenAI shape translation is
correct, not that a specific upstream provider is up. Live end-to-end
verification against an actual freellmapi router lives outside pytest
(needs Docker, upstream API keys, and network) -- see scripts/eval_* for
the pattern the project already uses for that kind of thing."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from services.llm_service import freellmapi_adapter as adapter


def _mock_response(payload):
    return SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: payload,
    )


def test_is_active_defaults_off(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert adapter.is_active() is False


def test_is_active_matches_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "freellmapi")
    assert adapter.is_active() is True
    monkeypatch.setenv("LLM_PROVIDER", "FreeLLMAPI")
    assert adapter.is_active() is True, "case-insensitive match"
    monkeypatch.setenv("LLM_PROVIDER", "  freellmapi  ")
    assert adapter.is_active() is True, "trimmed"
    monkeypatch.setenv("LLM_PROVIDER", "bedrock")
    assert adapter.is_active() is False


def test_model_for_task_env_precedence(monkeypatch):
    monkeypatch.delenv("FREELLM_MODEL", raising=False)
    monkeypatch.delenv("FREELLM_MODEL_EXTRACTION", raising=False)
    assert adapter._model_for("extraction") == "auto", "default is 'auto' (router-picked)"

    monkeypatch.setenv("FREELLM_MODEL", "llama-3.3-70b")
    assert adapter._model_for("extraction") == "llama-3.3-70b"

    monkeypatch.setenv("FREELLM_MODEL_EXTRACTION", "mixtral-8x7b")
    assert adapter._model_for("extraction") == "mixtral-8x7b", (
        "per-task env beats the global FREELLM_MODEL"
    )
    assert adapter._model_for("generation") == "llama-3.3-70b", (
        "unrelated task still falls back to the global"
    )


def test_headers_include_bearer_when_key_set(monkeypatch):
    monkeypatch.setenv("FREELLM_API_KEY", "sk-abc123")
    headers = adapter._headers()
    assert headers["Authorization"] == "Bearer sk-abc123"

    monkeypatch.delenv("FREELLM_API_KEY", raising=False)
    headers = adapter._headers()
    assert "Authorization" not in headers, "no key -> no auth header"


def test_to_openai_messages_prepends_system(monkeypatch):
    messages = [{"role": "user", "content": "hello"}]
    result = adapter._to_openai_messages(messages, system="you are helpful")
    assert result == [
        {"role": "system", "content": "you are helpful"},
        {"role": "user", "content": "hello"},
    ]


def test_to_openai_messages_flattens_content_block_list():
    """Defensive: some callers might pass Bedrock's rich `[{text}]` shape
    instead of a plain string -- flatten it back to a string so upstream
    OpenAI-compatible providers accept the request."""
    messages = [{"role": "user", "content": [{"text": "hi "}, {"text": "there"}]}]
    result = adapter._to_openai_messages(messages, system=None)
    assert result == [{"role": "user", "content": "hi there"}]


def test_tool_spec_to_openai_shape():
    bedrock_spec = {
        "name": "record_farmer_intent",
        "description": "Record what the farmer said",
        "inputSchema": {"json": {"type": "object", "properties": {"intent": {"type": "string"}}}},
    }
    out = adapter._tool_spec_to_openai(bedrock_spec)
    assert out == {
        "type": "function",
        "function": {
            "name": "record_farmer_intent",
            "description": "Record what the farmer said",
            "parameters": {"type": "object", "properties": {"intent": {"type": "string"}}},
        },
    }


def test_complete_translates_and_returns_content(monkeypatch):
    captured = {}

    def fake_post(url, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return _mock_response({
            "choices": [{"message": {"content": "hi from the model"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3},
        })

    monkeypatch.setattr("services.llm_service.freellmapi_adapter.requests.post", fake_post)
    monkeypatch.setenv("FREELLM_BASE_URL", "http://localhost:3001/v1")
    monkeypatch.setenv("FREELLM_MODEL", "some-model")

    result = adapter.complete(
        task="extraction", messages=[{"role": "user", "content": "hi"}],
        system=None, max_tokens=64, temperature=0.0,
    )
    assert result == "hi from the model"
    assert captured["url"] == "http://localhost:3001/v1/chat/completions"
    assert captured["json"]["model"] == "some-model"
    assert captured["json"]["messages"] == [{"role": "user", "content": "hi"}]
    assert captured["json"]["max_tokens"] == 64
    assert captured["json"]["temperature"] == 0.0


def test_converse_with_tool_forced_choice_returns_bedrock_shape(monkeypatch):
    captured = {}

    def fake_post(url, json, headers, timeout):
        captured["json"] = json
        return _mock_response({
            "choices": [{
                "finish_reason": "tool_calls",
                "message": {
                    "content": None,
                    "tool_calls": [{
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "record_farmer_intent",
                            "arguments": '{"intent": "WEATHER_ALERT"}',
                        },
                    }],
                },
            }],
            "usage": {"prompt_tokens": 20, "completion_tokens": 5},
        })

    monkeypatch.setattr("services.llm_service.freellmapi_adapter.requests.post", fake_post)

    result = adapter.converse_with_tool(
        task="extraction",
        messages=[{"role": "user", "content": "will it rain"}],
        tool_spec={"name": "record_farmer_intent", "description": "", "inputSchema": {"json": {}}},
        system=None,
        tool_choice_name="record_farmer_intent",
        max_tokens=256, temperature=0.0,
    )
    assert result == {
        "tool_name": "record_farmer_intent",
        "tool_input": {"intent": "WEATHER_ALERT"},
        "text": None,
        "stop_reason": "tool_calls",
    }
    assert captured["json"]["tool_choice"] == {
        "type": "function", "function": {"name": "record_farmer_intent"},
    }


def test_converse_with_tool_no_choice_name_uses_required(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "services.llm_service.freellmapi_adapter.requests.post",
        lambda url, json, headers, timeout: (captured.update({"json": json}) or _mock_response({"choices": []})),
    )
    adapter.converse_with_tool(
        task="extraction", messages=[{"role": "user", "content": "x"}],
        tool_spec={"name": "t", "description": "", "inputSchema": {"json": {}}},
        system=None, tool_choice_name=None, max_tokens=64, temperature=0,
    )
    assert captured["json"]["tool_choice"] == "required", (
        "no forced name -> OpenAI 'required' (any tool must be called)"
    )


def test_converse_with_tool_handles_malformed_arguments_json(monkeypatch):
    """A provider that streamed a truncated/malformed tool-call payload
    used to crash the request handler. Match Bedrock's 'no tool call'
    return shape instead so callers keep working."""
    monkeypatch.setattr(
        "services.llm_service.freellmapi_adapter.requests.post",
        lambda url, json, headers, timeout: _mock_response({
            "choices": [{
                "finish_reason": "tool_calls",
                "message": {
                    "tool_calls": [{
                        "type": "function",
                        "function": {"name": "t", "arguments": '{"broken":'},
                    }],
                },
            }],
        }),
    )
    result = adapter.converse_with_tool(
        task="extraction", messages=[{"role": "user", "content": "x"}],
        tool_spec={"name": "t", "description": "", "inputSchema": {"json": {}}},
        system=None, tool_choice_name="t", max_tokens=64, temperature=0,
    )
    assert result["tool_name"] == "t"
    assert result["tool_input"] == {}, "malformed JSON degrades to empty dict, not KeyError/500"


def test_converse_with_tool_arguments_can_be_dict(monkeypatch):
    """Some providers return `arguments` as an already-parsed dict rather
    than a JSON string (spec-compliant OpenAI is a string, but real
    behavior varies)."""
    monkeypatch.setattr(
        "services.llm_service.freellmapi_adapter.requests.post",
        lambda url, json, headers, timeout: _mock_response({
            "choices": [{
                "finish_reason": "tool_calls",
                "message": {
                    "tool_calls": [{
                        "type": "function",
                        "function": {"name": "t", "arguments": {"key": "value"}},
                    }],
                },
            }],
        }),
    )
    result = adapter.converse_with_tool(
        task="extraction", messages=[{"role": "user", "content": "x"}],
        tool_spec={"name": "t", "description": "", "inputSchema": {"json": {}}},
        system=None, tool_choice_name="t", max_tokens=64, temperature=0,
    )
    assert result["tool_input"] == {"key": "value"}
