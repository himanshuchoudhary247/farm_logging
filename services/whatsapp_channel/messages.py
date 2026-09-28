"""5-language message catalog for the WhatsApp channel.

Same lang-tag convention as the rest of the codebase (en/hi/ta/te/kn),
same {placeholder} format-string shape as animal_registration/messages
and appointment_supervisor's `_TEXT`. `_lang()` from
services.common.draft_supervisor is reused for the tag -> prefix
resolution and its "fall back to English on unknown language" behavior.

Enrollment prompt DELIBERATELY asks for "registered phone number or
username", never "farmer ID": farmers don't know their internal
f-001 UUIDs, so asking for one would be a dead end.
"""
from __future__ import annotations

from typing import Any

from services.common.draft_supervisor import _lang


_TEXT = {
    "en": {
        "blocked_intent": (
            "That kind of request is not available on WhatsApp right now. "
            "Please use the FarmHerd app for that. On WhatsApp you can: {allowed_summary}."
        ),
        "unknown_farmer_enroll_prompt": (
            "Hi! I don't recognize this WhatsApp number yet. Please reply with your "
            "registered phone number or your FarmHerd username so I can link this "
            "WhatsApp to your account."
        ),
        "unknown_farmer_no_enroll": (
            "This WhatsApp number is not registered with FarmHerd. Please contact "
            "support if you would like access."
        ),
        "enrollment_success": (
            "Thanks {name} -- your WhatsApp is now linked to your FarmHerd account. "
            "Send me your question and I'll help you."
        ),
        "enrollment_failed": (
            "I couldn't find a FarmHerd account matching that. Please reply with "
            "your registered phone number (like +91XXXXXXXXXX) or your username."
        ),
        "rate_limited": (
            "You are sending messages a bit fast. Please wait a moment and try again."
        ),
        "reply_trimmed_suffix": "\n\n... (reply trimmed; open the app to see the full answer)",
        # Human-readable labels for allowed_intents, used in the
        # blocked_intent message body.
        "intent_labels": {
            "query": "ask about your animals or records",
            "appointment": "book a vet appointment or log a health event",
            "weather": "check weather",
            "add_animal": "register a new animal",
        },
    },
    "hi": {
        "blocked_intent": (
            "यह अनुरोध अभी WhatsApp पर उपलब्ध नहीं है। कृपया इसके लिए FarmHerd ऐप का उपयोग करें। "
            "WhatsApp पर आप कर सकते हैं: {allowed_summary}।"
        ),
        "unknown_farmer_enroll_prompt": (
            "नमस्ते! मैं इस WhatsApp नंबर को अभी पहचान नहीं पा रहा। कृपया अपना पंजीकृत फोन नंबर "
            "या FarmHerd यूज़रनेम भेजें ताकि मैं इस WhatsApp को आपके खाते से जोड़ सकूं।"
        ),
        "unknown_farmer_no_enroll": (
            "यह WhatsApp नंबर FarmHerd में पंजीकृत नहीं है। कृपया सहायता से संपर्क करें।"
        ),
        "enrollment_success": (
            "धन्यवाद {name} -- आपका WhatsApp अब आपके FarmHerd खाते से जुड़ गया है। "
            "अपना प्रश्न भेजें, मैं मदद करूंगा।"
        ),
        "enrollment_failed": (
            "मुझे कोई मिलान वाला FarmHerd खाता नहीं मिला। कृपया अपना पंजीकृत फोन नंबर "
            "(जैसे +91XXXXXXXXXX) या यूज़रनेम भेजें।"
        ),
        "rate_limited": "आप बहुत तेज़ी से संदेश भेज रहे हैं। कृपया थोड़ी देर बाद फिर से कोशिश करें।",
        "reply_trimmed_suffix": "\n\n... (उत्तर छोटा किया गया है; पूरा उत्तर देखने के लिए ऐप खोलें)",
        "intent_labels": {
            "query": "अपने पशुओं या रिकॉर्ड के बारे में पूछना",
            "appointment": "पशु चिकित्सक अपॉइंटमेंट बुक करना या स्वास्थ्य घटना दर्ज करना",
            "weather": "मौसम देखना",
            "add_animal": "नया पशु पंजीकृत करना",
        },
    },
    "ta": {
        "blocked_intent": (
            "இந்த கோரிக்கை தற்போது WhatsApp-இல் கிடைக்கவில்லை. இதற்கு FarmHerd செயலியைப் "
            "பயன்படுத்தவும். WhatsApp-இல் நீங்கள் செய்யக்கூடியவை: {allowed_summary}."
        ),
        "unknown_farmer_enroll_prompt": (
            "வணக்கம்! இந்த WhatsApp எண்ணை என்னால் அடையாளம் காண முடியவில்லை. உங்கள் பதிவு "
            "செய்யப்பட்ட தொலைபேசி எண் அல்லது FarmHerd பயனர்பெயரை அனுப்பவும்."
        ),
        "unknown_farmer_no_enroll": (
            "இந்த WhatsApp எண் FarmHerd-இல் பதிவு செய்யப்படவில்லை. உதவிக்கு தொடர்பு கொள்ளவும்."
        ),
        "enrollment_success": (
            "நன்றி {name} -- உங்கள் WhatsApp இப்போது FarmHerd கணக்குடன் இணைக்கப்பட்டது. "
            "உங்கள் கேள்வியை அனுப்புங்கள்."
        ),
        "enrollment_failed": (
            "பொருந்தும் FarmHerd கணக்கு எதுவும் கிடைக்கவில்லை. உங்கள் பதிவு செய்யப்பட்ட "
            "தொலைபேசி எண் (+91XXXXXXXXXX போன்று) அல்லது பயனர்பெயரை அனுப்பவும்."
        ),
        "rate_limited": "நீங்கள் மிக வேகமாக செய்திகளை அனுப்புகிறீர்கள். சிறிது நேரம் காத்திருந்து மீண்டும் முயற்சிக்கவும்.",
        "reply_trimmed_suffix": "\n\n... (பதில் சுருக்கப்பட்டது; முழு பதிலைக் காண செயலியைத் திறக்கவும்)",
        "intent_labels": {
            "query": "உங்கள் விலங்குகள் அல்லது பதிவுகள் பற்றி கேட்க",
            "appointment": "கால்நடை மருத்துவர் சந்திப்பு அல்லது சுகாதார நிகழ்வு பதிவு",
            "weather": "வானிலை பார்க்க",
            "add_animal": "புதிய விலங்கு பதிவு செய்ய",
        },
    },
    "te": {
        "blocked_intent": (
            "ఈ అభ్యర్థన ప్రస్తుతం WhatsApp-లో అందుబాటులో లేదు. దీని కోసం FarmHerd యాప్‌ను "
            "ఉపయోగించండి. WhatsApp-లో మీరు చేయగలిగినవి: {allowed_summary}."
        ),
        "unknown_farmer_enroll_prompt": (
            "నమస్తే! ఈ WhatsApp నంబర్‌ను నేను గుర్తించలేదు. దయచేసి మీ నమోదిత ఫోన్ నంబర్ లేదా "
            "FarmHerd యూజర్‌నేమ్ పంపండి."
        ),
        "unknown_farmer_no_enroll": (
            "ఈ WhatsApp నంబర్ FarmHerd-లో నమోదు కాలేదు. దయచేసి మద్దతును సంప్రదించండి."
        ),
        "enrollment_success": (
            "ధన్యవాదాలు {name} -- మీ WhatsApp ఇప్పుడు FarmHerd ఖాతాతో లింక్ చేయబడింది. "
            "మీ ప్రశ్నను పంపండి."
        ),
        "enrollment_failed": (
            "సరిపోలే FarmHerd ఖాతా కనుగొనబడలేదు. దయచేసి మీ నమోదిత ఫోన్ నంబర్ "
            "(+91XXXXXXXXXX వంటిది) లేదా యూజర్‌నేమ్ పంపండి."
        ),
        "rate_limited": "మీరు చాలా వేగంగా సందేశాలు పంపుతున్నారు. కొంచెం వేచి మళ్ళీ ప్రయత్నించండి.",
        "reply_trimmed_suffix": "\n\n... (సమాధానం కుదించబడింది; పూర్తి సమాధానం కోసం యాప్ తెరవండి)",
        "intent_labels": {
            "query": "మీ జంతువుల లేదా రికార్డుల గురించి అడగడం",
            "appointment": "పశువైద్యుని అపాయింట్‌మెంట్ లేదా ఆరోగ్య సంఘటన నమోదు",
            "weather": "వాతావరణం చూడడం",
            "add_animal": "కొత్త జంతువును నమోదు చేయడం",
        },
    },
    "kn": {
        "blocked_intent": (
            "ಈ ವಿನಂತಿ ಪ್ರಸ್ತುತ WhatsApp-ನಲ್ಲಿ ಲಭ್ಯವಿಲ್ಲ. ಇದಕ್ಕಾಗಿ FarmHerd ಆಪ್ ಬಳಸಿ. "
            "WhatsApp-ನಲ್ಲಿ ನೀವು ಮಾಡಬಹುದಾದವು: {allowed_summary}."
        ),
        "unknown_farmer_enroll_prompt": (
            "ನಮಸ್ಕಾರ! ಈ WhatsApp ಸಂಖ್ಯೆಯನ್ನು ನಾನು ಗುರುತಿಸಲಾಗಿಲ್ಲ. ದಯವಿಟ್ಟು ನಿಮ್ಮ ನೋಂದಾಯಿತ "
            "ಫೋನ್ ಸಂಖ್ಯೆ ಅಥವಾ FarmHerd ಬಳಕೆದಾರಹೆಸರನ್ನು ಕಳುಹಿಸಿ."
        ),
        "unknown_farmer_no_enroll": (
            "ಈ WhatsApp ಸಂಖ್ಯೆ FarmHerd-ನಲ್ಲಿ ನೋಂದಾಯಿಸಲಾಗಿಲ್ಲ. ದಯವಿಟ್ಟು ಬೆಂಬಲವನ್ನು ಸಂಪರ್ಕಿಸಿ."
        ),
        "enrollment_success": (
            "ಧನ್ಯವಾದಗಳು {name} -- ನಿಮ್ಮ WhatsApp ಈಗ FarmHerd ಖಾತೆಗೆ ಲಿಂಕ್ ಆಗಿದೆ. "
            "ನಿಮ್ಮ ಪ್ರಶ್ನೆಯನ್ನು ಕಳುಹಿಸಿ."
        ),
        "enrollment_failed": (
            "ಹೊಂದಾಣಿಕೆಯಾಗುವ FarmHerd ಖಾತೆ ಸಿಗಲಿಲ್ಲ. ದಯವಿಟ್ಟು ನಿಮ್ಮ ನೋಂದಾಯಿತ ಫೋನ್ ಸಂಖ್ಯೆ "
            "(+91XXXXXXXXXX ರೀತಿ) ಅಥವಾ ಬಳಕೆದಾರಹೆಸರನ್ನು ಕಳುಹಿಸಿ."
        ),
        "rate_limited": "ನೀವು ತುಂಬಾ ವೇಗವಾಗಿ ಸಂದೇಶಗಳನ್ನು ಕಳುಹಿಸುತ್ತಿದ್ದೀರಿ. ಸ್ವಲ್ಪ ಕಾಯಿರಿ.",
        "reply_trimmed_suffix": "\n\n... (ಉತ್ತರ ಸಂಕ್ಷಿಪ್ತಗೊಳಿಸಲಾಗಿದೆ; ಪೂರ್ಣ ಉತ್ತರಕ್ಕಾಗಿ ಆಪ್ ತೆರೆಯಿರಿ)",
        "intent_labels": {
            "query": "ನಿಮ್ಮ ಪ್ರಾಣಿಗಳು ಅಥವಾ ದಾಖಲೆಗಳ ಬಗ್ಗೆ ಕೇಳಲು",
            "appointment": "ಪಶು ವೈದ್ಯರ ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ಅಥವಾ ಆರೋಗ್ಯ ಘಟನೆ ದಾಖಲಿಸಲು",
            "weather": "ಹವಾಮಾನ ನೋಡಲು",
            "add_animal": "ಹೊಸ ಪ್ರಾಣಿಯನ್ನು ನೋಂದಾಯಿಸಲು",
        },
    },
}


def message(language: str, key: str, **values: Any) -> str:
    """Look up a catalog string. Falls back to English on unknown language;
    raises KeyError with the specific missing key if the key doesn't exist
    in either catalog (matching draft_supervisor._message's shape)."""
    lang = _lang(language)
    catalog = _TEXT.get(lang) or _TEXT.get("en", {})
    return str(catalog[key]).format(**values)


def summarize_allowed_intents(language: str, allowed: "frozenset[str] | set[str]") -> str:
    """Turn `{query, appointment}` into a localized human-readable list
    like "ask about your animals or records; book a vet appointment or
    log a health event". Order is deterministic (allowed_intents order in
    the config isn't guaranteed, so sort for stability)."""
    lang = _lang(language)
    labels_map = (_TEXT.get(lang) or _TEXT["en"]).get("intent_labels") or _TEXT["en"]["intent_labels"]
    ordered = sorted(allowed)
    return "; ".join(labels_map.get(i, i) for i in ordered)
