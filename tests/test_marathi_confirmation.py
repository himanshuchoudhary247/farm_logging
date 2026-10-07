"""Marathi confirmation fallback matches only the WHOLE reply, never a
word inside an ordinary answer (PR #36 review: "ताप आहे, औषध नको" used to
cancel the whole draft)."""
import pytest

from services.common.draft_supervisor import marathi_confirmation_signal
import services.appointment_supervisor.service as appointment_service
import services.animal_registration.service as registration_service


@pytest.mark.parametrize("text, expected", [
    ("रद्द करा", "cancel"),
    ("नको", "no"),
    ("कॅन्सल.", "cancel"),
    ("हो", "yes"),
    (" हो बरोबर ", "yes"),
    ("सबमिट!", "yes"),
    ("नाही।", "no"),
    ("बदल करा", "no"),
])
def test_whole_reply_confirmation_words(text, expected):
    assert marathi_confirmation_signal(text) == expected


@pytest.mark.parametrize("text", [
    "ताप आहे, औषध नको",
    "गौरीला ताप आहे आणि ती खात नाही",
    "हो, पण उद्या संध्याकाळी",
    "उद्या रद्द करा असं नाही",
    "",
])
def test_words_inside_an_answer_are_not_a_signal(text):
    assert marathi_confirmation_signal(text) is None


def test_supervisors_no_longer_use_substring_matching():
    # Both call sites must go through the shared exact-match helper.
    for module in (appointment_service, registration_service):
        assert module.marathi_confirmation_signal is marathi_confirmation_signal

def _record_confirm(monkeypatch, cls):
    """Replace confirm() so we can see whether a turn tried to cancel."""
    calls = []

    def fake_confirm(self, farmer_id, session_id, answer, include_audio=True):
        calls.append(answer)
        return {"status": "confirm-called", "answer": answer}

    monkeypatch.setattr(cls, "confirm", fake_confirm)
    return calls


def test_appointment_answer_containing_nako_does_not_cancel(tmp_path, monkeypatch):
    monkeypatch.setattr(appointment_service, "synthesize_speech", lambda text, target_lang=None: (None, None), raising=False)
    monkeypatch.setattr(
        appointment_service, "process_text_input",
        lambda text, session_id, pending_questions_override=None: {"entities": {}, "confirmation_signal": None},
    )
    monkeypatch.setattr(appointment_service, "animals_for_farmer", lambda farmer_id: [])
    calls = _record_confirm(monkeypatch, appointment_service.AppointmentSupervisor)
    supervisor = appointment_service.AppointmentSupervisor(tmp_path)

    supervisor.turn("demo-farmer", "s-answer", "ताप आहे, औषध नको", "mr-IN")
    assert "cancel" not in calls

    # Control: an explicit cancel still cancels.
    supervisor.turn("demo-farmer", "s-cancel", "रद्द करा", "mr-IN")
    assert calls and calls[-1] == "cancel"


def test_registration_answer_containing_nako_does_not_cancel(tmp_path, monkeypatch):
    monkeypatch.setattr(registration_service, "synthesize_speech", lambda text, target_lang=None: (None, None), raising=False)
    monkeypatch.setattr(registration_service.AnimalRegistrationSupervisor, "_extract", lambda self, draft, text: {})
    calls = _record_confirm(monkeypatch, registration_service.AnimalRegistrationSupervisor)
    supervisor = registration_service.AnimalRegistrationSupervisor(tmp_path)

    supervisor.turn("demo-farmer", "s-answer", "शेळी आहे, नाव नको", "mr-IN")
    assert "cancel" not in calls

    supervisor.turn("demo-farmer", "s-cancel", "रद्द करा", "mr-IN")
    assert calls and calls[-1] == "cancel"

@pytest.mark.parametrize("text", ["माहीत नाही", "माहीत नाही.", "मला माहित नाही", "  माहित   नाही ।"])
def test_marathi_dont_know_whole_reply(text):
    assert registration_service.is_marathi_dont_know(text)


@pytest.mark.parametrize("text", ["जात माहीत नाही पण वजन 20 किलो", "बीटल", "नाही", ""])
def test_marathi_dont_know_ignores_other_replies(text):
    assert not registration_service.is_marathi_dont_know(text)


def test_registration_breed_dont_know_moves_on_even_if_llm_misses_it(tmp_path, monkeypatch):
    """Seen live: "माहीत नाही." kept re-asking for the breed because only
    the LLM's field_unknown could skip it."""
    monkeypatch.setattr(registration_service, "synthesize_speech", lambda text, target_lang=None: (None, None), raising=False)
    replies = iter([
        {"unique_animal_id": "MHTEST02", "species": "goat", "sex": "female"},
        {},  # LLM misses field_unknown on "माहीत नाही."
        {},
    ])
    seen = []

    def fake_extract(self, draft, text):
        seen.append(dict(draft["draft"]))
        return next(replies)

    monkeypatch.setattr(registration_service.AnimalRegistrationSupervisor, "_extract", fake_extract)
    supervisor = registration_service.AnimalRegistrationSupervisor(tmp_path)

    supervisor.turn("demo-farmer", "s-breed", "आयडी MHTEST02, शेळी, मादी", "mr-IN")
    supervisor.turn("demo-farmer", "s-breed", "माहीत नाही.", "mr-IN")
    supervisor.turn("demo-farmer", "s-breed", "नको", "mr-IN")

    # Draft as saved after the "माहीत नाही." turn.
    assert seen[2].get("breed") == registration_service._BREED_UNSPECIFIED

