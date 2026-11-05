"""The /farmers/{id}/chat/image-turn route over HTTP: multipart in, the same
reply shape as /chat/turn out, upload errors as HTTP status codes.

services/api_service/main.py runs validate_env() on import and exits when an
AWS variable is missing, so (as in test_farm_summary.py) only the missing
ones are filled with placeholders before the import. The photo turn makes no
AWS call, so nothing reaches AWS either way."""
from __future__ import annotations

import os

import pytest

from services.image_agent import registry

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 2000
URL = "/farmers/f-1/chat/image-turn"


@pytest.fixture
def client(monkeypatch):
    from fastapi.testclient import TestClient
    from utils.env_check import REQUIRED_ENV

    for name in REQUIRED_ENV:
        if not os.getenv(name):
            monkeypatch.setenv(name, "ap-south-1" if name == "AWS_REGION" else "test-placeholder")
    from services.api_service import main

    monkeypatch.delenv("CHAT_IMAGE_AGENT", raising=False)
    monkeypatch.setattr(main, "_API_KEY", "")
    registry._cache.clear()
    return TestClient(main.app)


def _post(client, image=JPEG, content_type="image/jpeg", **fields):
    form = {"session_id": "s-1", "language": "hi-IN", "text": "", "task": "count", **fields}
    return client.post(URL, data=form, files={"image": ("photo.jpg", image, content_type)})


def test_photo_turn_returns_the_chat_turn_shape(client):
    res = _post(client, text="kitne bakre hain?")
    assert res.status_code == 200
    body = res.json()
    assert body["agent"] == "image_agent"
    assert body["intent"] == "count"
    assert body["reply_text"]


def test_not_a_photo_is_415(client):
    assert _post(client, image=b"GIF89a" + b"\x00" * 50, content_type="image/gif").status_code == 415


def test_too_large_is_413(client):
    assert _post(client, image=JPEG[:3] + b"\x00" * (5 * 1024 * 1024)).status_code == 413


def test_switched_off_is_503(client, monkeypatch):
    monkeypatch.setenv("CHAT_IMAGE_AGENT", "off")
    assert _post(client).status_code == 503


def test_session_id_is_required(client):
    res = client.post(URL, data={"language": "en-IN"}, files={"image": ("p.jpg", JPEG, "image/jpeg")})
    assert res.status_code == 422
