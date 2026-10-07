"""Whole-reply fallback words (services/common/reply_words.py) match only
the WHOLE reply, never a word inside an ordinary answer (PR #36 review:
"ताप आहे, औषध नको" used to cancel the whole draft), and the breed
"don't know" fallback works in every supported language (seen live:
Telugu "తెలియదు" kept re-asking for the breed)."""
import pytest

from services.common import reply_words
from services.common.reply_words import confirmation_signal, is_dont_know
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
    assert confirmation_signal(text, "mr-IN") == expected


@pytest.mark.parametrize("text", [
    "ताप आहे, औषध नको",
    "गौरीला ताप आहे आणि ती खात नाही",
    "हो, पण उद्या संध्याकाळी",
    "उद्या रद्द करा असं नाही",
    "",
])
def test_words_inside_an_answer_are_not_a_signal(text):
    assert confirmation_signal(text, "mr-IN") is None


def test_supervisors_use_the_shared_reply_words_fallback():
    """Both supervisors use the one shared whole-reply fallback in
    services/common/reply_words.py, with no per-language copies of their own."""
    for module in (appointment_service, registration_service):
        assert module.reply_words is reply_words
        assert not hasattr(module, "marathi_confirmation_signal")
        assert not hasattr(module, "is_marathi_dont_know")


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
    assert is_dont_know(text, "mr-IN")


@pytest.mark.parametrize("text", ["जात माहीत नाही पण वजन 20 किलो", "बीटल", "नाही", ""])
def test_marathi_dont_know_ignores_other_replies(text):
    assert not is_dont_know(text, "mr-IN")


# --- "don't know" in every supported language -------------------------

@pytest.mark.parametrize("language, text", [
    ("te-IN", "తెలియదు"),
    ("te-IN", "నాకు తెలియదు."),
    ("ta-IN", "தெரியாது"),
    ("ta-IN", "எனக்கு தெரியாது"),
    ("kn-IN", "ಗೊತ್ತಿಲ್ಲ"),
    ("hi-IN", "पता नहीं"),
    ("hi-IN", "मुझे पता नहीं।"),
    ("en-IN", "Not sure."),
    ("en-IN", "I don't know"),
    ("mr-IN", "माहीत नाही"),
    ("ml-IN", "അറിയില്ല"),
    ("ml-IN", "എനിക്ക് അറിയില്ല."),
])
def test_dont_know_in_every_language(language, text):
    assert is_dont_know(text, language)


@pytest.mark.parametrize("language, text", [
    ("te-IN", "బ్రీడ్ ఉస్మానాబాది, తెలియదు ఏమో"),  # longer answer, left to the LLM
    ("ta-IN", "சிரோஹி"),                          # a real breed answer
    ("hi-IN", "पता नहीं, शायद बीटल"),             # don't-know inside a longer answer
    ("mr-IN", "తెలియదు"),                         # Telugu word, Marathi farmer: no match
    ("bn-IN", "জানি না"),                          # unsupported language: no fallback
])
def test_dont_know_ignores_other_replies_and_languages(language, text):
    assert not is_dont_know(text, language)


@pytest.mark.parametrize("language, first_reply, dont_know", [
    ("te-IN", "ఐడి TETEST01, మేక, ఆడ", "తెలియదు"),
    ("ta-IN", "ஐடி TATEST01, வெள்ளாடு, பெண்", "தெரியாது"),
    ("kn-IN", "ಐಡಿ KNTEST01, ಮೇಕೆ, ಹೆಣ್ಣು", "ಗೊತ್ತಿಲ್ಲ"),
    ("hi-IN", "आईडी HITEST01, बकरी, मादा", "पता नहीं"),
    ("en-IN", "ID ENTEST01, goat, female", "not sure"),
    ("mr-IN", "आयडी MHTEST02, शेळी, मादी", "माहीत नाही."),
])
def test_registration_breed_dont_know_moves_on_even_if_llm_misses_it(
    tmp_path, monkeypatch, language, first_reply, dont_know,
):
    """Seen live: "माहीत नाही." (Marathi) and "తెలియదు" (Telugu) kept
    re-asking for the breed because only the LLM's field_unknown could
    skip it."""
    monkeypatch.setattr(registration_service, "synthesize_speech", lambda text, target_lang=None: (None, None), raising=False)
    monkeypatch.setattr(registration_service, "animals_for_farmer", lambda farmer_id: [])
    replies = iter([
        {"unique_animal_id": "TEST01", "species": "goat", "sex": "female"},
        {},  # LLM misses field_unknown on the don't-know reply
        {},
    ])
    seen = []

    def fake_extract(self, draft, text):
        seen.append(dict(draft["draft"]))
        return next(replies)

    monkeypatch.setattr(registration_service.AnimalRegistrationSupervisor, "_extract", fake_extract)
    supervisor = registration_service.AnimalRegistrationSupervisor(tmp_path)

    supervisor.turn("demo-farmer", "s-breed", first_reply, language)
    supervisor.turn("demo-farmer", "s-breed", dont_know, language)
    supervisor.turn("demo-farmer", "s-breed", "ok", language)

    # Draft as saved after the don't-know turn.
    assert seen[2].get("breed") == registration_service._BREED_UNSPECIFIED
    