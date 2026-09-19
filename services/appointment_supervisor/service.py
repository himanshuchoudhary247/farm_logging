from __future__ import annotations

import json
import re
import uuid
from base64 import b64encode
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from filelock import FileLock

from services.flokiq_sync import client as flokiq_sync
from services.llm_service.bedrock_adapter import generate_health_recommendation
from services.query_agent.agent import process_query
from services.voice_agent.orchestrator import APPOINTMENT_FIELD_LABELS, process_text_input
from services.voice_agent.session_store import clear_session
from services.voice_agent.tts import synthesize_speech
from storage import (
    append_ai_health_log,
    append_appointment,
    append_health_log,
    atomic_write_json,
    animals_for_farmer,
    get_data_dir,
)


SUPPORTED_LANGUAGES = {"en-IN": "English", "hi-IN": "Hindi", "ta-IN": "Tamil", "te-IN": "Telugu", "kn-IN": "Kannada"}
REQUIRED_FIELDS = ("animal_identifier", "issue", "date", "time")
_BOOKING_INTENTS = {"CREATE_APPOINTMENT", "LOG_HEALTH"}

_TEXT = {
    "en": {
        "welcome": "Hello. Please tell me the animal name or tag, the issue and symptoms, and your preferred appointment date and time.",
        "correct": "I understood: {summary}",
        "updated": "Updated: {summary}",
        "yes_missing": "Thank you. Please provide {field}.",
        "ready": "All required details are complete. Would you like to submit this appointment?",
        "submit_yes": "Please say submit when you are ready to save the appointment.",
        "submitted": "The appointment and animal health record were saved successfully.",
        "animal_not_found": "I could not find an animal named or tagged '{identifier}' registered to you. Your registered animals are: {animals}. Please tell me the correct name, tag, or ID.",
        "no": "What would you like to correct?",
        "cancelled": "The appointment draft was cancelled and not submitted.",
        "missing_animal_identifier": "the animal name, tag, or ID",
        "missing_issue": "the animal issue and symptoms",
        "missing_date": "the preferred appointment date",
        "missing_time": "the preferred appointment time",
    },
    "hi": {
        "welcome": "नमस्ते। कृपया पशु का नाम या टैग, समस्या और लक्षण, तथा अपॉइंटमेंट की पसंदीदा तारीख और समय बताएं।",
        "correct": "मैंने समझा: {summary}",
        "updated": "अपडेट किया गया: {summary}",
        "yes_missing": "धन्यवाद। कृपया {field} बताएं।",
        "ready": "सभी जरूरी जानकारी पूरी है। क्या आप अपॉइंटमेंट जमा करना चाहते हैं?",
        "submit_yes": "सेव करने के लिए कृपया सबमिट कहें।",
        "submitted": "अपॉइंटमेंट और पशु स्वास्थ्य रिकॉर्ड सफलतापूर्वक सेव हो गए हैं।",
        "animal_not_found": "मुझे आपके नाम पर '{identifier}' नाम या टैग वाला कोई पशु नहीं मिला। आपके पंजीकृत पशु हैं: {animals}। कृपया सही नाम, टैग या आईडी बताएं।",
        "no": "आप किस जानकारी को सुधारना चाहते हैं?",
        "cancelled": "अपॉइंटमेंट ड्राफ्ट रद्द कर दिया गया है और सेव नहीं किया गया।",
        "missing_animal_identifier": "पशु का नाम, टैग या आईडी",
        "missing_issue": "पशु की समस्या और लक्षण",
        "missing_date": "अपॉइंटमेंट की तारीख",
        "missing_time": "अपॉइंटमेंट का समय",
    },
    "ta": {
        "welcome": "வணக்கம். விலங்கின் பெயர் அல்லது குறிச்சொல், பிரச்சினை மற்றும் அறிகுறிகள், விருப்பமான சந்திப்பு தேதி மற்றும் நேரத்தைச் சொல்லுங்கள்.",
        "correct": "நான் புரிந்துகொண்டது: {summary}",
        "updated": "புதுப்பிக்கப்பட்டது: {summary}",
        "yes_missing": "நன்றி. தயவுசெய்து {field} தெரிவிக்கவும்.",
        "ready": "தேவையான தகவல்கள் அனைத்தும் உள்ளன. இந்த சந்திப்பை சமர்ப்பிக்கவா?",
        "submit_yes": "சேமிக்க தயாரானதும் சமர்ப்பிக்கவும் என்று சொல்லுங்கள்.",
        "submitted": "சந்திப்பு மற்றும் விலங்கு சுகாதார பதிவு வெற்றிகரமாக சேமிக்கப்பட்டது.",
        "animal_not_found": "'{identifier}' என்ற பெயர் அல்லது டேக் கொண்ட விலங்கு உங்கள் பெயரில் இல்லை. உங்கள் பதிவு செய்யப்பட்ட விலங்குகள்: {animals}. சரியான பெயர், டேக் அல்லது ஐடி தெரிவிக்கவும்.",
        "no": "எந்த தகவலை திருத்த வேண்டும்?",
        "cancelled": "சந்திப்பு வரைவு ரத்து செய்யப்பட்டது.",
        "missing_animal_identifier": "விலங்கின் பெயர், குறிச்சொல் அல்லது ஐடி",
        "missing_issue": "விலங்கின் பிரச்சினை மற்றும் அறிகுறிகள்",
        "missing_date": "சந்திப்பு தேதி",
        "missing_time": "சந்திப்பு நேரம்",
    },
    "te": {
        "welcome": "నమస్కారం. జంతువు పేరు లేదా ట్యాగ్, సమస్య మరియు లక్షణాలు, మీకు కావలసిన అపాయింట్‌మెంట్ తేదీ మరియు సమయాన్ని చెప్పండి.",
        "correct": "నేను అర్థం చేసుకున్నది: {summary}. ఇది సరైనదేనా?",
        "updated": "వివరాలు నవీకరించబడ్డాయి. {summary} ఇది సరైనదేనా?",
        "yes_missing": "ధన్యవాదాలు. దయచేసి {field} చెప్పండి.",
        "ready": "అవసరమైన వివరాలు పూర్తయ్యాయి. ఈ అపాయింట్‌మెంట్‌ను సమర్పించాలా?",
        "submit_yes": "సేవ్ చేయడానికి సిద్ధంగా ఉన్నప్పుడు సబ్మిట్ అని చెప్పండి.",
        "submitted": "అపాయింట్‌మెంట్ మరియు జంతు ఆరోగ్య రికార్డు విజయవంతంగా సేవ్ చేయబడ్డాయి.",
        "animal_not_found": "'{identifier}' అనే పేరు లేదా ట్యాగ్ ఉన్న జంతువు మీ పేరు మీద కనిపించలేదు. మీ నమోదిత జంతువులు: {animals}. దయచేసి సరైన పేరు, ట్యాగ్ లేదా ఐడి చెప్పండి.",
        "no": "ఏ వివరాన్ని సరిచేయాలి?",
        "cancelled": "అపాయింట్‌మెంట్ డ్రాఫ్ట్ రద్దు చేయబడింది.",
        "missing_animal_identifier": "జంతువు పేరు, ట్యాగ్ లేదా ఐడి",
        "missing_issue": "జంతువు సమస్య మరియు లక్షణాలు",
        "missing_date": "అపాయింట్‌మెంట్ తేదీ",
        "missing_time": "అపాయింట్‌మెంట్ సమయం",
    },
    "kn": {
        "welcome": "ನಮಸ್ಕಾರ. ಪ್ರಾಣಿಯ ಹೆಸರು ಅಥವಾ ಟ್ಯಾಗ್, ಸಮಸ್ಯೆ ಮತ್ತು ಲಕ್ಷಣಗಳು, ನಿಮ್ಮ ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ದಿನಾಂಕ ಮತ್ತು ಸಮಯವನ್ನು ತಿಳಿಸಿ.",
        "correct": "ನಾನು ಅರ್ಥಮಾಡಿಕೊಂಡದ್ದು: {summary}. ಇದು ಸರಿಯೇ?",
        "updated": "ವಿವರಗಳನ್ನು ನವೀಕರಿಸಲಾಗಿದೆ. {summary} ಇದು ಸರಿಯೇ?",
        "yes_missing": "ಧನ್ಯವಾದಗಳು. ದಯವಿಟ್ಟು {field} ತಿಳಿಸಿ.",
        "ready": "ಅಗತ್ಯ ವಿವರಗಳು ಪೂರ್ಣಗೊಂಡಿವೆ. ಈ ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ಸಲ್ಲಿಸಬೇಕೇ?",
        "submit_yes": "ಉಳಿಸಲು ಸಿದ್ಧವಾದಾಗ ಸಬ್ಮಿಟ್ ಎಂದು ಹೇಳಿ.",
        "submitted": "ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ಮತ್ತು ಪ್ರಾಣಿಯ ಆರೋಗ್ಯ ದಾಖಲೆ ಯಶಸ್ವಿಯಾಗಿ ಉಳಿಸಲಾಗಿದೆ.",
        "animal_not_found": "'{identifier}' ಎಂಬ ಹೆಸರು ಅಥವಾ ಟ್ಯಾಗ್ ಇರುವ ಪ್ರಾಣಿ ನಿಮ್ಮ ಹೆಸರಿನಲ್ಲಿ ಕಂಡುಬಂದಿಲ್ಲ. ನಿಮ್ಮ ನೋಂದಾಯಿತ ಪ್ರಾಣಿಗಳು: {animals}. ದಯವಿಟ್ಟು ಸರಿಯಾದ ಹೆಸರು, ಟ್ಯಾಗ್ ಅಥವಾ ಐಡಿ ತಿಳಿಸಿ.",
        "no": "ಯಾವ ವಿವರವನ್ನು ಸರಿಪಡಿಸಬೇಕು?",
        "cancelled": "ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ಕರಡು ರದ್ದುಗೊಳಿಸಲಾಗಿದೆ.",
        "missing_animal_identifier": "ಪ್ರಾಣಿಯ ಹೆಸರು, ಟ್ಯಾಗ್ ಅಥವಾ ಐಡಿ",
        "missing_issue": "ಪ್ರಾಣಿಯ ಸಮಸ್ಯೆ ಮತ್ತು ಲಕ್ಷಣಗಳು",
        "missing_date": "ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ದಿನಾಂಕ",
        "missing_time": "ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ಸಮಯ",
    },
}

_LABELS = {
    "en": {"animal_identifier": "animal", "issue": "issue", "symptoms": "symptoms", "duration": "duration", "severity": "severity", "date": "date", "time": "time", "notes": "notes"},
    "hi": {"animal_identifier": "पशु", "issue": "समस्या", "symptoms": "लक्षण", "duration": "अवधि", "severity": "गंभीरता", "date": "तारीख", "time": "समय", "notes": "नोट्स"},
    "ta": {"animal_identifier": "விலங்கு", "issue": "பிரச்சினை", "symptoms": "அறிகுறிகள்", "duration": "காலம்", "severity": "தீவிரம்", "date": "தேதி", "time": "நேரம்", "notes": "குறிப்புகள்"},
    "te": {"animal_identifier": "జంతువు", "issue": "సమస్య", "symptoms": "లక్షణాలు", "duration": "వ్యవధి", "severity": "తీవ్రత", "date": "తేదీ", "time": "సమయం", "notes": "గమనికలు"},
    "kn": {"animal_identifier": "ಪ್ರಾಣಿ", "issue": "ಸಮಸ್ಯೆ", "symptoms": "ಲಕ್ಷಣಗಳು", "duration": "ಅವಧಿ", "severity": "ತೀವ್ರತೆ", "date": "ದಿನಾಂಕ", "time": "ಸಮಯ", "notes": "ಟಿಪ್ಪಣಿಗಳು"},
}

_VALUES = {
    "hi": {"not eating": "खाना नहीं खा रहा", "lethargy": "सुस्ती", "fever": "बुखार", "swelling": "सूजन", "limping": "लंगड़ाना", "wound": "घाव", "not drinking": "पानी नहीं पी रहा"},
    "ta": {"not eating": "சாப்பிடவில்லை", "lethargy": "சோர்வு", "fever": "காய்ச்சல்", "swelling": "வீக்கம்", "limping": "நொண்டுதல்", "wound": "காயம்", "not drinking": "தண்ணீர் குடிக்கவில்லை"},
    "te": {"not eating": "తినడం లేదు", "lethargy": "నీరసం", "fever": "జ్వరం", "swelling": "వాపు", "limping": "కుంటుతూ నడవడం", "wound": "గాయం", "not drinking": "నీరు తాగడం లేదు"},
    "kn": {"not eating": "ತಿನ್ನುತ್ತಿಲ್ಲ", "lethargy": "ಸುಸ್ತು", "fever": "ಜ್ವರ", "swelling": "ಊತ", "limping": "ಕುಂಟುವುದು", "wound": "ಗಾಯ", "not drinking": "ನೀರು ಕುಡಿಯುತ್ತಿಲ್ಲ"},
}


def _lang(language: str) -> str:
    return (language or "en-IN").split("-")[0].lower()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()




class AppointmentSupervisor:
    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or get_data_dir()
        self.intake_dir = self.data_dir / "appointment_intakes"

    def _path(self, session_id: str) -> Path:
        safe = "".join(ch for ch in session_id if ch.isalnum() or ch in "-_")
        return self.intake_dir / f"{safe}.json"

    def _fresh(self, session_id: str, farmer_id: str, language: str) -> dict[str, Any]:
        return {
            "session_id": session_id,
            "farmer_id": farmer_id,
            "language": language if language in SUPPORTED_LANGUAGES else "en-IN",
            "state": "COLLECTING",
            "draft": {"symptoms": [], "attachments": [], "miscellaneous_notes": ""},
            "confirmed_fields": [],
            "transcript_history": [],
            "confirmation_history": [],
            "submitted": False,
            "created_at": _now(),
            "updated_at": _now(),
        }

    def _load(self, session_id: str, farmer_id: str, language: str) -> dict[str, Any]:
        path = self._path(session_id)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return self._fresh(session_id, farmer_id, language)

    def _save(self, draft: dict[str, Any]) -> None:
        path = self._path(draft["session_id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(path) + ".lock"):
            draft["updated_at"] = _now()
            atomic_write_json(path, draft)

    def _copy_entities(self, draft: dict[str, Any], entities: dict[str, Any]) -> None:
        target = draft["draft"]
        for key, value in entities.items():
            if value not in (None, "", []):
                target[key] = value
        if not target.get("animal_identifier"):
            # animal_tag is the extraction schema's field for a bare
            # ear-tag/ID number (see bedrock_adapter.py's _EXTRACTION_TOOL_SPEC);
            # animal_name is a name. REQUIRED_FIELDS only checks
            # animal_identifier, so either one must bridge into it or a
            # correctly-extracted tag number silently never counts as
            # having answered the question at all.
            identifier = target.get("animal_tag") or target.get("animal_name")
            if identifier:
                target["animal_identifier"] = identifier
        if target.get("issue") and not target.get("symptoms"):
                target["symptoms"] = [target["issue"]]

    def _missing(self, draft: dict[str, Any]) -> list[str]:
        values = draft["draft"]
        return [field for field in REQUIRED_FIELDS if not values.get(field)]

    def _has_any_info(self, values: dict[str, Any]) -> bool:
        return any(
            v not in (None, "", [])
            for k, v in values.items()
            if k not in ("attachments", "miscellaneous_notes")
        )

    def _summary(self, draft: dict[str, Any]) -> str:
        values = draft["draft"]
        labels = _LABELS.get(_lang(draft["language"]), _LABELS["en"])
        values_map = _VALUES.get(_lang(draft["language"]), {})
        parts = []
        for field in ("animal_identifier", "issue", "symptoms", "duration", "severity", "date", "time"):
            value = values.get(field)
            if value not in (None, "", []):
                if isinstance(value, list):
                    value = ", ".join(values_map.get(str(item), str(item)) for item in value)
                if isinstance(value, str):
                    value = values_map.get(value, value)
                parts.append(f"{labels.get(field, field)}: {value}")
        if values.get("miscellaneous_notes"):
            parts.append(f"{labels['notes']}: {values['miscellaneous_notes']}")
        return "; ".join(parts) or "no appointment details yet"

    def _message(self, language: str, key: str, **values: str) -> str:
        catalog = _TEXT.get(_lang(language), _TEXT["en"])
        return catalog[key].format(**values)

    def _response(self, draft: dict[str, Any], text: str, input_transcript: str | None = None, include_audio: bool = True) -> dict[str, Any]:
        language = draft["language"]
        if include_audio:
            audio, audio_error = synthesize_speech(text, target_lang=_lang(language))
        else:
            audio, audio_error = None, None
        return {
            "session_id": draft["session_id"],
            "state": draft["state"],
            "language": language,
            "transcript": input_transcript,
            "draft": draft["draft"],
            "missing_fields": self._missing(draft),
            "response_text": text,
            "response_audio_base64": b64encode(audio).decode("ascii") if audio else None,
            "audio_error": audio_error,
        }

    def turn(self, farmer_id: str, session_id: str, text: str, language: str = "en-IN", include_audio: bool = True) -> dict[str, Any]:
        draft = self._load(session_id, farmer_id, language)
        if draft.get("submitted"):
            # Prior booking on this session_id is already saved permanently
            # (appointments.json/health_logs.json) -- that record is not
            # touched here. A new message on the same thread after submit
            # means the farmer wants to start another booking, not that the
            # thread is dead. Start a fresh draft under the same session_id
            # instead of 400ing forever on every message after submit.
            draft = self._fresh(session_id, farmer_id, language)
        draft["language"] = language if language in SUPPORTED_LANGUAGES else draft["language"]
        draft["transcript_history"].append({"text": text, "language": draft["language"], "at": _now()})

        # Tell the extraction model exactly what our own last message
        # asked for, so it can resolve the reply with real context instead
        # of a Python-side keyword/regex guess. Two things ride on this
        # one hint: (1) confirmation_signal (yes/no/cancel/submit) when
        # we're mid-confirmation or ready-to-submit -- classified by
        # actual meaning ("that's wrong, try again" = no) rather than
        # literal keyword matching, which used to misfire on ordinary
        # words like "enough" containing "no"; (2) which entity field a
        # bare reply like "1122" answers (draft["expected_field"], set
        # below and in confirm()'s "yes" branch) -- this extraction call
        # already has a designed mechanism for exactly this (see
        # _TOOL_SYSTEM_PROMPT's example 5: "10 am" + pending_questions:
        # ["appointment time"] -> {time: '10:00'}), appointment_supervisor
        # just never wired into it before, so bare tag/ID replies kept
        # landing in issue/symptoms instead with no way to correct it.
        # "CONFIRMING" is overloaded: it means BOTH "just asked a literal
        # yes/no confirm question" (nothing missing) AND "still mid-collection,
        # asked a proactive missing-field question in the same breath"
        # (expected_field set). Only the first is genuinely a yes/no/cancel
        # moment -- treating the second the same way misroutes a farmer's
        # frustrated-but-informative reply ("... arnt you smart enough")
        # into "What would you like to correct?" purely because the state
        # name says CONFIRMING, when the bot's actual last message was
        # asking for a specific field, not a yes/no confirmation.
        state = draft.get("state")
        awaiting_confirmation = state == "CONFIRMING" and not draft.get("expected_field")
        if awaiting_confirmation:
            pending = ["confirm these details are correct (yes/no), or cancel"]
        elif state == "READY_TO_SUBMIT":
            pending = ["submit the appointment now (yes/submit), or cancel"]
        elif draft.get("expected_field") in APPOINTMENT_FIELD_LABELS:
            pending = [APPOINTMENT_FIELD_LABELS[draft["expected_field"]]]
        else:
            pending = None

        result = process_text_input(text, session_id=f"{farmer_id}:{session_id}", pending_questions_override=pending)
        confirmation_signal = result.get("confirmation_signal")
        turn_entities = result.get("entities") or {}

        # Real gap, found via live testing: a genuine off-topic question
        # mid-booking ("any animal with ram") got forced through this state
        # machine's narrow yes/no/field lens and silently misread as a
        # correction/rejection, with no way to actually answer it.
        #
        # First attempt: rely on the extraction call's own "intent" field
        # to spot a genuinely different intent -- didn't work. Verified
        # directly (bypassing this code) that for this exact input the
        # model returns intent=null, confirmation_signal="no" -- it can't
        # confidently classify a vague phrase like "any animal with ram"
        # into any of the six defined intents, so there's no "switched
        # intent" signal to detect, and the forced yes/no-shaped pending
        # question nudges it toward "no" regardless of instruction wording.
        #
        # Working approach: when confirmation_signal="no" fires and
        # nothing new was actually extracted for this booking, ask
        # query_agent whether it can answer the text for real. A genuine
        # SQL+data result is strong empirical evidence this was an
        # answerable question, not a rejection -- far more reliable than
        # depending on a classification the model won't reliably make.
        answers_expected_field = bool(draft.get("expected_field")) and bool(turn_entities.get(draft["expected_field"]))
        if awaiting_confirmation and confirmation_signal == "no" and not answers_expected_field:
            probe = process_query(text, farmer_id)
            if probe.get("sql") and probe.get("data"):
                self._save(draft)
                return self._response(draft, probe.get("answer") or "", input_transcript=text, include_audio=include_audio)

        if awaiting_confirmation and confirmation_signal in {"yes", "no", "cancel"}:
            self._save(draft)
            return self.confirm(farmer_id, session_id, confirmation_signal, include_audio=include_audio)
        if state == "READY_TO_SUBMIT" and confirmation_signal in {"yes", "submit"}:
            # "yes" is the natural way to affirmatively answer "would you
            # like to submit?" -- the model correctly reports the farmer's
            # literal word (confirmation_signal="yes"), not the enum value
            # "submit", so both must count as consent here. Missing this
            # caused a real infinite loop: "yes" fell through unmatched,
            # regressed state back to CONFIRMING, and the next turn's
            # "done??" bounced it back to READY_TO_SUBMIT via confirm()'s
            # own "yes" handling -- never once reaching submit().
            self._save(draft)
            return self.submit(farmer_id, session_id, include_audio=include_audio)
        if state == "READY_TO_SUBMIT" and confirmation_signal == "cancel":
            self._save(draft)
            return self.confirm(farmer_id, session_id, "cancel", include_audio=include_audio)

        before = dict(draft["draft"])
        self._copy_entities(draft, result.get("entities") or {})

        missing = self._missing(draft)
        draft["expected_field"] = missing[0] if missing else None

        if draft["draft"] == before and missing:
            # Extraction found nothing new and something is still missing.
            # Previously this always resent the full 4-field "Hello,
            # please tell me..." welcome, discarding whatever was already
            # collected (a real bug: looked like the bot forgot the whole
            # conversation). Now: re-ask specifically for the field still
            # missing if anything has been collected already; only show
            # the full welcome when truly nothing has been said yet.
            draft["state"] = "COLLECTING"
            if self._has_any_info(draft["draft"]):
                field = self._message(draft["language"], f"missing_{missing[0]}")
                message = self._message(draft["language"], "yes_missing", field=field)
            else:
                message = self._message(draft["language"], "welcome")
            self._save(draft)
            return self._response(draft, message, input_transcript=text, include_audio=include_audio)

        draft["state"] = "CONFIRMING"
        self._save(draft)
        message = self._message(draft["language"], "correct", summary=self._summary(draft))
        if missing:
            # Proactively ask for the next missing required field in the
            # same turn, instead of only echoing back what was understood
            # and waiting for a separate "yes" before asking anything --
            # avoids a robotic "I understood: X" -> silence -> "I understood: X, Y"
            # loop with no question in it. Reuses the existing translated
            # "yes_missing" copy (already vetted in every supported
            # language) rather than adding new phrasing.
            field = self._message(draft["language"], f"missing_{missing[0]}")
            message = f"{message} {self._message(draft['language'], 'yes_missing', field=field)}"
        return self._response(draft, message, input_transcript=text, include_audio=include_audio)

    def confirm(self, farmer_id: str, session_id: str, response: str, include_audio: bool = True) -> dict[str, Any]:
        draft = self._load(session_id, farmer_id, "en-IN")
        if draft.get("submitted"):
            raise ValueError("This appointment intake has already been submitted")
        normalized = response.strip().lower()
        language = draft["language"]
        draft["confirmation_history"].append({"response": response, "at": _now()})
        if normalized in {"yes", "y", "haan", "ಹೌದು", "అవును", "ஆம்"}:
            draft["confirmed_fields"] = list(draft["draft"].keys())
            missing = self._missing(draft)
            draft["expected_field"] = missing[0] if missing else None
            if missing:
                draft["state"] = "COLLECTING"
                field = self._message(language, f"missing_{missing[0]}")
                message = self._message(language, "yes_missing", field=field)
            else:
                draft["state"] = "READY_TO_SUBMIT"
                message = self._message(language, "ready")
        elif normalized in {"no", "n", "wrong", "गलत", "இல்லை", "ಇಲ್ಲ", "కాదు"}:
            draft["state"] = "CORRECTING"
            message = self._message(language, "no")
        elif normalized in {"cancel", "cancelled", "रद्द", "ரத்து", "ರದ್ದು", "రద్దు"}:
            draft["state"] = "CANCELLED"
            message = self._message(language, "cancelled")
        else:
            draft["state"] = "CONFIRMING"
            result = process_text_input(response, session_id=f"{farmer_id}:{session_id}")
            self._copy_entities(draft, result.get("entities") or {})
            message = self._message(language, "updated", summary=self._summary(draft))
        self._save(draft)
        return self._response(draft, message, include_audio=include_audio)

    def submit(self, farmer_id: str, session_id: str, include_audio: bool = True) -> dict[str, Any]:
        draft = self._load(session_id, farmer_id, "en-IN")
        if draft.get("submitted"):
            return {"status": "already_submitted", "intake": draft}
        if draft.get("state") != "READY_TO_SUBMIT":
            raise ValueError("The appointment requires final confirmation before submission")
        values = draft["draft"]
        animal_id = values.get("animal_id")
        animals = animals_for_farmer(farmer_id)
        if not animal_id:
            wanted = str(values.get("animal_identifier") or "").lower()
            matches = [a for a in animals if wanted in {a.id.lower(), a.tag_or_name.lower()}]
            if matches:
                animal_id = matches[0].id
        if not animal_id:
            # Loop back into the conversation instead of raising -- a raw
            # exception here used to become a dead-end HTTP 400 with no way
            # to recover, breaking the one invariant every other branch of
            # this state machine keeps: a mistake gets a chance to be
            # corrected, not a wall. Data-driven, not a generic retry
            # prompt -- lists the farmer's actual registered animals so
            # they know what to say instead of guessing again.
            bad_identifier = str(values.get("animal_identifier") or "")
            animal_names = ", ".join(a.tag_or_name for a in animals) or self._message(draft["language"], "missing_animal_identifier")
            draft["draft"]["animal_identifier"] = None
            draft["draft"].pop("animal_id", None)
            draft["draft"].pop("animal_tag", None)
            draft["draft"].pop("animal_name", None)
            draft["state"] = "COLLECTING"
            draft["expected_field"] = "animal_identifier"
            self._save(draft)
            # process_text_input keeps its OWN persistent per-session entity
            # cache (services/voice_agent/session_store.py), independent of
            # this draft. Clearing our draft's animal fields above is not
            # enough -- that cache still holds the stale animal_tag/name,
            # and _copy_entities would silently re-merge it back in on the
            # very next turn, undoing this reset before the farmer's
            # correction ever had a chance. Real bug, found live: "GAURI"
            # typed right after this message still came back as "1122".
            clear_session(f"{farmer_id}:{session_id}")
            message = self._message(draft["language"], "animal_not_found", identifier=bad_identifier, animals=animal_names)
            return self._response(draft, message, include_audio=include_audio)
        health = append_health_log(farmer_id, animal_id, str(values.get("issue")), {
            "symptoms": values.get("symptoms", []),
            "duration": values.get("duration"),
            "severity": values.get("severity"),
            "temperature_c": values.get("temperature_c"),
            "current_medication": values.get("current_medication"),
            "attachments": values.get("attachments", []),
        }, str(values.get("miscellaneous_notes") or values.get("notes") or ""))
        appointment = append_appointment(farmer_id, str(values.get("date")), str(values.get("time")), str(values.get("doctor_id") or ""), str(values.get("miscellaneous_notes") or ""), health.id, animal_id, str(values.get("issue")), values)
        draft["draft"]["animal_id"] = animal_id
        draft["health_log_id"] = health.id
        draft["appointment_id"] = appointment.id
        draft["state"] = "SUBMITTED"
        draft["submitted"] = True
        self._save(draft)

        # Second agent in the handoff: appointment_supervisor has finished
        # collecting details, now hand the symptoms off to a dedicated
        # generation-tier agent for preliminary, non-diagnostic guidance to
        # show the farmer while they wait for the real vet visit already
        # booked above. Never raises -- returns empty fields on any failure,
        # so a generation-agent problem never blocks the booking that
        # already succeeded.
        recommendation = generate_health_recommendation(
            species=str(values.get("species") or ""),
            symptoms=values.get("symptoms") or [],
            issue=str(values.get("issue") or ""),
            severity=str(values.get("severity") or ""),
            duration=str(values.get("duration") or ""),
            language=_lang(draft["language"]),
        )

        # Our own AI-health-log record, shaped like flokiq's real
        # health_logs table but stored locally -- always on, independent of
        # FLOKIQ_SYNC_ENABLED. Lets us accumulate real data and iterate
        # without needing flokiq's team to first confirm it's safe to write
        # AI-generated diagnosis/risk fields into their shared table.
        severity_to_risk = {"mild": "Low", "moderate": "Medium", "severe": "High"}
        risk_level = severity_to_risk.get(str(values.get("severity") or "").lower())
        append_ai_health_log(
            farmer_id=farmer_id,
            animal_id=animal_id,
            pincode=str(values.get("weather_location") or ""),
            symptoms=values.get("symptoms") or [],
            risk_level=risk_level,
            ai_diagnosis_suggestion=recommendation["diagnosis_suggestion"],
            potential_ailments=recommendation["potential_ailments"],
            first_aid_advice=recommendation["first_aid_advice"],
        )

        # Best-effort sync to flokiq's DB. Local write above is already the
        # source of truth for this booking -- a sync failure here is logged
        # and swallowed inside flokiq_sync, never raised, never loses the
        # farmer's appointment.
        flokiq_health_log = flokiq_sync.create_health_log(
            user_id=farmer_id,
            pincode=str(values.get("weather_location") or ""),
            symptoms=values.get("symptoms") or [],
            animal_id=animal_id,
            risk_level=risk_level,
            ai_diagnosis_suggestion=recommendation["diagnosis_suggestion"],
            potential_ailments=recommendation["potential_ailments"],
            first_aid_advice=recommendation["first_aid_advice"],
        )
        flokiq_sync.create_appointment(
            farmer_id=farmer_id,
            date=str(values.get("date")),
            time=str(values.get("time")),
            notes=str(values.get("miscellaneous_notes") or values.get("notes") or ""),
            health_log_id=(flokiq_health_log or {}).get("log_id"),
        )

        # Show the recommendation to the farmer -- spoken via TTS same as
        # every other response, plus returned as structured data for the
        # frontend to render (e.g. clearly labeled "AI suggestion, not a
        # diagnosis" the way the data model's source=ai_unverified marker
        # already implies).
        recommendation_audio, recommendation_audio_error = (None, None)
        if include_audio and recommendation["first_aid_advice"]:
            recommendation_audio, recommendation_audio_error = synthesize_speech(
                recommendation["first_aid_advice"], target_lang=_lang(draft["language"]),
            )

        # response_text/response_audio_base64/audio_error at the top level,
        # same keys turn()/confirm() already return -- lets any caller
        # (UI, orchestrator envelope) read one consistent field regardless
        # of which state the conversation ended in, instead of needing a
        # separate branch just for the submit shape.
        submitted_text = self._message(draft["language"], "submitted")
        if recommendation.get("first_aid_advice"):
            submitted_text = f"{submitted_text} {recommendation['first_aid_advice']}"
        return {
            "status": "submitted",
            "intake": draft,
            "health_log": health.model_dump(),
            "appointment": appointment.model_dump(),
            "response_text": submitted_text,
            "response_audio_base64": (
                b64encode(recommendation_audio).decode("ascii") if recommendation_audio else None
            ),
            "audio_error": recommendation_audio_error,
            "ai_recommendation": {
                **recommendation,
                "source": "ai_unverified",
                "response_audio_base64": (
                    b64encode(recommendation_audio).decode("ascii") if recommendation_audio else None
                ),
                "audio_error": recommendation_audio_error,
            },
        }

    def attach(self, farmer_id: str, session_id: str, attachment: dict[str, Any]) -> dict[str, Any]:
        draft = self._load(session_id, farmer_id, "en-IN")
        if draft.get("submitted"):
            raise ValueError("This appointment intake has already been submitted")
        draft["draft"].setdefault("attachments", []).append(attachment)
        self._save(draft)
        return {"session_id": session_id, "attachments": draft["draft"]["attachments"], "draft": draft["draft"]}
