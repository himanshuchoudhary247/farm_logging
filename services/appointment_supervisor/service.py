from __future__ import annotations

import json
import uuid
from base64 import b64encode
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from filelock import FileLock

from services.flokiq_sync import client as flokiq_sync
from services.voice_agent.orchestrator import process_text_input
from services.voice_agent.tts import synthesize_speech
from storage import (
    append_appointment,
    append_health_log,
    atomic_write_json,
    animals_for_farmer,
    get_data_dir,
)


SUPPORTED_LANGUAGES = {"en-IN": "English", "hi-IN": "Hindi", "ta-IN": "Tamil", "te-IN": "Telugu", "kn-IN": "Kannada"}
REQUIRED_FIELDS = ("animal_identifier", "issue", "date", "time")

_TEXT = {
    "en": {
        "welcome": "Hello. Please tell me the animal name or tag, the issue and symptoms, and your preferred appointment date and time.",
        "correct": "I understood: {summary}",
        "updated": "Updated: {summary}",
        "yes_missing": "Thank you. Please provide {field}.",
        "ready": "All required details are complete. Would you like to submit this appointment?",
        "submit_yes": "Please say submit when you are ready to save the appointment.",
        "submitted": "The appointment and animal health record were saved successfully.",
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

    def _load(self, session_id: str, farmer_id: str, language: str) -> dict[str, Any]:
        path = self._path(session_id)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
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
        if target.get("animal_name") and not target.get("animal_identifier"):
            target["animal_identifier"] = target["animal_name"]
        if target.get("issue") and not target.get("symptoms"):
                target["symptoms"] = [target["issue"]]

    def _missing(self, draft: dict[str, Any]) -> list[str]:
        values = draft["draft"]
        return [field for field in REQUIRED_FIELDS if not values.get(field)]

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

    def _response_kind(self, text: str) -> str | None:
        value = text.strip().lower()
        if any(token in value for token in ("submit", "save", "जमा", "सबमिट", "சமர்ப்பி", "సమర్ప", "ಸಲ್ಲಿಸ")):
            return "submit"
        if any(token in value for token in ("yes", " y ", "हाँ", "हां", "सही", "ஆம்", "சரி", "అవును", "సరే", "ಹೌದು", "ಸರಿ")):
            return "yes"
        if any(token in value for token in ("no", "गलत", "नहीं", "இல்லை", "தவறு", "కాదు", "ತಪ್ಪು")):
            return "no"
        if any(token in value for token in ("cancel", "रद्द", "ரத்து", "రద్దు", "ರದ್ದು")):
            return "cancel"
        return None

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
            raise ValueError("This appointment intake has already been submitted")
        draft["language"] = language if language in SUPPORTED_LANGUAGES else draft["language"]
        draft["transcript_history"].append({"text": text, "language": draft["language"], "at": _now()})
        response_kind = self._response_kind(text)
        if draft.get("state") == "CONFIRMING" and response_kind in {"yes", "no", "cancel"}:
            self._save(draft)
            return self.confirm(farmer_id, session_id, response_kind, include_audio=include_audio)
        if draft.get("state") == "READY_TO_SUBMIT" and response_kind == "submit":
            self._save(draft)
            return self.submit(farmer_id, session_id)
        result = process_text_input(text, session_id=f"{farmer_id}:{session_id}")
        before = dict(draft["draft"])
        self._copy_entities(draft, result.get("entities") or {})
        if draft["draft"] == before and not self._missing(draft) == []:
            draft["state"] = "COLLECTING"
            message = self._message(draft["language"], "welcome")
            self._save(draft)
            return self._response(draft, message, input_transcript=text, include_audio=include_audio)
        draft["state"] = "CONFIRMING"
        self._save(draft)
        message = self._message(draft["language"], "correct", summary=self._summary(draft))
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

    def submit(self, farmer_id: str, session_id: str) -> dict[str, Any]:
        draft = self._load(session_id, farmer_id, "en-IN")
        if draft.get("submitted"):
            return {"status": "already_submitted", "intake": draft}
        if draft.get("state") != "READY_TO_SUBMIT":
            raise ValueError("The appointment requires final confirmation before submission")
        values = draft["draft"]
        animal_id = values.get("animal_id")
        if not animal_id:
            animals = animals_for_farmer(farmer_id)
            wanted = str(values.get("animal_identifier") or "").lower()
            matches = [a for a in animals if wanted in {a.id.lower(), a.tag_or_name.lower()}]
            if matches:
                animal_id = matches[0].id
        if not animal_id:
            raise ValueError("Could not match the appointment to a registered animal")
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

        # Best-effort sync to flokiq's DB. Local write above is already the
        # source of truth for this booking -- a sync failure here is logged
        # and swallowed inside flokiq_sync, never raised, never loses the
        # farmer's appointment.
        flokiq_health_log = flokiq_sync.create_health_log(
            user_id=farmer_id,
            pincode=str(values.get("weather_location") or ""),
            symptoms=values.get("symptoms") or [],
            animal_id=animal_id,
            risk_level={"mild": "Low", "moderate": "Medium", "severe": "High"}.get(str(values.get("severity") or "").lower()),
        )
        flokiq_sync.create_appointment(
            farmer_id=farmer_id,
            date=str(values.get("date")),
            time=str(values.get("time")),
            notes=str(values.get("miscellaneous_notes") or values.get("notes") or ""),
            health_log_id=(flokiq_health_log or {}).get("log_id"),
        )

        return {"status": "submitted", "intake": draft, "health_log": health.model_dump(), "appointment": appointment.model_dump()}

    def attach(self, farmer_id: str, session_id: str, attachment: dict[str, Any]) -> dict[str, Any]:
        draft = self._load(session_id, farmer_id, "en-IN")
        if draft.get("submitted"):
            raise ValueError("This appointment intake has already been submitted")
        draft["draft"].setdefault("attachments", []).append(attachment)
        self._save(draft)
        return {"session_id": session_id, "attachments": draft["draft"]["attachments"], "draft": draft["draft"]}
