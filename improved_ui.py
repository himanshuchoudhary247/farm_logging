import os
import hashlib
import streamlit as st

from gateways import (
    get_farmer_weather_location,
    set_farmer_weather_location,
    create_animal_for_farmer,
    create_farmer_weather_notification,
    create_health_log,
    create_preconsult_appointment,
    fetch_weather_alert,
    list_animals_for_farmer,
    list_farms_for_farmer,
    save_farm_onboarding,
    update_animal_for_farmer,
)
from services.voice_agent.orchestrator import process_text_input, process_voice
from services.voice_agent.session_store import clear_session, get_session
from services.voice_agent.tts import synthesize_speech
from services.llm_service.bedrock_adapter import get_weather_recommendation, extract_farm_onboarding, FARM_FIELDS


st.set_page_config(page_title="Farm Assistant", layout="wide", page_icon="🐄")

# Runtime defaults
os.environ.setdefault("AWS_REGION", "ap-south-1")
os.environ.setdefault("TRANSCRIBE_MODE", "aws")
os.environ.setdefault("VOICE_S3_BUCKET", "farmer-chat-audio-bucket-198799425726")
os.environ.setdefault("BEDROCK_MODEL_ID", "deepseek.v3-v1:0")
os.environ.setdefault("AWS_TRANSCRIBE_LANGUAGE_CODE", "en-IN")
os.environ.setdefault("TRANSCRIBE_FALLBACK_TO_LOCAL", "false")
os.environ.setdefault("AWS_TRANSCRIBE_MULTILINGUAL", "true")
os.environ.setdefault("AWS_TRANSCRIBE_LANGUAGE_OPTIONS", "en-IN,hi-IN,kn-IN,te-IN")
os.environ.setdefault("TTS_ENABLED", "true")
os.environ.setdefault("AWS_POLLY_VOICE_HI", "Aditi")
os.environ.setdefault("AWS_POLLY_VOICE_EN", "Raveena")
os.environ.setdefault("AWS_POLLY_VOICE_KN", "Aditi")
os.environ.setdefault("AWS_POLLY_VOICE_TE", "Aditi")
os.environ.setdefault("AWS_POLLY_LANGUAGE_CODE_HI", "hi-IN")
os.environ.setdefault("AWS_POLLY_LANGUAGE_CODE_EN", "en-IN")
os.environ.setdefault("AWS_POLLY_LANGUAGE_CODE_KN", "kn-IN")
os.environ.setdefault("AWS_POLLY_LANGUAGE_CODE_TE", "te-IN")
os.environ.setdefault("UI_RESPONSE_LANGUAGE", "auto")

# ── Session state init ──────────────────────────────────────────────
_DEFAULTS = {
    "messages": [],
    "last_result": None,
    "last_voice_hash": None,
    "last_saved_signature": None,
    "last_assistant_audio": None,
    "last_tts_error": None,
    "weather_pref_farmer_id": None,
    "weather_pref_value": "",
    "last_weather_data": None,
    "active_tab": "Chat",
    "pinned_lang": "auto",
    "onboarding_data": {},
    "onboarding_messages": [],
    "onboarding_complete": False,
    "onboarding_saved_id": None,
}
for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Sidebar ─────────────────────────────────────────────────────────
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/cow.png", width=60)
    st.title("Farm Assistant")

    with st.expander("Session Settings", expanded=True):
        session_id = st.text_input("Session ID", value="farmer-demo-1")
        farmer_id = st.text_input("Farmer ID", value="f-001")
        doctor_id = st.text_input("Doctor ID (optional)", value="")

        col_reset, col_status = st.columns(2)
        if col_reset.button("Reset Conversation", use_container_width=True, type="primary"):
            clear_session(session_id)
            for k in _DEFAULTS:
                st.session_state[k] = _DEFAULTS[k] if k not in ("weather_pref_value",) else ""
            st.session_state.onboarding_data = {}
            st.session_state.onboarding_messages = []
            st.session_state.onboarding_complete = False
            st.session_state.onboarding_saved_id = None
            st.rerun()

        cfg = f"🌐 {os.getenv('AWS_TRANSCRIBE_LANGUAGE_OPTIONS')}"
        col_status.metric("Languages", cfg)

    if st.checkbox("Show Examples", value=True):
        with st.expander("Quick Start Examples", expanded=True):
            st.markdown("**🐑 New Animal**")
            st.code('"add a new goat named gauri, female, sirohi, 2 years"')

            st.markdown("**✏️ Update Animal**")
            st.code('"update animal a-f-001-99 breed to jamunapari"')

            st.markdown("**🏥 Health Issue**")
            st.code('"my goat is not eating since yesterday"')

            st.markdown("**📅 Book Appointment**")
            st.code('"book an appointment for tomorrow at 5pm"')

            st.markdown("**🌤️ Weather**")
            st.code('"weather alert for 411001"')

    st.markdown("---")
    st.subheader("🌐 Output Language")
    lang_options = {
        "auto": "Dynamic (auto-detect from input)",
        "hi": "हिन्दी (Hindi)",
        "kn": "ಕನ್ನಡ (Kannada)",
        "te": "తెలుగు (Telugu)",
        "en": "English",
        "mix": "Hinglish (हिंग्लिश)",
    }
    selected = st.selectbox(
        "Response language",
        options=list(lang_options.keys()),
        format_func=lambda x: lang_options[x],
        index=list(lang_options.keys()).index(st.session_state.pinned_lang)
        if st.session_state.pinned_lang in lang_options
        else 0,
        key="lang_selector",
    )
    if selected != st.session_state.pinned_lang:
        st.session_state.pinned_lang = selected
        st.rerun()

    st.caption(f"🤖 Model: `{os.getenv('BEDROCK_MODEL_ID')}`")

# ── Helper functions (all reused from original) ────────────────────

def _is_hindi_text(text: str) -> bool:
    t = str(text or "")
    return any("\u0900" <= ch <= "\u097F" for ch in t)


def _is_kannada_text(text: str) -> bool:
    t = str(text or "")
    return any("\u0C80" <= ch <= "\u0CFF" for ch in t)


def _is_telugu_text(text: str) -> bool:
    t = str(text or "")
    return any("\u0C00" <= ch <= "\u0C7F" for ch in t)


def _is_hinglish_text(text: str) -> bool:
    t = str(text or "").lower()
    if not t.strip() or _is_hindi_text(t):
        return False

    hindi_markers = {
        "mera", "meri", "mujhe", "hai", "nahi", "nahin",
        "kya", "ka", "ki", "ke", "kr", "kar", "kal", "aaj",
        "bhai", "please", "doctor", "dawai", "bukhar", "khana",
    }
    english_markers = {
        "appointment", "update", "details", "animal",
        "issue", "severity", "medicine", "time", "date",
    }
    words = {w.strip(".,!?") for w in t.split() if w.strip(".,!?")}
    has_hi = any(w in words for w in hindi_markers)
    has_en = any(w in words for w in english_markers)
    return has_hi and has_en


def _is_script_code_mix(text: str, script: str) -> bool:
    t = str(text or "")
    has_latin = any("a" <= ch.lower() <= "z" for ch in t)
    if script == "kn":
        has_native = _is_kannada_text(t)
    elif script == "te":
        has_native = _is_telugu_text(t)
    else:
        has_native = _is_hindi_text(t)
    return has_native and has_latin


_LANG_TRANSLATIONS = {
    "hi": {
        "Please provide:": "कृपया बताएं:",
        "whether this is a new animal registration or an existing animal update": "यह नया पशु पंजीकरण है या पहले से मौजूद पशु का अपडेट",
        "animal ID or animal name/tag": "पशु आईडी या पशु का नाम/टैग",
        "the details to update": "अपडेट करने वाली जानकारी",
        "species": "प्रजाति",
        "sex (male/female)": "लिंग (नर/मादा)",
        "breed": "नस्ल",
        "age in years": "उम्र (वर्षों में)",
        "feeding details": "खुराक/फीडिंग विवरण",
        "issue/symptoms": "समस्या/लक्षण",
        "duration": "अवधि",
        "severity (mild/moderate/severe)": "गंभीरता (हल्का/मध्यम/गंभीर)",
        "current medication (or 'none')": "चल रही दवा (या 'कोई नहीं')",
        "appointment date": "अपॉइंटमेंट की तारीख",
        "appointment time": "अपॉइंटमेंट का समय",
    },
    "kn": {
        "Please provide:": "ದಯವಿಟ್ಟು ತಿಳಿಸಿ:",
        "animal ID or animal name/tag": "ಪ್ರಾಣಿಯ ID ಅಥವಾ ಹೆಸರು/ಟ್ಯಾಗ್",
        "species": "ಜಾತಿ",
        "sex (male/female)": "ಲಿಂಗ (ಗಂಡು/ಹೆಣ್ಣು)",
        "breed": "ತಳಿ",
        "age in years": "ವಯಸ್ಸು (ವರ್ಷಗಳಲ್ಲಿ)",
        "feeding details": "ಆಹಾರ ವಿವರಗಳು",
        "issue/symptoms": "ಸಮಸ್ಯೆ/ಲಕ್ಷಣಗಳು",
        "duration": "ಅವಧಿ",
        "severity (mild/moderate/severe)": "ತೀವ್ರತೆ (ಸಾಮಾನ್ಯ/ಮಧ್ಯಮ/ತೀವ್ರ)",
        "current medication (or 'none')": "ಪ್ರಸ್ತುತ ಔಷಧಿ (ಅಥವಾ 'none')",
        "appointment date": "ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ದಿನಾಂಕ",
        "appointment time": "ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ಸಮಯ",
    },
    "te": {
        "Please provide:": "దయచేసి చెప్పండి:",
        "animal ID or animal name/tag": "జంతువు ID లేదా పేరు/ట్యాగ్",
        "species": "జాతి",
        "sex (male/female)": "లింగం (male/female)",
        "breed": "జాతి రకం",
        "age in years": "వయస్సు (సంవత్సరాల్లో)",
        "feeding details": "ఆహార వివరాలు",
        "issue/symptoms": "సమస్య/లక్షణాలు",
        "duration": "వ్యవధి",
        "severity (mild/moderate/severe)": "తీవ్రత (mild/moderate/severe)",
        "current medication (or 'none')": "ప్రస్తుత మందులు (లేదా 'none')",
        "appointment date": "అపాయింట్‌మెంట్ తేదీ",
        "appointment time": "అపాయింట్‌మెంట్ సమయం",
    },
}


def _translate_followup(q: str, lang: str) -> str:
    out = str(q or "").strip()
    mapping = _LANG_TRANSLATIONS.get(lang, {})
    for src, dst in mapping.items():
        out = out.replace(src, dst)
    return out


def _resolve_pinned_lang() -> str:
    return st.session_state.get("pinned_lang", "auto")


_LANG_CHANGE_PATTERNS = [
    "speak in", "speak in hindi", "speak in kannada", "speak in telugu",
    "speak in english", "speak in hinglish",
    "switch to", "change to", "change language to",
    "hindi mein bolo", "kannada maatadu", "kannada maatadi",
    "telugu maatlaadu", "telugu lo cheppu",
    "english lo cheppu", "english maatadu",
    "bolo", "baat karo",
]
_LANG_NAME_MAP = {
    "hindi": "hi", "hind": "hi",
    "kannada": "kn", "kannad": "kn", "kannada maatadu": "kn", "kannada maatadi": "kn",
    "telugu": "te", "telugu maatlaadu": "te", "telugu lo cheppu": "te",
    "english": "en", "english lo cheppu": "en", "english maatadu": "en",
    "hinglish": "mix", "hing": "mix",
}


def _detect_language_change(text: str):
    """Returns language code str if user requested a language change, else None."""
    t = str(text or "").lower().strip()
    for pattern in _LANG_CHANGE_PATTERNS:
        if pattern in t:
            for name, code in _LANG_NAME_MAP.items():
                if name in t:
                    return code
            return "en"
    return None


def _response_language(text: str) -> str:
    pinned = _resolve_pinned_lang()
    if pinned != "auto":
        return pinned

    forced = os.getenv("UI_RESPONSE_LANGUAGE", "auto").strip().lower()
    forced_map = {
        "hi": "hi", "hindi": "hi",
        "kn": "kn", "kannada": "kn",
        "te": "te", "telugu": "te",
        "mix": "mix", "hinglish": "mix", "code-mix": "mix", "code_mix": "mix",
        "en": "en", "english": "en",
    }
    if forced in forced_map:
        return forced_map[forced]

    if _is_hindi_text(text):
        return "mix-hi" if _is_script_code_mix(text, "hi") else "hi"
    if _is_kannada_text(text):
        return "mix-kn" if _is_script_code_mix(text, "kn") else "kn"
    if _is_telugu_text(text):
        return "mix-te" if _is_script_code_mix(text, "te") else "te"
    if _is_hinglish_text(text):
        return "mix-hi"
    return "en"


def _resolve_animal_id_for_farmer(scope_farmer_id, entities):
    animal_id = entities.get("animal_id")
    if animal_id:
        return animal_id
    animal_name = str(entities.get("animal_name") or "").strip().lower()
    if not animal_name:
        return None
    for a in list_animals_for_farmer(scope_farmer_id):
        if str(a.tag_or_name).strip().lower() == animal_name:
            return a.id
    return None


def _save_from_result(scope_farmer_id, scope_doctor_id, result):
    intent = result.get("intent")
    entities = dict(result.get("entities") or {})

    if intent == "CREATE_ANIMAL":
        row = create_animal_for_farmer(
            farmer_id=scope_farmer_id,
            tag_or_name=str(entities.get("animal_name") or "").strip(),
            species=str(entities.get("species") or "").strip(),
            sex=str(entities.get("sex") or "").strip(),
            breed=str(entities.get("breed") or "").strip(),
            age_years=entities.get("age_years"),
            feeding_details=str(entities.get("feeding_details") or "").strip(),
        )
        return {"kind": "animal_created", "row": row.model_dump()}

    if intent == "UPDATE_ANIMAL":
        animal_id = _resolve_animal_id_for_farmer(scope_farmer_id, entities)
        updates = {
            "species": entities.get("species"),
            "sex": entities.get("sex"),
            "breed": entities.get("breed"),
            "age_years": entities.get("age_years"),
            "feeding_details": entities.get("feeding_details"),
        }
        row = update_animal_for_farmer(
            farmer_id=scope_farmer_id,
            animal_id=animal_id,
            animal_name=entities.get("animal_name"),
            updates=updates,
        )
        return {"kind": "animal_updated", "row": row.model_dump()}

    if intent == "LOG_HEALTH":
        animal_id = _resolve_animal_id_for_farmer(scope_farmer_id, entities)
        if not animal_id:
            raise ValueError("Could not resolve animal ID for health log")
        symptoms = entities.get("symptoms") or []
        if isinstance(symptoms, str):
            symptoms = [symptoms]
        issue = str(entities.get("issue") or ", ".join(symptoms) or "health issue").strip()
        row = create_health_log(
            farmer_id=scope_farmer_id,
            animal_id=animal_id,
            issue=issue,
            params=entities,
            notes="Saved from assistant",
        )
        return {"kind": "health_log_created", "row": row.model_dump()}

    if intent == "CREATE_APPOINTMENT":
        animal_id = _resolve_animal_id_for_farmer(scope_farmer_id, entities)
        if not animal_id:
            raise ValueError("Could not resolve animal ID for appointment")
        payload = create_preconsult_appointment(
            farmer_id=scope_farmer_id,
            animal_id=animal_id,
            issue=str(entities.get("issue") or "").strip(),
            date=str(entities.get("date") or "").strip(),
            time=str(entities.get("time") or "").strip(),
            duration=str(entities.get("duration") or "").strip(),
            severity=str(entities.get("severity") or "").strip(),
            current_medication=str(entities.get("current_medication") or "").strip(),
            temperature_c=entities.get("temperature_c"),
            doctor_id=scope_doctor_id,
            notes="Saved from assistant",
        )
        return {"kind": "appointment_preconsult_created", "row": payload}

    raise ValueError(f"Save not supported for intent: {intent}")


# ── Core chat logic ─────────────────────────────────────────────────

def run_turn(user_text=None, audio_bytes=None):
    if user_text is not None:
        result = process_text_input(user_text, session_id=session_id)
        user_view_text = user_text
    else:
        result = process_voice(audio_bytes, session_id=session_id)
        user_view_text = result.get("meta", {}).get("raw_text", "<voice input>")

    st.session_state.messages.append({"role": "user", "content": user_view_text})

    followups = result.get("follow_up_questions", [])
    detected_lang = _response_language(user_view_text)
    verbal_change = _detect_language_change(user_view_text)
    if verbal_change:
        st.session_state.pinned_lang = verbal_change
        lang = verbal_change
    else:
        lang = detected_lang

    if result.get("intent") == "WEATHER_ALERT" and not followups and result.get("complete"):
        entities = result.get("entities") or {}
        location_query = str(entities.get("weather_location") or "").strip()
        if not location_query:
            location_query = get_farmer_weather_location(farmer_id)
        if location_query:
            days = int(entities.get("forecast_days") or 3)
            country = str(entities.get("country_code") or "in")
            weather = fetch_weather_alert(
                location_or_pin=location_query, country_code=country, days=days
            )
            result["weather_alert"] = weather
            result["entities"]["weather_location"] = location_query
            result["entities"]["forecast_days"] = days
            result["entities"]["country_code"] = country
            risk = str(weather.get("risk_level") or "low")
            if risk in {"medium", "high"}:
                try:
                    create_farmer_weather_notification(
                        farmer_id=farmer_id,
                        location_or_pin=location_query,
                        country_code=country,
                        days=days,
                    )
                except Exception:
                    pass
        else:
            result["follow_up_questions"] = ["Please provide: pin code or location for weather alert."]
            result["complete"] = False
            followups = result["follow_up_questions"]

    if followups:
        formatted = []
        for q in followups:
            q_text = str(q).strip()
            if not q_text.lower().startswith("please provide:"):
                q_text = f"Please provide: {q_text}"
            if lang == "hi":
                q_text = _translate_followup(q_text, "hi")
            elif lang in {"mix", "mix-hi"}:
                q_text = _translate_followup(q_text, "hi")
            elif lang in {"kn", "mix-kn"}:
                q_text = _translate_followup(q_text, "kn")
            elif lang in {"te", "mix-te"}:
                q_text = _translate_followup(q_text, "te")
            formatted.append(q_text)
        assistant_text = " | ".join(formatted)
    elif result.get("complete") and result.get("intent"):
        if result.get("intent") == "WEATHER_ALERT" and result.get("weather_alert"):
            weather = result.get("weather_alert") or {}
            assistant_text = str(weather.get("summary") or "Weather alert prepared.")
        else:
            msgs = {
                "hi": "बहुत बढ़िया, मुझे सारी जानकारी मिल गई है। अंतिम JSON नीचे तैयार है।",
                "kn": "ಚೆನ್ನಾಗಿದೆ, ನನಗೆ ಎಲ್ಲಾ ಮಾಹಿತಿ ಸಿಕ್ಕಿದೆ. ಅಂತಿಮ JSON ಕೆಳಗೆ ಸಿದ್ಧವಾಗಿದೆ.",
                "te": "చాలా బాగుంది, నాకు మొత్తం సమాచారం వచ్చింది. చివరి JSON కింద సిద్ధంగా ఉంది.",
                "mix": "Badiya, mujhe sari jankari mil gayi hai. Final JSON neeche ready hai.",
                "en": "Great, I have everything I need. Final JSON is ready below.",
            }
            if lang in msgs:
                assistant_text = msgs[lang]
            elif lang in {"mix-hi"}:
                assistant_text = msgs["mix"]
            elif lang in {"mix-kn"}:
                assistant_text = msgs["kn"]
            elif lang in {"mix-te"}:
                assistant_text = msgs["te"]
            else:
                assistant_text = msgs["en"]
    else:
        msgs = {
            "hi": "ठीक है, आपकी जानकारी दर्ज कर ली गई है।",
            "kn": "ಸರಿ, ನಿಮ್ಮ ಇನ್‌ಪುಟ್ ದಾಖಲಿಸಲಾಗಿದೆ.",
            "te": "సరే, మీ ఇన్‌పుట్‌ను నమోదు చేశాను.",
            "mix": "Thik hai, maine aapka input capture kar liya.",
            "en": "Got it. I captured your input.",
        }
        if lang in msgs:
            assistant_text = msgs[lang]
        elif lang in {"mix-hi"}:
            assistant_text = msgs["mix"]
        elif lang in {"mix-kn"}:
            assistant_text = msgs["kn"]
        elif lang in {"mix-te"}:
            assistant_text = msgs["te"]
        else:
            assistant_text = msgs["en"]

    tts_lang_map = {
        "hi": "hi", "mix": "hi", "mix-hi": "hi",
        "kn": "kn", "mix-kn": "kn",
        "te": "te", "mix-te": "te",
    }
    tts_lang = tts_lang_map.get(lang, "en")
    assistant_audio, tts_error = synthesize_speech(assistant_text, target_lang=tts_lang)
    st.session_state.last_assistant_audio = assistant_audio
    st.session_state.last_tts_error = tts_error

    msg = {"role": "assistant", "content": assistant_text}
    if assistant_audio:
        msg["audio"] = assistant_audio
    elif tts_error:
        msg["tts_error"] = tts_error
    st.session_state.messages.append(msg)
    st.session_state.last_result = result


def render_save_button(result):
    intent = result.get("intent")
    complete = result.get("complete", False)
    if not complete or not intent:
        return
    if intent not in {"CREATE_ANIMAL", "UPDATE_ANIMAL", "LOG_HEALTH", "CREATE_APPOINTMENT"}:
        return

    sig = f"{session_id}:{intent}:{result.get('meta', {}).get('raw_text', '')}:{hash(str(result.get('entities', {})))}"
    labels = {
        "CREATE_APPOINTMENT": "Save Pre-consult + Appointment",
        "CREATE_ANIMAL": "Create Animal",
        "UPDATE_ANIMAL": "Update Animal",
        "LOG_HEALTH": "Save Health Log",
    }
    label = labels.get(intent, "Save Record")

    if st.session_state.last_saved_signature == sig:
        st.info("✅ Already saved.")
        return
    if st.button(label, type="primary", use_container_width=True):
        try:
            saved = _save_from_result(farmer_id, doctor_id, result)
            st.session_state.last_saved_signature = sig
            st.success(f"Saved: {saved.get('kind')}")
            st.json(saved.get("row"))
        except Exception as e:
            st.error(f"Save failed: {e}")


def render_language_badge(text):
    lang = _response_language(text)
    pinned = _resolve_pinned_lang()
    badges = {
        "hi": "🔤 Hindi",
        "kn": "🔤 Kannada",
        "te": "🔤 Telugu",
        "mix": "🔤 Hinglish",
        "mix-hi": "🔤 Hinglish",
        "mix-kn": "🔤 Kannada+English",
        "mix-te": "🔤 Telugu+English",
        "en": "🔤 English",
    }
    label = badges.get(lang, "🔤 English")
    if pinned != "auto":
        label += " 📌"
    return label


# ════════════════════════════════════════════════════════════════════
#  MAIN PAGE - TABS
# ════════════════════════════════════════════════════════════════════

tab_chat, tab_weather, tab_animals, tab_onboard, tab_settings = st.tabs(
    ["💬 Chat", "🌤️ Weather", "🐄 My Animals", "📋 Onboarding", "⚙️ Session"]
)

# ── TAB 1: CHAT ────────────────────────────────────────────────────

with tab_chat:
    st.subheader("Conversation")

    chat_container = st.container()
    with chat_container:
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])
                if msg.get("role") == "user":
                    st.caption(render_language_badge(msg["content"]))
                if msg.get("role") == "assistant":
                    if msg.get("audio"):
                        st.audio(msg["audio"], format="audio/mp3")
                    elif msg.get("tts_error"):
                        st.caption(f"🔇 Voice not available: {msg['tts_error']}")

    text_query = st.chat_input("Type your message (or answer follow-up)")
    if text_query:
        run_turn(user_text=text_query)
        st.rerun()

    with st.container():
        st.markdown("---")
        voice_col1, voice_col2 = st.columns([3, 1])
        with voice_col1:
            pending = []
            if st.session_state.last_result:
                pending = st.session_state.last_result.get("follow_up_questions", []) or []
            voice_label = "Record voice answer for follow-up" if pending else "Record voice for next turn"
            if pending:
                st.caption("📌 Follow-up pending: answer by voice or text.")
            audio = st.audio_input(voice_label)
        with voice_col2:
            st.write("")
            st.write("")
            if st.session_state.last_assistant_audio:
                if st.button("🔊 Play Last Response", use_container_width=True):
                    pass

        if audio is not None:
            audio_bytes = audio.getvalue()
            current_hash = hashlib.sha256(audio_bytes).hexdigest()
            if st.session_state.last_voice_hash != current_hash:
                st.session_state.last_voice_hash = current_hash
                with st.spinner("Processing voice..."):
                    run_turn(audio_bytes=audio_bytes)
                st.rerun()

    with st.expander("📋 Last Pipeline Output"):
        if st.session_state.last_result:
            result = st.session_state.last_result
            st.markdown(f"**Intent:** `{result.get('intent')}`")
            st.markdown(f"**Complete:** `{result.get('complete', False)}`")
            followups = result.get("follow_up_questions", [])
            if followups:
                st.markdown("**Follow-up questions**")
                for q in followups:
                    st.write(f"- {q}")
            if result.get("complete") and result.get("intent"):
                st.json(result)
                render_save_button(result)
        else:
            st.info("No turns yet.")

# ── TAB 2: WEATHER ─────────────────────────────────────────────────

with tab_weather:
    st.subheader("🌤️ Weather Alerts & Recommendations")

    if st.session_state.weather_pref_farmer_id != farmer_id:
        st.session_state.weather_pref_farmer_id = farmer_id
        try:
            st.session_state.weather_pref_value = get_farmer_weather_location(farmer_id) or ""
        except Exception:
            st.session_state.weather_pref_value = ""

    loc_col1, loc_col2 = st.columns([2, 1])
    with loc_col1:
        weather_location = st.text_input(
            "📍 Enter pin code or location name",
            value=st.session_state.weather_pref_value or "411001",
            key="improved_weather_location",
        )
    with loc_col2:
        weather_country = st.text_input("🌐 Country code", value="in", key="improved_weather_country")

    weather_days = st.slider(
        "📅 Forecast horizon (days)", min_value=1, max_value=7, value=3,
        key="improved_weather_days",
    )

    wcol1, wcol2, wcol3 = st.columns(3)
    with wcol1:
        if st.button("💾 Save as Default Location", use_container_width=True):
            try:
                saved = set_farmer_weather_location(farmer_id, weather_location)
                st.session_state.weather_pref_value = saved
                st.success("Default location saved!")
            except Exception as e:
                st.error(f"Failed: {e}")

    with wcol2:
        if st.button("🌤️ Get Weather Alert", use_container_width=True, type="primary"):
            with st.spinner("Fetching forecast..."):
                try:
                    weather = fetch_weather_alert(
                        location_or_pin=weather_location,
                        country_code=weather_country,
                        days=weather_days,
                    )
                    st.session_state.last_weather_data = weather
                except Exception as e:
                    st.error(f"Failed: {e}")

    with wcol3:
        if st.button("🤖 AI Recommendations", use_container_width=True):
            if st.session_state.get("last_weather_data") is None:
                st.warning("Fetch weather alert first.")
            else:
                with st.spinner("Generating recommendations..."):
                    try:
                        w = st.session_state.last_weather_data
                        loc_name = w.get("resolved_location", {}).get("display_name", weather_location)
                        rec = get_weather_recommendation(w, location_display=loc_name)
                        st.session_state["last_ai_rec"] = rec
                        st.session_state["last_ai_rec_location"] = loc_name
                    except Exception as e:
                        st.error(f"Failed: {e}")

    # Display weather results
    weather = st.session_state.get("last_weather_data")
    if weather:
        risk = str(weather.get("risk_level") or "low").lower()
        summary = weather.get("summary") or ""
        loc_name = weather.get("resolved_location", {}).get("display_name", weather_location)

        risk_colors = {"high": "red", "medium": "orange", "low": "green"}
        icons = {"high": "🔴", "medium": "🟡", "low": "🟢"}
        color = risk_colors.get(risk, "green")
        icon = icons.get(risk, "🟢")

        st.markdown(
            f"<div style='padding:1rem;border-radius:8px;border-left:4px solid {color};"
            f"background-color:{color}10;margin:0.5rem 0'>"
            f"<h4>{icon} Risk Level: <span style='color:{color}'>{risk.upper()}</span></h4>"
            f"<p><b>📍 {loc_name}</b></p>"
            f"<p>{summary}</p>"
            f"</div>",
            unsafe_allow_html=True,
        )

        alerts = weather.get("alerts") or []
        if alerts:
            st.markdown("**⚠️ Alerts**")
            for a in alerts:
                reasons = ", ".join(a.get("reasons") or [])
                al_color = "red" if a.get("level") == "high" else "orange"
                st.markdown(
                    f"<div style='padding:0.5rem;border-radius:4px;border-left:3px solid {al_color};"
                    f"background:{al_color}08;margin:0.25rem 0'>"
                    f"<b>{a.get('date')}</b> — {a.get('level')} risk: {reasons}"
                    f"</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.info("No significant weather alerts for this period.")

        with st.expander("📊 Forecast Details"):
            st.json(weather.get("forecast_days") or [])

    # AI Recommendation display
    if st.session_state.get("last_ai_rec"):
        st.markdown("---")
        st.markdown("### 🤖 AI Livestock Recommendation")
        loc_for_rec = st.session_state.get("last_ai_rec_location", "")
        st.markdown(f"*Based on weather for {loc_for_rec}*")
        st.success(st.session_state["last_ai_rec"])

# ── TAB 3: MY ANIMALS ─────────────────────────────────────────────

with tab_animals:
    st.subheader("🐄 Your Animals")

    with st.spinner("Loading animals..."):
        try:
            animals = list_animals_for_farmer(farmer_id)
        except Exception:
            animals = []

    if animals:
        total = len(animals)
        species_count = {}
        for a in animals:
            s = a.species or "unknown"
            species_count[s] = species_count.get(s, 0) + 1

        summary_cols = st.columns(4)
        with summary_cols[0]:
            st.metric("Total Animals", total)
        for i, (sp, cnt) in enumerate(sorted(species_count.items())):
            if i + 1 < 4:
                with summary_cols[i + 1]:
                    st.metric(sp.capitalize(), cnt)

        st.markdown("---")
        for a in animals:
            age_str = f"{a.age_years:.0f} yr{'s' if a.age_years != 1 else ''}" if a.age_years else "—"
            with st.container():
                cols = st.columns([1, 3, 2, 2])
                sex_icon = "♂️" if a.sex == "male" else "♀️" if a.sex == "female" else ""
                with cols[0]:
                    st.markdown(f"**{a.tag_or_name}**")
                    st.caption(f"`{a.id}`")
                with cols[1]:
                    st.write(f"{a.species.capitalize()} {sex_icon}")
                    if a.breed:
                        st.caption(f"Breed: {a.breed}")
                with cols[2]:
                    st.write(f"Age: {age_str}")
                with cols[3]:
                    if a.feeding_details:
                        st.caption(f"🥘 {a.feeding_details[:40]}{'...' if len(a.feeding_details) > 40 else ''}")
                st.divider()
    else:
        st.info("No animals registered yet for this farmer.")
        st.markdown("Go to the **Chat** tab and say: *\"add a new goat named gauri, female, sirohi, 2 years\"*")

# ── TAB 4: ONBOARDING ─────────────────────────────────────────────

with tab_onboard:
    st.subheader("📋 Farm Onboarding")
    st.caption("Tell me about your farm and I'll fill in the details. You can provide info in any language.")

    onboard_msgs = st.session_state.onboarding_messages

    chat_cont = st.container(height=400)
    with chat_cont:
        for msg in onboard_msgs:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])

    progress = 0
    total = len(FARM_FIELDS)
    filled = sum(1 for f in FARM_FIELDS if st.session_state.onboarding_data.get(f) not in (None, "", 0))
    if total:
        progress = filled / total
    st.progress(progress, text=f"{filled}/{total} fields collected")

    if st.session_state.onboarding_complete:
        st.success("✅ All farm details collected!")
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            if st.button("💾 Save Farm Details", type="primary", use_container_width=True):
                try:
                    saved = save_farm_onboarding(farmer_id, st.session_state.onboarding_data)
                    st.session_state.onboarding_saved_id = saved.id
                    st.success(f"Farm saved! ID: {saved.id}")
                except Exception as e:
                    st.error(f"Save failed: {e}")
        with col_s2:
            if st.button("🔄 Start Over", use_container_width=True):
                st.session_state.onboarding_data = {}
                st.session_state.onboarding_messages = []
                st.session_state.onboarding_complete = False
                st.session_state.onboarding_saved_id = None
                st.rerun()

        with st.expander("📄 Collected Data"):
            st.json(st.session_state.onboarding_data)
    else:
        if not onboard_msgs:
            with st.chat_message("assistant"):
                welcome = "Hello! I'll help you register your farm. What's the name of your farm?"
                st.write(welcome)
                onboard_msgs.append({"role": "assistant", "content": welcome})

        onboard_input = st.chat_input("Tell me about your farm...")
        if onboard_input:
            onboard_msgs.append({"role": "user", "content": onboard_input})
            with chat_cont:
                with st.chat_message("user"):
                    st.write(onboard_input)

            with st.spinner("Processing..."):
                result = extract_farm_onboarding(
                    onboard_input,
                    existing_data=st.session_state.onboarding_data,
                )
                st.session_state.onboarding_data = result["data"]
                st.session_state.onboarding_complete = result["complete"]

                fq = result.get("follow_up_question")
                if fq:
                    onboard_msgs.append({"role": "assistant", "content": fq})
                elif not result["complete"]:
                    onboard_msgs.append({"role": "assistant", "content": "What else can you tell me about your farm?"})
                else:
                    onboard_msgs.append({"role": "assistant", "content": "I have all the details! Click 'Save Farm Details' to save."})
                st.rerun()

    with st.expander("View Existing Farm Records"):
        try:
            existing = list_farms_for_farmer(farmer_id)
            if existing:
                for f in existing:
                    st.write(f"**{f.name or 'Unnamed'}** — {f.city}, {f.state}")
                    st.caption(f"ID: `{f.id}` | {f.sheep_count} sheep, {f.goat_count} goats")
                    st.divider()
            else:
                st.info("No farm records yet.")
        except Exception as e:
            st.error(f"Failed to load farm records: {e}")

# ── TAB 5: SESSION ────────────────────────────────────────────────

with tab_settings:
    st.subheader("⚙️ Session State")

    col_s1, col_s2, col_s3 = st.columns(3)
    with col_s1:
        st.metric("Session", session_id)
    with col_s2:
        st.metric("Farmer ID", farmer_id)
    with col_s3:
        st.metric("Doctor ID", doctor_id or "—")

    st.markdown("---")
    with st.expander("Raw Session State", expanded=False):
        st.json(get_session(session_id))

    with st.expander("Message History", expanded=True):
        for i, msg in enumerate(st.session_state.messages):
            st.markdown(f"**{msg['role'].title()}:** {msg['content']}")
            if msg.get("audio"):
                st.audio(msg["audio"], format="audio/mp3")
            if i < len(st.session_state.messages) - 1:
                st.divider()

    with st.expander("Assistant Voice Output", expanded=False):
        if st.session_state.last_assistant_audio:
            st.audio(st.session_state.last_assistant_audio, format="audio/mp3")
        else:
            tts_enabled = os.getenv("TTS_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
            if tts_enabled and st.session_state.last_tts_error:
                st.warning(
                    "Voice output unavailable. "
                    f"TTS error: {st.session_state.last_tts_error}. "
                    "Check IAM permission polly:SynthesizeSpeech and voice/language settings."
                )
            else:
                st.info("No assistant voice generated yet.")

    with st.expander("System Config", expanded=False):
        config_prefs = {
            "AWS_REGION": os.getenv("AWS_REGION"),
            "BEDROCK_MODEL_ID": os.getenv("BEDROCK_MODEL_ID"),
            "TRANSCRIBE_MODE": os.getenv("TRANSCRIBE_MODE"),
            "LANGUAGE_OPTIONS": os.getenv("AWS_TRANSCRIBE_LANGUAGE_OPTIONS"),
            "MULTILINGUAL": os.getenv("AWS_TRANSCRIBE_MULTILINGUAL"),
            "TTS_ENABLED": os.getenv("TTS_ENABLED"),
            "POLLY_VOICES": f"hi={os.getenv('AWS_POLLY_VOICE_HI')}, en={os.getenv('AWS_POLLY_VOICE_EN')}, kn={os.getenv('AWS_POLLY_VOICE_KN')}, te={os.getenv('AWS_POLLY_VOICE_TE')}",
            "UI_RESPONSE_LANGUAGE": os.getenv("UI_RESPONSE_LANGUAGE", "auto"),
        }
        st.json(config_prefs)
