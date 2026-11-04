"""An animal registered through Chocolate is also created in main_backend
(flokiq_sync.create_animal), so it shows in the app's Animals list.

The registration tests drive the real AnimalRegistrationSupervisor turn by
turn (only the LLM extraction is faked, as in test_animal_registration.py),
so create_animal receives the draft values the real flow builds. The HTTP
call is faked at requests.post."""
from __future__ import annotations

import pytest

from services.animal_registration.service import AnimalRegistrationSupervisor
from services.flokiq_sync import client

FARMER = "9e95446d-c317-4074-b698-c8cc35325de6"


class _Resp:
    def __init__(self, status=201, body=None, text=""):
        self.status_code, self._body, self.text = status, body, text

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv("FLOKIQ_SYNC_ENABLED", "true")
    monkeypatch.setenv("FLOKIQ_SYNC_ANIMALS", "true")
    monkeypatch.setenv("FLOKIQ_API_BASE_URL", "https://backend.test/api/v1/")
    monkeypatch.setenv("FLOKIQ_INTERNAL_API_KEY", "secret-key")


def _capture(monkeypatch, resp):
    calls = []

    def fake_post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        if isinstance(resp, Exception):
            raise resp
        return resp

    monkeypatch.setattr(client.requests, "post", fake_post)
    return calls


# ---- build_animal_payload / create_animal ---------------------------------

def test_payload_keeps_only_values_main_backend_accepts():
    payload = client.build_animal_payload({
        "unique_animal_id": " GAURI-7 ", "species": "goat", "sex": "female", "breed": "Jamunapari",
        "status": "active", "birth_date": "2025-01-31", "initial_weight_kg": "24.5",
        "current_location": "", "official_tag_type": "rfid", "official_tag_number": "RF-1",
        "acquisition_date": "last year", "acquisition_source": "market", "sire_id": "", "dam_id": "MOTI",
    })
    assert payload == {
        "unique_animal_id": "GAURI-7", "species": "goat", "sex": "female", "breed": "Jamunapari",
        "status": "active", "birth_date": "2025-01-31", "initial_weight_kg": 24.5,
        "official_tag_type": "rfid", "official_tag_number": "RF-1", "acquisition_source": "market",
        "dam_id": "MOTI",
    }


@pytest.mark.parametrize("weight", ["", "heavy", "0", "-4", "5000", "nan"])
def test_payload_leaves_out_a_weight_that_is_not_a_real_one(weight):
    payload = client.build_animal_payload({"unique_animal_id": "A", "species": "goat", "sex": "male", "initial_weight_kg": weight})
    assert "initial_weight_kg" not in payload


@pytest.mark.parametrize("values", [
    {"species": "goat", "sex": "male"},
    {"unique_animal_id": "A", "species": "cow", "sex": "male"},
    {"unique_animal_id": "A", "species": "goat", "sex": ""},
    {"unique_animal_id": "A" * 300, "species": "goat", "sex": "male"},
])
def test_payload_is_none_without_valid_required_values(values):
    assert client.build_animal_payload(values) is None


def test_off_by_default(monkeypatch):
    monkeypatch.delenv("FLOKIQ_SYNC_ANIMALS", raising=False)
    monkeypatch.setenv("FLOKIQ_SYNC_ENABLED", "true")
    calls = _capture(monkeypatch, _Resp(201, {"id": "x"}))
    assert client.create_animal(FARMER, {"unique_animal_id": "A", "species": "goat", "sex": "male"})["status"] == "skipped"
    assert calls == []


def test_local_demo_farmer_is_skipped(on, monkeypatch):
    calls = _capture(monkeypatch, _Resp(201, {"id": "x"}))
    assert client.create_animal("f-001", {"unique_animal_id": "A", "species": "goat", "sex": "male"})["status"] == "skipped"
    assert calls == []


def test_created_posts_to_the_farmer_route_and_clears_the_cached_list(on, monkeypatch):
    client._farm_animals_cache[FARMER] = (10**12, [])
    calls = _capture(monkeypatch, _Resp(201, {"id": "uuid-1", "uniqueAnimalId": "A"}))
    out = client.create_animal(FARMER, {"unique_animal_id": "A", "species": "goat", "sex": "male"})
    assert out == {"status": "synced", "animal": {"id": "uuid-1", "uniqueAnimalId": "A"}}
    assert calls[0]["url"] == f"https://backend.test/api/v1/internal/farmers/{FARMER}/animals"
    assert calls[0]["headers"] == {"X-Internal-Api-Key": "secret-key"}
    assert FARMER not in client._farm_animals_cache


def test_already_there_counts_as_synced(on, monkeypatch):
    _capture(monkeypatch, _Resp(200, {"id": "uuid-old"}))
    assert client.create_animal(FARMER, {"unique_animal_id": "A", "species": "goat", "sex": "male"})["status"] == "synced"


@pytest.mark.parametrize("reason", ["tag_taken", "tag_number_taken"])
def test_conflict_reasons_are_passed_on(on, monkeypatch, reason):
    _capture(monkeypatch, _Resp(409, {"code": 409, "reason": reason}))
    assert client.create_animal(FARMER, {"unique_animal_id": "A", "species": "goat", "sex": "male"})["status"] == reason


@pytest.mark.parametrize("resp", [
    _Resp(409, {"code": 409, "reason": "something_else"}),
    _Resp(404, {"code": 404, "reason": "no_farm"}),
    _Resp(400, {"code": 400, "message": "bad"}),
    _Resp(500, None, "oops"),
    _Resp(503, None),
])
def test_other_answers_are_failures(on, monkeypatch, resp):
    _capture(monkeypatch, resp)
    assert client.create_animal(FARMER, {"unique_animal_id": "A", "species": "goat", "sex": "male"})["status"] == "failed"


def test_network_error_is_a_failure_not_a_crash(on, monkeypatch):
    import requests
    _capture(monkeypatch, requests.ConnectionError("down"))
    assert client.create_animal(FARMER, {"unique_animal_id": "A", "species": "goat", "sex": "male"})["status"] == "failed"


# ---- registration submit ---------------------------------------------------

@pytest.fixture
def registration(monkeypatch, tmp_path):
    """A supervisor whose local store is faked, plus a list of what it saved."""
    monkeypatch.setattr("services.animal_registration.service._try_mid_draft_escape",
                        lambda text, farmer_id, session_id, language: None)
    monkeypatch.setattr("services.animal_registration.service.synthesize_speech", lambda text, target_lang=None: (None, None))
    monkeypatch.setattr("services.animal_registration.service.animals_for_farmer", lambda farmer_id: [])
    saved = []

    def fake_append_animal(**kwargs):
        saved.append(kwargs)
        return type("Animal", (), {"id": "local-1", "tag_or_name": kwargs["tag_or_name"],
                                   "model_dump": lambda self: {**kwargs, "id": "local-1"}})()

    monkeypatch.setattr("services.animal_registration.service.append_animal", fake_append_animal)
    return AnimalRegistrationSupervisor(tmp_path), saved


def _register(sup, language="en-IN", tag="GAURI-7"):
    """Real turns up to the final readback, then yes."""
    calls = iter([
        {"species": "goat"},
        {"unique_animal_id": tag},
        {"breed": "Jamunapari", "sex": "female"},
        {"birth_date": "2025-01-31", "initial_weight_kg": "24"},
        {"wants_to_skip_optional": True},
    ])
    sup._extract = lambda draft, text: next(calls, {})
    sup.turn(FARMER, "s1", "register a goat", language, include_audio=False)
    sup.turn(FARMER, "s1", tag, language, include_audio=False)
    sup.turn(FARMER, "s1", "Jamunapari female", language, include_audio=False)
    sup.turn(FARMER, "s1", "born 31 January 2025, 24 kg", language, include_audio=False)
    readback = sup.turn(FARMER, "s1", "no thats all", language, include_audio=False)
    assert readback["state"] == "CONFIRMING"
    return sup.confirm(FARMER, "s1", "yes", include_audio=False)


def test_registration_sends_the_real_draft_values_then_saves_locally(on, monkeypatch, registration):
    sup, saved = registration
    calls = _capture(monkeypatch, _Resp(201, {"id": "uuid-1"}))

    out = _register(sup)

    assert out["status"] == "submitted"
    assert out["app_sync"] == "synced"
    assert out["response_text"] == "GAURI-7 has been registered successfully."
    assert calls[0]["json"] == {
        "unique_animal_id": "GAURI-7", "species": "goat", "sex": "female", "breed": "Jamunapari",
        "birth_date": "2025-01-31", "initial_weight_kg": 24.0,
    }
    assert len(saved) == 1


def test_id_taken_in_the_app_saves_nothing_and_asks_for_another_id(on, monkeypatch, registration):
    sup, saved = registration
    _capture(monkeypatch, _Resp(409, {"code": 409, "reason": "tag_taken"}))

    out = _register(sup)

    assert out["state"] == "COLLECTING"
    assert saved == []
    assert out["response_text"] == "The ID 'GAURI-7' is already used for another animal in the app. Please give a different ID."
    assert out["draft"].get("unique_animal_id") is None


def test_app_unreachable_still_saves_here_and_says_so(on, monkeypatch, registration):
    import requests
    sup, saved = registration
    _capture(monkeypatch, requests.Timeout("slow"))

    out = _register(sup)

    assert out["status"] == "submitted"
    assert out["app_sync"] == "failed"
    assert len(saved) == 1
    assert "could not add it to the app" in out["response_text"]


def test_sync_off_keeps_the_earlier_behaviour(monkeypatch, registration):
    monkeypatch.delenv("FLOKIQ_SYNC_ANIMALS", raising=False)
    sup, saved = registration
    calls = _capture(monkeypatch, _Resp(201, {"id": "uuid-1"}))

    out = _register(sup)

    assert calls == []
    assert out["app_sync"] == "skipped"
    assert out["response_text"] == "GAURI-7 has been registered successfully."
    assert len(saved) == 1


def test_a_second_yes_does_not_call_main_backend_again(on, monkeypatch, registration):
    sup, saved = registration
    calls = _capture(monkeypatch, _Resp(201, {"id": "uuid-1"}))
    _register(sup)

    again = sup.submit(FARMER, "s1", include_audio=False)

    assert again["status"] == "already_submitted"
    assert len(calls) == 1
    assert len(saved) == 1


@pytest.mark.parametrize("language", ["en-IN", "hi-IN", "mr-IN", "ta-IN", "te-IN", "kn-IN", "ml-IN"])
def test_every_language_has_the_new_messages(on, monkeypatch, registration, language):
    sup, _ = registration
    _capture(monkeypatch, _Resp(409, {"code": 409, "reason": "tag_taken"}))
    taken = _register(sup, language)
    assert "GAURI-7" in taken["response_text"] and "{" not in taken["response_text"]
    assert sup._message(language, "submitted_sync_failed", identifier="X").startswith("X")
