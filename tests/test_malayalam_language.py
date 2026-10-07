"""Malayalam (ml-IN) support across the AI backend, plus a guard for every
language: each message catalog must have the same keys and the same
{placeholders} as English, so a message added in English but forgotten in
another language fails here instead of crashing a live chat with KeyError."""
from string import Formatter

import pytest

from services.common.draft_supervisor import SUPPORTED_LANGUAGES
from services.common.reply_words import is_dont_know
from services.chat_orchestrator.intents import INTENTS, LANGUAGES
from services.llm_service.bedrock_adapter import _LANG_INSTRUCTIONS
from services.query_agent.adk_agent import _COLUMN_LABELS, _to_native_digits, detect_language
from services.whatsapp_channel.messages import _TEXT as WHATSAPP_TEXT
import services.animal_registration.service as registration_service
import services.appointment_supervisor.service as appointment_service

LANG_PREFIXES = sorted({tag.split("-")[0] for tag in SUPPORTED_LANGUAGES})


def _placeholders(text: str) -> set:
    return {name for _, name, _, _ in Formatter().parse(text) if name}


def _check_catalog(catalog: dict, lang: str) -> None:
    english = catalog["en"]
    other = catalog[lang]
    assert set(other) == set(english), f"{lang} keys differ from en"
    for key, en_value in english.items():
        if isinstance(en_value, dict):
            assert set(other[key]) == set(en_value), f"{lang}.{key} keys differ from en"
        else:
            assert _placeholders(other[key]) == _placeholders(en_value), (
                f"{lang}.{key} placeholders differ from en"
            )


# --- every language: catalogs complete ---------------------------------

@pytest.mark.parametrize("lang", LANG_PREFIXES)
def test_registration_messages_complete(lang):
    _check_catalog(registration_service._TEXT, lang)


@pytest.mark.parametrize("lang", LANG_PREFIXES)
def test_appointment_messages_complete(lang):
    _check_catalog(appointment_service.AppointmentSupervisor.MESSAGES, lang)


@pytest.mark.parametrize("lang", LANG_PREFIXES)
def test_whatsapp_messages_complete(lang):
    _check_catalog(WHATSAPP_TEXT, lang)


# --- Malayalam specifically ---------------------------------------------

def test_malayalam_is_a_supported_language():
    assert "ml-IN" in SUPPORTED_LANGUAGES
    assert "ml" in LANGUAGES
    for spec in INTENTS.values():
        assert spec.labels.get("ml"), f"intent {spec.name} has no Malayalam label"


@pytest.mark.parametrize("cls", [
    registration_service.AnimalRegistrationSupervisor,
    appointment_service.AppointmentSupervisor,
])
def test_malayalam_draft_keeps_malayalam(tmp_path, cls):
    """The original bug: ml-IN was not in SUPPORTED_LANGUAGES, so every
    draft silently fell back to en-IN and replied in English."""
    draft = cls(tmp_path)._fresh("s-ml", "demo-farmer", "ml-IN")
    assert draft["language"] == "ml-IN"


def test_malayalam_welcome_is_malayalam(tmp_path):
    supervisor = registration_service.AnimalRegistrationSupervisor(tmp_path)
    welcome = supervisor._message("ml-IN", "welcome")
    assert any(0x0D00 <= ord(ch) <= 0x0D7F for ch in welcome)


def test_malayalam_registration_summary(tmp_path):
    supervisor = registration_service.AnimalRegistrationSupervisor(tmp_path)
    draft = {
        "language": "ml-IN",
        "draft": {
            "unique_animal_id": "MLTEST01",
            "species": "goat",
            "breed": registration_service._BREED_UNSPECIFIED,
            "sex": "female",
        },
    }
    summary = supervisor._summary(draft, localize_values=True)
    assert "ആട്" in summary
    assert "പെൺ" in summary
    assert "അറിയില്ല (നാടൻ/സങ്കര ഇനം)" in summary
    assert "goat" not in summary and "female" not in summary
    assert draft["draft"]["species"] == "goat"  # stored value stays English


def test_malayalam_appointment_extras():
    assert appointment_service._VALUES["ml"]["fever"] == "പനി"
    assert appointment_service._OTHER_LABEL["ml"]


@pytest.mark.parametrize("text", ["അറിയില്ല", "എനിക്ക് അറിയില്ല.", "  ഇനം   അറിയില്ല "])
def test_malayalam_dont_know(text):
    assert is_dont_know(text, "ml-IN")


def test_malayalam_prompts_and_query_labels():
    assert "Malayalam" in _LANG_INSTRUCTIONS["ml"]
    assert _COLUMN_LABELS["ml"]["breed"] == "ഇനം"


def test_query_agent_detects_malayalam_but_keeps_western_digits():
    assert detect_language("എനിക്ക് എത്ര മൃഗങ്ങൾ ഉണ്ട്?") == "ml"
    assert _to_native_digits("56 മൃഗങ്ങൾ", "ml") == "56 മൃഗങ്ങൾ"

    