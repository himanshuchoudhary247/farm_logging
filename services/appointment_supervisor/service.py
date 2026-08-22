from __future__ import annotations

import json
import re
import uuid
from base64 import b64encode
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from filelock import FileLock

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

    _NUMBER_WORDS: dict[str, dict[str, int]] = {
        "en": {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50},
        "hi": {"एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5, "छह": 6, "छः": 6, "सात": 7, "आठ": 8, "नौ": 9, "दस": 10, "ग्यारह": 11, "बारह": 12, "तेरह": 13, "चौदह": 14, "पंद्रह": 15, "सोलह": 16, "सत्रह": 17, "अठारह": 18, "उन्नीस": 19, "बीस": 20, "तीस": 30, "पैंतालीस": 45, "पंतालीस": 45},
        "ta": {"ஒன்று": 1, "இரண்டு": 2, "மூன்று": 3, "நான்கு": 4, "ஐந்து": 5, "ஆறு": 6, "ஏழு": 7, "எட்டு": 8, "ஒன்பது": 9, "பத்து": 10, "பதினொன்று": 11, "பன்னிரண்டு": 12, "பதிமூன்று": 13, "பதினான்கு": 14, "பதினைந்து": 15, "இருபது": 20, "முப்பது": 30, "நாற்பது": 40, "ஐம்பது": 50},
        "te": {"ఒకటి": 1, "రెండు": 2, "మూడు": 3, "నాలుగు": 4, "ఐదు": 5, "ఆరు": 6, "ఏడు": 7, "ఎనిమిది": 8, "తొమ్మిది": 9, "పది": 10, "పదకొండు": 11, "పన్నెండు": 12, "పదమూడు": 13, "పధమూడు": 13, "పద్నాలుగు": 14, "పదిహేను": 15, "ఇరవై": 20, "ముప్పై": 30, "నలభై": 40, "యాభై": 50},
        "kn": {"ಒಂದು": 1, "ಎರಡು": 2, "ಮೂರು": 3, "ನಾಲ್ಕು": 4, "ಐದು": 5, "ಆರು": 6, "ಏಳು": 7, "ಎಂಟು": 8, "ಒಂಬತ್ತು": 9, "ಹತ್ತು": 10, "ಹನ್ನೊಂದು": 11, "ಹನ್ನೆರಡು": 12, "ಹದಿಮೂರು": 13, "ಹದಿನಾಲ್ಕು": 14, "ಹದಿಐದು": 15, "ಇಪ್ಪತ್ತು": 20, "ಮೂವತ್ತು": 30, "ನಲವತ್ತು": 40, "ಐವತ್ತು": 50},
    }

    def _replace_number_words(self, text: str, lang: str) -> str:
        """Replace spoken number words with digits so regex patterns can match."""
        word_map = self._NUMBER_WORDS.get(lang)
        if not word_map:
            return text
        result = text
        for word, digit in sorted(word_map.items(), key=lambda kv: len(kv[0]), reverse=True):
            result = result.replace(word, str(digit))
        return result

    def _localized_entities(self, text: str, language: str) -> dict[str, Any]:
        """Fill common livestock phrases when translation/LLM is unavailable."""
        t = text.strip().lower()
        lang = _lang(language)
        t = self._replace_number_words(t, lang)
        entities: dict[str, Any] = {}
        patterns = {
            "en": {
                "not eating": ["not eating", "off feed", "stopped eating"],
                "fever": ["fever", "high temperature"],
                "swelling": ["swelling", "swollen", "foot swelling"],
                "lethargy": ["lethargic", "lethargy", "weak", "dull", "inactive"],
                "limping": ["limping", "lame", "limps"],
                "wound": ["wound", "injury", "cut"],
                "not drinking": ["not drinking", "dehydrated"],
            },
            "hi": {
                "not eating": ["खाना पीना बंद", "खाना बंद", "नहीं खा", "नहीं खाता", "खाना नहीं"],
                "fever": ["बुखार", "तेज गर्मी"],
                "swelling": ["सूजन", "फूल गया"],
                "lethargy": ["सुस्त", "सोई सोई", "कमजोर"],
                "limping": ["लंगड़ा", "लंगड़ाना"],
                "wound": ["घाव", "ज़ख्म"],
                "not drinking": ["पानी नहीं", "प्यास"],
            },
            "ta": {
                "not eating": ["சாப்பிடவில்லை", "சாப்பிடாமல்"],
                "fever": ["காய்ச்சல்"],
                "swelling": ["வீக்கம்"],
                "lethargy": ["சோர்வாக", "தூங்குகிறது", "சோர்வு"],
                "limping": ["நொண்டுதல்"],
                "wound": ["காயம்"],
                "not drinking": ["குடிக்கவில்லை", "தண்ணீர் குடிக்கவில்லை"],
            },
            "te": {
                "not eating": ["తినడం లేదు", "తినటం లేదు"],
                "fever": ["జ్వరం"],
                "swelling": ["వాపు"],
                "lethargy": ["నీరసంగా", "బలహీనంగా", "నీరసం"],
                "limping": ["కుంటు"],
                "wound": ["గాయం"],
                "not drinking": ["తాగడం లేదు", "నీరు తాగడం లేదు"],
            },
            "kn": {
                "not eating": ["ತಿನ್ನುತ್ತಿಲ್ಲ", "ತಿನ್ನುವುದಿಲ್ಲ"],
                "fever": ["ಜ್ವರ"],
                "swelling": ["ಊತ"],
                "lethargy": ["ಸುಸ್ತಾಗಿದೆ", "ದಣಿದಿದೆ", "ಸುಸ್ತು"],
                "limping": ["ಕುಂಟು"],
                "wound": ["ಗಾಯ"],
                "not drinking": ["ಕುಡಿಯುತ್ತಿಲ್ಲ", "ನೀರು ಕುಡಿಯುತ್ತಿಲ್ಲ"],
            },
        }
        for canonical, phrases in patterns.get(lang, {}).items():
            if any(phrase in t for phrase in phrases):
                entities["issue"] = canonical
                entities.setdefault("symptoms", []).append(canonical)

        name_patterns = {
            "hi": r"नाम\s+(?:है\s+)?([\u0900-\u097f\w-]+)",
            "ta": r"பெயர்\s+([^\s,]+)",
            "te": r"పేరు\s+([^\s,]+)",
            "kn": r"ಹೆಸರು\s+([^\s,]+)",
        }
        match = re.search(name_patterns.get(lang, r"$^"), t)
        if match:
            candidate = match.group(1).rstrip(",।.;!?")
            _stopwords = {
                "है", "हैं", "यह", "इसका", "पशु", "जानवर",
                "मतलब", "वो", "मेरे", "मेरा", "का", "की", "नाम", "टैग",
                "hai", "nam", "tag", "animal", "sheep", "goat",
            }
            if candidate not in _stopwords:
                entities["animal_name"] = candidate
                entities["animal_identifier"] = candidate

        # Tag number detection: "टैग है 1234" / "tag is 1234" / "tag number 1234"
        tag_patterns = {
            "hi": r"टैग\s*(?:है\s*)?(?:नंबर\s*)?(\d[\d\s]{1,15})\d",
            "en": r"tag\s*(?:is\s*)?(?:number\s*)?(\d[\d\s]{1,15})\d",
        }
        tag_match = re.search(tag_patterns.get(lang, r"$^"), t)
        if tag_match:
            tag_digits = re.sub(r"\s+", "", tag_match.group(1)) + tag_match.group(0)[-1]
            tag_digits = re.sub(r"[^\d]", "", tag_digits)
            if tag_digits:
                entities["animal_tag"] = tag_digits
                if not entities.get("animal_identifier"):
                    entities["animal_identifier"] = f"tag-{tag_digits}"

        # Also detect pure-digit tag when "टैग" appears with spelled-out English numbers
        if lang == "hi" and "टैग" in t and not entities.get("animal_tag"):
            # Transcribe often returns English words for digits: "वन टू थ्री फोर"
            en_word_to_digit = {"वन": "1", "टू": "2", "्री": "3", "थ्री": "3", "फोर": "4",
                                "फाइव": "5", "सिक्स": "6", "सेवन": "7", "एट": "8", "नाइन": "9", "जीरो": "0"}
            words = t.split()
            tag_parts = []
            capturing = False
            for w in words:
                if "टैग" in w:
                    capturing = True
                    continue
                if capturing:
                    digit = en_word_to_digit.get(w)
                    if digit:
                        tag_parts.append(digit)
                    elif w in {"है", "नंबर", "मेरे", "पास", "और"}:
                        continue
                    else:
                        break
            if tag_parts:
                tag_digits = "".join(tag_parts)
                entities["animal_tag"] = tag_digits
                if not entities.get("animal_identifier"):
                    entities["animal_identifier"] = f"tag-{tag_digits}"

        tomorrow_words = {"hi": "कल", "ta": "நாளை", "te": "రేపు", "kn": "ನಾಳೆ", "en": "tomorrow"}
        if tomorrow_words.get(lang) in t:
            entities["date"] = (datetime.now().date() + timedelta(days=1)).isoformat()
            entities["date_relative"] = "tomorrow"

        time_patterns = {
            "hi": r"(\d{1,2})\s*(?:वाजे|बजे|बजे|बज)",
            "ta": r"(\d{1,2})\s*மணி",
            "te": r"(\d{1,2})\s*గంటల",
            "kn": r"(\d{1,2})\s*ಗಂಟೆ",
            "en": r"(\d{1,2})\s*(?::\s*(\d{2}))?\s*(?:am|pm|morning|evening|afternoon|बजे)",
        }
        time_match = re.search(time_patterns.get(lang, r"$^"), t)
        if time_match:
            hour = int(time_match.group(1))
            minute = 0
            if time_match.lastindex and time_match.lastindex >= 2:
                try:
                    minute = int(time_match.group(2))
                except (ValueError, TypeError):
                    pass
            if lang == "en" and "pm" in t and hour < 12:
                hour += 12
            if lang == "en" and "afternoon" in t and hour < 12:
                hour += 12
            if lang == "en" and "evening" in t and hour < 12:
                hour += 12
            if lang == "hi" and "शाम" in t and hour < 12:
                hour += 12
            if lang == "te" and "సాయంత్రం" in t and hour < 12:
                hour += 12
            if lang == "ta" and "மாலை" in t and hour < 12:
                hour += 12
            if lang == "kn" and "ಸಂಜೆ" in t and hour < 12:
                hour += 12
            entities["time"] = f"{hour:02d}:{minute:02d}"

        if lang == "en" and "morning" in t:
            morning_match = re.search(r"(\d{1,2})\s*morning", t)
            if morning_match:
                entities["time"] = f"{int(morning_match.group(1)):02d}:00"

        date_patterns = {
            "en": r"(\d{1,2})\s+(january|february|march|april|may|june|july|august|september|october|november|december)",
            "hi": r"(\d{1,2})\s*(?:अगस्त|अगस्त|सितंबर|अक्टूबर|नवंबर|दिसंबर|जनवरी|फरवरी|मार्च|अप्रैल|मई|जून|जुलाई)",
        }
        month_map_en = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12}
        month_map_hi = {"अगस्त": 8, "सितंबर": 9, "अक्टूबर": 10, "नवंबर": 11, "दिसंबर": 12, "जनवरी": 1, "फरवरी": 2, "मार्च": 3, "अप्रैल": 4, "मई": 5, "जून": 6, "जुलाई": 7}
        date_match = re.search(date_patterns.get(lang, r"$^"), t)
        if date_match:
            day = int(date_match.group(1))
            month_word = date_match.group(2) if date_match.lastindex and date_match.lastindex >= 2 else ""
            month_map = month_map_en if lang == "en" else month_map_hi
            month = month_map.get(month_word)
            if month:
                year = datetime.now().year
                entities["date"] = f"{year}-{month:02d}-{day:02d}"

        return entities

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

    def _response(self, draft: dict[str, Any], text: str, input_transcript: str | None = None) -> dict[str, Any]:
        language = draft["language"]
        audio, audio_error = synthesize_speech(text, target_lang=_lang(language))
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

    def turn(self, farmer_id: str, session_id: str, text: str, language: str = "en-IN") -> dict[str, Any]:
        draft = self._load(session_id, farmer_id, language)
        if draft.get("submitted"):
            raise ValueError("This appointment intake has already been submitted")
        draft["language"] = language if language in SUPPORTED_LANGUAGES else draft["language"]
        draft["transcript_history"].append({"text": text, "language": draft["language"], "at": _now()})
        response_kind = self._response_kind(text)
        if draft.get("state") == "CONFIRMING" and response_kind in {"yes", "no", "cancel"}:
            self._save(draft)
            return self.confirm(farmer_id, session_id, response_kind)
        if draft.get("state") == "READY_TO_SUBMIT" and response_kind == "submit":
            self._save(draft)
            return self.submit(farmer_id, session_id)
        result = process_text_input(text, session_id=f"{farmer_id}:{session_id}")
        before = dict(draft["draft"])
        localized = self._localized_entities(text, draft["language"])
        merged_entities = dict(localized)
        merged_entities.update(result.get("entities") or {})
        self._copy_entities(draft, merged_entities)
        if draft["draft"] == before and not self._missing(draft) == []:
            draft["state"] = "COLLECTING"
            message = self._message(draft["language"], "welcome")
            self._save(draft)
            return self._response(draft, message, input_transcript=text)
        draft["state"] = "CONFIRMING"
        self._save(draft)
        message = self._message(draft["language"], "correct", summary=self._summary(draft))
        return self._response(draft, message, input_transcript=text)

    def confirm(self, farmer_id: str, session_id: str, response: str) -> dict[str, Any]:
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
        return self._response(draft, message)

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
        return {"status": "submitted", "intake": draft, "health_log": health.model_dump(), "appointment": appointment.model_dump()}

    def attach(self, farmer_id: str, session_id: str, attachment: dict[str, Any]) -> dict[str, Any]:
        draft = self._load(session_id, farmer_id, "en-IN")
        if draft.get("submitted"):
            raise ValueError("This appointment intake has already been submitted")
        draft["draft"].setdefault("attachments", []).append(attachment)
        self._save(draft)
        return {"session_id": session_id, "attachments": draft["draft"]["attachments"], "draft": draft["draft"]}
