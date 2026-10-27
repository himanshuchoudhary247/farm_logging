"""Routing for the shop-order agent: a classified "order" message reaches
it, an order in progress keeps the session with it (so a bare "2" or a
tapped pill is not re-classified), a finished or cancelled order releases
the session, and a channel that does not allow "order" (WhatsApp, where
there is no Pay button) never reaches it."""
from __future__ import annotations

from services.chat_orchestrator import adk_router
from services.order_supervisor.service import OrderSupervisor

FARMER = "24cdd479-7ce8-4951-91cb-e295f8a2b0ff"


def _no_other_drafts(monkeypatch):
    monkeypatch.setattr(adk_router, "_has_active_booking_draft", lambda farmer_id, session_id: False)
    monkeypatch.setattr(adk_router, "_has_active_registration_draft", lambda farmer_id, session_id: False)


def _fake_order_turn(monkeypatch, calls):
    def turn(farmer_id, session_id, text, language="en-IN", include_audio=True):
        calls.append(text)
        return {"state": "QUANTITY", "response_text": "How many?", "response_audio_base64": None}

    monkeypatch.setattr(adk_router._order_supervisor, "turn", turn)


def test_order_in_progress_is_sticky_and_skips_the_classifier(monkeypatch):
    _no_other_drafts(monkeypatch)
    monkeypatch.setattr(adk_router, "_has_active_order_draft", lambda farmer_id, session_id: True)
    calls = []
    _fake_order_turn(monkeypatch, calls)

    async def must_not_classify(text):
        raise AssertionError("an order in progress must not be re-classified")

    monkeypatch.setattr(adk_router, "_classify_intent_async", must_not_classify)
    envelope = adk_router.route_turn_adk(FARMER, "s-1", "2", include_audio=False)
    assert envelope["agent"] == "order_supervisor"
    assert envelope["reply_text"] == "How many?"
    assert calls == ["2"]


def test_classified_order_message_goes_to_the_order_agent(monkeypatch):
    _no_other_drafts(monkeypatch)
    monkeypatch.setattr(adk_router, "_has_active_order_draft", lambda farmer_id, session_id: False)
    calls = []
    _fake_order_turn(monkeypatch, calls)

    async def classify(text):
        return "order"

    monkeypatch.setattr(adk_router, "_classify_intent_async", classify)
    envelope = adk_router.route_turn_adk(FARMER, "s-1", "I want to buy calcium gel", include_audio=False)
    assert envelope["agent"] == "order_supervisor"
    assert envelope["intent"] == "order"
    assert calls == ["I want to buy calcium gel"]


def test_channel_without_order_never_reaches_the_order_agent(monkeypatch):
    _no_other_drafts(monkeypatch)
    calls = []
    _fake_order_turn(monkeypatch, calls)

    async def classify(text):
        return "order"

    monkeypatch.setattr(adk_router, "_classify_intent_async", classify)
    monkeypatch.setattr(adk_router, "_has_active_order_draft", lambda farmer_id, session_id: False)
    blocked = adk_router.route_turn_adk(FARMER, "s-1", "buy calcium", include_audio=False,
                                        allowed_intents={"query", "appointment", "weather", "add_animal"})
    assert blocked["agent"] is None and blocked["intent"] == "order"

    # Same for a session that has an order in progress from the app.
    monkeypatch.setattr(adk_router, "_has_active_order_draft", lambda farmer_id, session_id: True)
    blocked = adk_router.route_turn_adk(FARMER, "s-1", "2", include_audio=False, allowed_intents={"query"})
    assert blocked["agent"] is None and blocked["intent"] == "order"
    assert calls == []


def test_only_an_unfinished_order_keeps_the_session(tmp_path, monkeypatch):
    sup = OrderSupervisor(tmp_path)
    monkeypatch.setattr(adk_router, "_order_supervisor", sup)
    assert adk_router._has_active_order_draft(FARMER, "s-1") is False  # nothing started

    draft = sup._fresh("s-1", FARMER, "en-IN")
    draft["state"] = "QUANTITY"
    sup._save(draft)
    assert adk_router._has_active_order_draft(FARMER, "s-1") is True

    draft["state"] = "CANCELLED"
    sup._save(draft)
    assert adk_router._has_active_order_draft(FARMER, "s-1") is False

    draft["state"] = "ORDERED"
    draft["submitted"] = True
    sup._save(draft)
    assert adk_router._has_active_order_draft(FARMER, "s-1") is False


def test_order_reply_audio_is_not_synthesized_twice(monkeypatch):
    """The order agent already returns response_audio_base64 (like the other
    supervisors), so the router's envelope must not synthesize again."""
    _no_other_drafts(monkeypatch)
    monkeypatch.setattr(adk_router, "_has_active_order_draft", lambda farmer_id, session_id: True)
    calls = []
    _fake_order_turn(monkeypatch, calls)

    def must_not_synthesize(*args, **kwargs):
        raise AssertionError("audio synthesized twice")

    monkeypatch.setattr(adk_router, "synthesize_speech", must_not_synthesize)
    envelope = adk_router.route_turn_adk(FARMER, "s-1", "2", include_audio=True)
    assert "response_audio_base64" not in envelope
