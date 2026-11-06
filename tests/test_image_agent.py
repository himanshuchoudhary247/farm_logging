"""Photo turns: upload checks, agent choice from .env, the placeholder agent,
and the reply shape the app reads (same as /chat/turn)."""
from __future__ import annotations

import pytest

from services.common.draft_supervisor import SUPPORTED_LANGUAGES
from services.image_agent import registry, service
from services.image_agent.base import TASKS, ImageAgent, ImageRequest, ImageResult
from services.image_agent.service import MAX_IMAGE_BYTES, ImageTurnError, handle_image_turn
from services.image_agent.stub import StubImageAgent
from tests.image_fixtures import JPEG, PNG, WEBP


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for key in ["CHAT_IMAGE_AGENT"] + [f"CHAT_IMAGE_AGENT_{t.upper()}" for t in TASKS]:
        monkeypatch.delenv(key, raising=False)
    registry._cache.clear()
    yield
    registry._cache.clear()


def _turn(**overrides):
    args = dict(farmer_id="f-1", session_id="s-1", language="en-IN", text="", task="general",
                content_type="image/jpeg", image=JPEG)
    args.update(overrides)
    return handle_image_turn(**args)


@pytest.mark.parametrize("content_type,image", [("image/jpeg", JPEG), ("image/jpg", JPEG), ("image/png", PNG),
                                                ("image/webp", WEBP), ("image/jpeg; charset=binary", JPEG)],
                         ids=["jpeg", "jpg", "png", "webp", "jpeg_with_params"])
def test_accepted_photos_get_the_reply_shape_chat_turn_uses(content_type, image):
    out = _turn(content_type=content_type, image=image)
    assert out["agent"] == "image_agent"
    assert out["intent"] == "general"
    assert out["reply_text"] == out["result"]["response_text"]
    assert out["result"]["image_agent"] == "stub"
    assert out["result"]["data"] == {}
    assert out["timing"]["total_ms"] >= 0


@pytest.mark.parametrize("content_type,image,status", [
    ("image/gif", b"GIF89a" + b"\x00" * 100, 415),
    ("application/pdf", b"%PDF-1.4", 415),
    ("", JPEG, 415),
    ("image/jpeg", PNG, 415),            # declared JPG, really PNG
    ("image/png", b"not a photo at all", 415),
    ("image/jpeg", b"", 400),
    ("image/jpeg", JPEG[:3] + b"\x00" * MAX_IMAGE_BYTES, 413),
], ids=["gif", "pdf", "no_type", "jpg_is_really_png", "not_a_photo", "empty", "too_large"])
def test_bad_uploads_are_refused_before_any_agent_runs(content_type, image, status, monkeypatch):
    called = []
    monkeypatch.setattr(service, "get_agent", lambda task: called.append(task))
    with pytest.raises(ImageTurnError) as err:
        _turn(content_type=content_type, image=image)
    assert err.value.status_code == status
    assert called == []


def test_a_photo_of_exactly_the_limit_is_accepted():
    assert _turn(image=JPEG[:3] + b"\x00" * (MAX_IMAGE_BYTES - 3))["agent"] == "image_agent"


@pytest.mark.parametrize("overrides", [{"language": "fr-FR"}, {"session_id": " "}])
def test_bad_language_or_session_is_a_400(overrides):
    with pytest.raises(ImageTurnError) as err:
        _turn(**overrides)
    assert err.value.status_code == 400


@pytest.mark.parametrize("task,expected", [("weight", "weight"), (" HEALTH ", "health"), ("count", "count"),
                                           ("breed", "breed"), ("", "general"), ("selfie", "general"), (None, "general")])
def test_task_from_the_app_is_kept_or_falls_back_to_general(task, expected):
    assert _turn(task=task)["intent"] == expected


@pytest.mark.parametrize("language", sorted(SUPPORTED_LANGUAGES))
def test_stub_answers_honestly_in_every_language(language):
    reply = _turn(language=language)["reply_text"]
    assert reply and "{" not in reply
    if language != "en-IN":
        assert reply != StubImageAgent().analyze(
            ImageRequest("f", "s", "en-IN", "general", "", JPEG, "image/jpeg")).reply_text


def test_off_switches_photo_turns_off(monkeypatch):
    monkeypatch.setenv("CHAT_IMAGE_AGENT", "off")
    with pytest.raises(ImageTurnError) as err:
        _turn()
    assert err.value.status_code == 503


def test_one_task_can_be_switched_off_alone(monkeypatch):
    monkeypatch.setenv("CHAT_IMAGE_AGENT_WEIGHT", "off")
    with pytest.raises(ImageTurnError):
        _turn(task="weight")
    assert _turn(task="count")["agent"] == "image_agent"


def test_unknown_agent_name_falls_back_to_the_stub(monkeypatch):
    monkeypatch.setenv("CHAT_IMAGE_AGENT", "typo_agent")
    assert _turn()["result"]["image_agent"] == "stub"


class _WeightAgent:
    """What a real sub-agent looks like: the contract and nothing else."""
    name = "animal_weight"

    def __init__(self):
        self.requests = []

    def analyze(self, request: ImageRequest) -> ImageResult:
        self.requests.append(request)
        return ImageResult(reply_text="About 32 kg.", data={"weight_kg": 32.0})


def test_a_real_agent_replaces_the_stub_for_its_task_with_one_registry_line(monkeypatch):
    monkeypatch.setitem(registry._AGENTS, "animal_weight", _WeightAgent)
    monkeypatch.setenv("CHAT_IMAGE_AGENT_WEIGHT", "animal_weight")

    weight = _turn(task="weight", text="how heavy is she?", language="hi-IN")
    other = _turn(task="count")

    assert weight["reply_text"] == "About 32 kg."
    assert weight["result"]["data"] == {"weight_kg": 32.0}
    assert weight["result"]["image_agent"] == "animal_weight"
    request = registry._cache["animal_weight"].requests[0]
    assert (request.task, request.text, request.language, request.content_type) == (
        "weight", "how heavy is she?", "hi-IN", "image/jpeg")
    assert request.image == JPEG
    assert other["result"]["image_agent"] == "stub"
    assert isinstance(_WeightAgent(), ImageAgent)


def test_an_agent_that_fails_gives_a_clean_502(monkeypatch):
    class Broken:
        name = "broken"

        def analyze(self, request):
            raise RuntimeError("model timeout")

    monkeypatch.setitem(registry._AGENTS, "broken", Broken)
    monkeypatch.setenv("CHAT_IMAGE_AGENT", "broken")
    with pytest.raises(ImageTurnError) as err:
        _turn()
    assert err.value.status_code == 502
    assert "model timeout" not in err.value.detail


def test_the_question_is_trimmed_and_capped():
    agent = _WeightAgent()
    registry._cache["stub"] = agent
    _turn(text="  " + "x" * 5000 + "  ")
    assert agent.requests[0].text == "x" * service.MAX_TEXT_CHARS
