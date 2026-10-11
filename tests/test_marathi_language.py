"""Tests for Marathi (mr-IN / mr) language support across Chocolate backend."""
import pytest
from unittest.mock import patch, MagicMock

from services.common.draft_supervisor import SUPPORTED_LANGUAGES, _lang
from services.appointment_supervisor.service import _TEXT as APPT_TEXT, _LABELS as APPT_LABELS, _VALUES as APPT_VALUES, _OTHER_LABEL
from services.animal_registration.service import _TEXT as REG_TEXT, _LABELS as REG_LABELS
from services.whatsapp_channel.messages import _TEXT as WA_TEXT, message as wa_message
from services.chat_orchestrator.intents import INTENTS, LANGUAGES
from services.query_agent.adk_agent import _COLUMN_LABELS, _NATIVE_DIGITS
from services.advisory.llm_advisory import _LANGUAGES as ADVISORY_LANGS
from services.voice_agent import tts


def test_supported_languages_has_marathi():
    assert "mr-IN" in SUPPORTED_LANGUAGES
    assert SUPPORTED_LANGUAGES["mr-IN"] == "Marathi"
    assert _lang("mr-IN") == "mr"
    assert _lang("mr") == "mr"


def test_appointment_supervisor_marathi_keys_match_hi():
    assert "mr" in APPT_TEXT
    assert set(APPT_TEXT["mr"].keys()) == set(APPT_TEXT["en"].keys())

    assert "mr" in APPT_LABELS
    assert set(APPT_LABELS["mr"].keys()) == set(APPT_LABELS["en"].keys())

    assert "mr" in APPT_VALUES
    # APPT_VALUES stores localized symptom maps; compare against 'hi' keys
    assert set(APPT_VALUES["mr"].keys()) == set(APPT_VALUES["hi"].keys())

    assert _OTHER_LABEL.get("mr") == "इतर"


def test_animal_registration_marathi_keys_match_english():
    assert "mr" in REG_TEXT
    assert set(REG_TEXT["mr"].keys()) == set(REG_TEXT["en"].keys())

    assert "mr" in REG_LABELS
    assert set(REG_LABELS["mr"].keys()) == set(REG_LABELS["en"].keys())


def test_whatsapp_messages_marathi_keys_match_english():
    assert "mr" in WA_TEXT
    assert set(WA_TEXT["mr"].keys()) == set(WA_TEXT["en"].keys())
    assert set(WA_TEXT["mr"]["intent_labels"].keys()) == set(WA_TEXT["en"]["intent_labels"].keys())

    msg = wa_message("mr-IN", "otp_wrong")
    assert "हा कोड चुकीचा आहे" in msg


def test_intents_marathi_support():
    assert "mr" in LANGUAGES
    for intent_name, spec in INTENTS.items():
        assert "mr" in spec.labels, f"Intent {intent_name} missing Marathi label"
        assert len(spec.labels["mr"].strip()) > 0


def test_query_agent_marathi_support():
    assert "mr" in _COLUMN_LABELS
    # _COLUMN_LABELS stores non-English translations; compare against 'hi' keys
    assert set(_COLUMN_LABELS["mr"].keys()) == set(_COLUMN_LABELS["hi"].keys())
    assert "mr" in _NATIVE_DIGITS
    assert _NATIVE_DIGITS["mr"] == "०१२३४५६७८९"


def test_advisory_marathi_support():
    assert "mr" in ADVISORY_LANGS
    assert ADVISORY_LANGS["mr"] == "Marathi"


def test_tts_marathi_falls_back_to_gtts():
    """Verify that since Polly has no Marathi voice, synthesize_speech routes to gTTS."""
    mock_polly = MagicMock()
    mock_gtts = MagicMock(return_value=(b"fake-mp3-bytes", None))

    with patch.object(tts, "_tts_cache_read", return_value=None), \
         patch.object(tts, "_tts_cache_write"), \
         patch.dict(tts._PROVIDERS, {"aws-polly": mock_polly, "gtts": mock_gtts}):
        audio, visemes = tts.synthesize_speech("चाचणी ऑडिओ युनिट टेस्ट युनिक", target_lang="mr")
        assert audio == b"fake-mp3-bytes"
        assert visemes is None
        mock_polly.assert_not_called()
        mock_gtts.assert_called_once_with("चाचणी ऑडिओ युनिट टेस्ट युनिक", "mr")


        