"""handle_inbound_batch runs as a background task after the webhook has
returned 200: every message is processed and one failure never stops the
rest."""
from types import SimpleNamespace

from services.whatsapp_channel import router


def test_one_failing_message_does_not_stop_the_rest(monkeypatch):
    seen = []

    def fake_handle(provider, msg):
        seen.append(msg.id)
        if msg.id == "m1":
            raise RuntimeError("boom")

    monkeypatch.setattr(router, "handle_inbound", fake_handle)
    router.handle_inbound_batch(None, [SimpleNamespace(id="m1"), SimpleNamespace(id="m2")])
    assert seen == ["m1", "m2"]


def test_empty_batch_does_nothing(monkeypatch):
    seen = []
    monkeypatch.setattr(router, "handle_inbound", lambda provider, msg: seen.append(msg))
    router.handle_inbound_batch(None, [])
    assert seen == []