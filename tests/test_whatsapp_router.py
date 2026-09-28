"""Router tests -- the load-bearing test file for the WhatsApp channel.

Mocks route_turn_adk at the boundary (matches how test_chat_orchestrator_adk.py
already mocks the classifier/agents). Never hits a live LLM or Meta/Twilio.
Uses MockProvider so send_text is captured in-memory.
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest


@pytest.fixture
def env(tmp_path: Path, monkeypatch):
    """Set up a self-contained data dir + config so nothing bleeds
    between tests. Also resets router + config module-level caches."""
    monkeypatch.setenv("FARMER_CHAT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHANNELS_CONFIG_PATH", str(tmp_path / "channels-none.yaml"))
    monkeypatch.setenv("WHATSAPP_ENABLED", "1")
    monkeypatch.setenv("WHATSAPP_PROVIDER", "mock")
    monkeypatch.setenv("WHATSAPP_ALLOWED_INTENTS", "query,appointment")
    monkeypatch.setenv("WHATSAPP_RATE_LIMIT_PER_MIN", "6")
    monkeypatch.setenv("WHATSAPP_RATE_LIMIT_PER_HOUR", "100")

    import storage
    importlib.reload(storage)
    from services.whatsapp_channel import config as cfg_mod
    from services.whatsapp_channel import router as router_mod
    cfg_mod.reset_cache_for_tests()
    router_mod.reset_state_for_tests()

    from services.whatsapp_channel.providers.mock import MockProvider
    provider = MockProvider(cfg_mod.load_config())
    return {
        "storage": storage,
        "cfg_mod": cfg_mod,
        "router_mod": router_mod,
        "provider": provider,
        "tmp_path": tmp_path,
    }


def _write_farmer(storage_mod, tmp_path: Path, id_: str, name: str, phone: str = "", whatsapp_phone=None):
    from models import Farmer
    farmers = list(storage_mod._load_json_list(tmp_path / "farmers.json"))
    farmers.append(Farmer(
        id=id_, name=name, login_username=id_, password_hash="x",
        phone=phone, whatsapp_phone=whatsapp_phone,
    ).model_dump())
    storage_mod.atomic_write_json(tmp_path / "farmers.json", farmers)


def _msg(text: str, from_phone: str = "+919876543210", id_: str = "m-1"):
    from services.whatsapp_channel.providers.base import InboundMessage
    return InboundMessage(from_phone=from_phone, text=text, id=id_)


# ---- Registered-farmer resolution ----------------------------------------


def test_registered_farmer_by_phone_alone_never_sees_enrollment(env, monkeypatch):
    """The user's stated requirement: farmer with .phone matching the
    WhatsApp sender resolves immediately, no enrollment prompt."""
    _write_farmer(env["storage"], env["tmp_path"], "f-1", "Asha", phone="+919876543210")
    calls = []
    def fake_route(farmer_id, session_id, text, language, include_audio, allowed_intents=None):
        calls.append({"farmer_id": farmer_id, "session_id": session_id, "text": text, "language": language, "allowed": allowed_intents})
        return {"agent": "query_agent", "intent": "query", "reply_text": "you have 12 animals", "result": {}}
    monkeypatch.setattr(env["router_mod"], "route_turn_adk", fake_route)

    env["router_mod"].handle_inbound(env["provider"], _msg("how many animals"))
    assert len(calls) == 1
    assert calls[0]["farmer_id"] == "f-1", "must resolve by phone, not prompt for enrollment"
    assert env["provider"].sent_texts == [("+919876543210", "you have 12 animals")]


# ---- Channel gate (the whole point of the module) ------------------------


def test_allowed_intent_dispatches(env, monkeypatch):
    _write_farmer(env["storage"], env["tmp_path"], "f-1", "Asha", phone="+919876543210")
    monkeypatch.setattr(env["router_mod"], "route_turn_adk", lambda *a, **k: {
        "agent": "query_agent", "intent": "query", "reply_text": "12 animals", "result": {}
    })
    env["router_mod"].handle_inbound(env["provider"], _msg("count animals"))
    assert env["provider"].sent_texts == [("+919876543210", "12 animals")]


def test_blocked_intent_returns_localized_message_no_agent_run(env, monkeypatch):
    """route_turn_adk returns the blocked stub (agent=None); the router
    must send the blocked_intent catalog message, NOT the empty reply."""
    _write_farmer(env["storage"], env["tmp_path"], "f-1", "Asha", phone="+919876543210")

    def fake_route(farmer_id, session_id, text, language, include_audio, allowed_intents=None):
        # Simulate the gate: incoming intent = add_animal, not in allowed set.
        assert "add_animal" not in allowed_intents
        return {"agent": None, "intent": "add_animal", "reply_text": "", "result": None}
    monkeypatch.setattr(env["router_mod"], "route_turn_adk", fake_route)

    env["router_mod"].handle_inbound(env["provider"], _msg("register a new goat"))
    assert len(env["provider"].sent_texts) == 1
    to, body = env["provider"].sent_texts[0]
    assert to == "+919876543210"
    # Body must mention the allowed intents (query, appointment) in English
    # (message is script-neutral, so falls back to en-IN default).
    assert "WhatsApp" in body or "FarmHerd" in body
    assert "ask about" in body or "book a vet" in body


# ---- Enrollment flow ------------------------------------------------------


def test_unknown_farmer_first_msg_sees_enrollment_prompt(env, monkeypatch):
    """No matching farmer + enrollment enabled -> localized prompt, no
    downstream call."""
    called = {"route": 0}
    monkeypatch.setattr(env["router_mod"], "route_turn_adk", lambda *a, **k: (called.__setitem__("route", called["route"] + 1) or {}))
    env["router_mod"].handle_inbound(env["provider"], _msg("hi"))
    assert called["route"] == 0
    assert len(env["provider"].sent_texts) == 1
    assert "recognize" in env["provider"].sent_texts[0][1] or "reply" in env["provider"].sent_texts[0][1]


def test_unknown_farmer_reply_with_registered_phone_binds_whatsapp_phone(env, monkeypatch):
    """Second message from an unknown phone that contains the farmer's
    registered phone -> we resolve and set whatsapp_phone. Third
    message from the same sender should now resolve normally."""
    _write_farmer(env["storage"], env["tmp_path"], "f-1", "Asha", phone="+911111111111")
    monkeypatch.setattr(env["router_mod"], "route_turn_adk", lambda *a, **k: {
        "agent": "query_agent", "intent": "query", "reply_text": "ok", "result": {}
    })

    # msg 1 -- unknown, prompt is sent
    env["router_mod"].handle_inbound(env["provider"], _msg("hello", id_="a"))
    # msg 2 -- reply contains the registered phone, we bind and confirm
    env["router_mod"].handle_inbound(env["provider"], _msg("+91 11111 11111", id_="b"))
    # msg 3 -- future messages now resolve normally
    env["router_mod"].handle_inbound(env["provider"], _msg("count animals", id_="c"))

    sent_bodies = [b for _, b in env["provider"].sent_texts]
    assert any("Thanks" in b or "जुड़ गया" in b or "ಲಿಂಕ್" in b for b in sent_bodies), (
        f"expected an enrollment_success message; got {sent_bodies}"
    )
    # Reload to verify the farmer now has whatsapp_phone set.
    import importlib
    importlib.reload(env["storage"])
    reloaded = env["storage"].get_farmer_by_id("f-1")
    assert reloaded.whatsapp_phone == "+919876543210", "whatsapp_phone should be set to the sender's number"


def test_unknown_farmer_enrollment_disabled_sends_generic_reject(env, monkeypatch):
    monkeypatch.setenv("WHATSAPP_ENROLLMENT_ENABLED", "0")
    env["cfg_mod"].reset_cache_for_tests()
    env["router_mod"].reset_state_for_tests()
    env["router_mod"].handle_inbound(env["provider"], _msg("hi"))
    assert len(env["provider"].sent_texts) == 1
    body = env["provider"].sent_texts[0][1]
    assert "not registered" in body or "not recognize" in body or "contact" in body.lower()


# ---- Rate limit ----------------------------------------------------------


def test_rate_limit_blocks_after_configured_per_min(env, monkeypatch):
    _write_farmer(env["storage"], env["tmp_path"], "f-1", "Asha", phone="+919876543210")
    route_calls = []
    monkeypatch.setattr(env["router_mod"], "route_turn_adk", lambda *a, **k: (
        route_calls.append(1) or {"agent": "query_agent", "intent": "query", "reply_text": "ok", "result": {}}
    ))
    # 6 per minute -> the 7th within the same window is refused
    for i in range(7):
        env["router_mod"].handle_inbound(env["provider"], _msg("hi", id_=f"m-{i}"))
    assert len(route_calls) == 6, "6 dispatched, 7th blocked"
    last_body = env["provider"].sent_texts[-1][1]
    assert "fast" in last_body.lower() or "wait" in last_body.lower() or "बहुत" in last_body or "मिनट" in last_body


# ---- Dedupe -------------------------------------------------------------


def test_duplicate_message_id_processed_once(env, monkeypatch):
    _write_farmer(env["storage"], env["tmp_path"], "f-1", "Asha", phone="+919876543210")
    calls = []
    monkeypatch.setattr(env["router_mod"], "route_turn_adk", lambda *a, **k: (
        calls.append(1) or {"agent": "query_agent", "intent": "query", "reply_text": "ok", "result": {}}
    ))
    env["router_mod"].handle_inbound(env["provider"], _msg("hi", id_="same-id"))
    env["router_mod"].handle_inbound(env["provider"], _msg("hi", id_="same-id"))  # dedupe hit
    env["router_mod"].handle_inbound(env["provider"], _msg("hi", id_="same-id"))  # dedupe hit
    assert len(calls) == 1


# ---- Reply truncation ---------------------------------------------------


def test_long_reply_gets_trimmed_with_suffix(env, monkeypatch):
    _write_farmer(env["storage"], env["tmp_path"], "f-1", "Asha", phone="+919876543210")
    monkeypatch.setenv("WHATSAPP_MAX_REPLY_CHARS", "50")
    env["cfg_mod"].reset_cache_for_tests()
    env["router_mod"].reset_state_for_tests()
    long_reply = "x" * 200
    monkeypatch.setattr(env["router_mod"], "route_turn_adk", lambda *a, **k: {
        "agent": "query_agent", "intent": "query", "reply_text": long_reply, "result": {}
    })
    env["router_mod"].handle_inbound(env["provider"], _msg("hi"))
    sent = env["provider"].sent_texts[0][1]
    assert len(sent) <= 50, f"reply must fit inside max_reply_chars; got {len(sent)}"
    assert "trimmed" in sent or "..." in sent


# ---- Session ID namespace ------------------------------------------------


def test_session_id_is_namespaced_and_deterministic(env, monkeypatch):
    _write_farmer(env["storage"], env["tmp_path"], "f-1", "Asha", phone="+919876543210")
    captured = []
    monkeypatch.setattr(env["router_mod"], "route_turn_adk", lambda *a, **k: (
        captured.append(k.get("session_id") or a[1]) or {"agent": "query_agent", "intent": "query", "reply_text": "ok", "result": {}}
    ))
    env["router_mod"].handle_inbound(env["provider"], _msg("hi", id_="a"))
    env["router_mod"].handle_inbound(env["provider"], _msg("hi again", id_="b"))
    assert captured[0] == captured[1], "same phone -> same session_id (sticky routing works)"
    assert captured[0].startswith("whatsapp-"), "explicit namespace so it can't collide with app UUIDs"
