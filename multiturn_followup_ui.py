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
    update_animal_for_farmer,
)
from services.voice_agent.orchestrator import process_text_input, process_voice
from services.voice_agent.session_store import clear_session, get_session
from services.voice_agent.tts import synthesize_speech
from services.llm_service.bedrock_adapter import get_weather_recommendation


st.set_page_config(page_title="Livestock Multi-turn Assistant", layout="centered")

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

st.title("Livestock Assistant (Multi-turn)")
st.caption(
    f"mode={os.getenv('TRANSCRIBE_MODE')} stt=amazon-transcribe multi={os.getenv('AWS_TRANSCRIBE_MULTILINGUAL')} lang_opts={os.getenv('AWS_TRANSCRIBE_LANGUAGE_OPTIONS')} tts=aws-polly hi_voice={os.getenv('AWS_POLLY_VOICE_HI')} en_voice={os.getenv('AWS_POLLY_VOICE_EN')} fallback_local={os.getenv('TRANSCRIBE_FALLBACK_TO_LOCAL')} region={os.getenv('AWS_REGION')} model={os.getenv('BEDROCK_MODEL_ID')}"
)

with st.sidebar:
    st.subheader("Session")
    session_id = st.text_input("Session ID", value="farmer-demo-1")
    farmer_id = st.text_input("Farmer ID", value="f-001")
    doctor_id = st.text_input("Doctor ID (optional)", value="")
    if st.button("Reset Conversation"):
        clear_session(session_id)
        st.session_state.messages = []
        st.session_state.last_result = None
        st.session_state.last_saved_signature = None
        st.success("Session reset")

    st.subheader("4 Multi-turn Examples")
    st.markdown("**1) New animal registration (full fields)**")
    st.code("I want to add details about my animal")
    st.code("new")
    st.code("name is gauri, goat female, breed sirohi, 2 years, feeding details green fodder morning and evening")

    st.markdown("**2) Existing animal update by ID (fetch + update)**")
    st.code("existing animal id a-f-001-99")
    st.code("update breed to jamunapari and feeding details concentrate 1kg daily")

    st.markdown("**3) Health log**")
    st.code("my goat is not eating since yesterday")

    st.markdown("**4) Appointment with follow-up**")
    st.code("book a vet appointment")
    st.code("tomorrow at 5 pm")


if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_result" not in st.session_state:
    st.session_state.last_result = None
if "last_voice_hash" not in st.session_state:
    st.session_state.last_voice_hash = None
if "last_saved_signature" not in st.session_state:
    st.session_state.last_saved_signature = None
if "last_assistant_audio" not in st.session_state:
    st.session_state.last_assistant_audio = None
if "last_tts_error" not in st.session_state:
    st.session_state.last_tts_error = None
if "weather_pref_farmer_id" not in st.session_state:
    st.session_state.weather_pref_farmer_id = None
if "weather_pref_value" not in st.session_state:
    st.session_state.weather_pref_value = ""


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
        "mera",
        "meri",
        "mujhe",
        "hai",
        "nahi",
        "nahin",
        "kya",
        "ka",
        "ki",
        "ke",
        "kr",
        "kar",
        "kal",
        "aaj",
        "bhai",
        "please",
        "doctor",
        "dawai",
        "bukhar",
        "khana",
    }
    english_markers = {
        "appointment",
        "update",
        "details",
        "animal",
        "issue",
        "severity",
        "medicine",
        "time",
        "date",
    }

    words = {w.strip(".,!?") for w in t.split() if w.strip(".,!?")}
    has_hi_marker = any(w in words for w in hindi_markers)
    has_en_marker = any(w in words for w in english_markers)
    return has_hi_marker and has_en_marker


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


def _translate_followup_to_hindi(q: str) -> str:
    out = str(q or "").strip()
    replacements = {
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
    }
    for src, dst in replacements.items():
        out = out.replace(src, dst)
    return out


def _translate_followup_to_hinglish(q: str) -> str:
    out = str(q or "").strip()
    replacements = {
        "Please provide:": "Please batayein:",
        "whether this is a new animal registration or an existing animal update": "yeh new animal registration hai ya existing animal update",
        "animal ID or animal name/tag": "animal ID ya animal name/tag",
        "the details to update": "update karne wali details",
        "species": "species",
        "sex (male/female)": "sex (male/female)",
        "breed": "breed",
        "age in years": "age (years me)",
        "feeding details": "feeding details",
        "issue/symptoms": "issue/symptoms",
        "duration": "duration",
        "severity (mild/moderate/severe)": "severity (mild/moderate/severe)",
        "current medication (or 'none')": "current medication (ya 'none')",
        "appointment date": "appointment date",
        "appointment time": "appointment time",
    }
    for src, dst in replacements.items():
        out = out.replace(src, dst)
    return out


def _translate_followup_to_kannada(q: str) -> str:
    out = str(q or "").strip()
    replacements = {
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
    }
    for src, dst in replacements.items():
        out = out.replace(src, dst)
    return out


def _translate_followup_to_telugu(q: str) -> str:
    out = str(q or "").strip()
    replacements = {
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
    }
    for src, dst in replacements.items():
        out = out.replace(src, dst)
    return out


def _response_language(text: str) -> str:
    forced = os.getenv("UI_RESPONSE_LANGUAGE", "auto").strip().lower()
    if forced in {"hi", "hindi"}:
        return "hi"
    if forced in {"kn", "kannada"}:
        return "kn"
    if forced in {"te", "telugu"}:
        return "te"
    if forced in {"mix", "hinglish", "code-mix", "code_mix"}:
        return "mix"
    if forced in {"en", "english"}:
        return "en"

    # Auto: derive from user's transcribed/input text.
    if _is_hindi_text(text):
        if _is_script_code_mix(text, "hi"):
            return "mix-hi"
        return "hi"
    if _is_kannada_text(text):
        if _is_script_code_mix(text, "kn"):
            return "mix-kn"
        return "kn"
    if _is_telugu_text(text):
        if _is_script_code_mix(text, "te"):
            return "mix-te"
        return "te"
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
            notes="Saved from multi-turn assistant",
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
            notes="Saved from multi-turn assistant",
        )
        return {"kind": "appointment_preconsult_created", "row": payload}

    raise ValueError(f"Save not supported for intent: {intent}")


def render_assistant_state(result):
    if not result:
        return

    intent = result.get("intent")
    followups = result.get("follow_up_questions", [])
    complete = result.get("complete", False)

    st.markdown(f"**Intent:** `{intent}`")
    st.markdown(f"**Target tables:** `{result.get('target_tables', [])}`")
    st.markdown(f"**Complete:** `{complete}`")

    if followups:
        st.markdown("**Follow-up questions**")
        for q in followups:
            st.write(f"- {q}")

    if complete and intent:
        st.success("All required details collected. Final JSON ready.")
        st.json(result)

        save_signature = f"{session_id}:{intent}:{result.get('meta', {}).get('raw_text', '')}:{hash(str(result.get('entities', {})))}"
        can_save = intent in {"CREATE_ANIMAL", "UPDATE_ANIMAL", "LOG_HEALTH", "CREATE_APPOINTMENT"}
        if can_save:
            button_label = "Save Record"
            if intent == "CREATE_APPOINTMENT":
                button_label = "Save Pre-consult + Appointment"
            elif intent == "CREATE_ANIMAL":
                button_label = "Create Animal"
            elif intent == "UPDATE_ANIMAL":
                button_label = "Update Animal"
            elif intent == "LOG_HEALTH":
                button_label = "Save Health Log"

            if st.session_state.last_saved_signature == save_signature:
                st.info("This result is already saved.")
            elif st.button(button_label, type="primary"):
                try:
                    saved = _save_from_result(farmer_id, doctor_id, result)
                    st.session_state.last_saved_signature = save_signature
                    st.success(f"Saved successfully: {saved.get('kind')}")
                    st.json(saved.get("row"))
                except Exception as e:
                    st.error(f"Save failed: {e}")


def run_turn(user_text=None, audio_bytes=None):
    if user_text is not None:
        result = process_text_input(user_text, session_id=session_id)
        user_view_text = user_text
    else:
        result = process_voice(audio_bytes, session_id=session_id)
        user_view_text = result.get("meta", {}).get("raw_text", "<voice input>")

    st.session_state.messages.append({"role": "user", "content": user_view_text})

    followups = result.get("follow_up_questions", [])
    lang = _response_language(user_view_text)

    if result.get("intent") == "WEATHER_ALERT" and not followups and result.get("complete"):
        entities = result.get("entities") or {}
        location_query = str(entities.get("weather_location") or "").strip()
        if not location_query:
            location_query = get_farmer_weather_location(farmer_id)

        if location_query:
            days = int(entities.get("forecast_days") or 3)
            country = str(entities.get("country_code") or "in")
            weather = fetch_weather_alert(location_or_pin=location_query, country_code=country, days=days)
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
        formatted_followups = []
        for q in followups:
            q_text = str(q).strip()
            if q_text.lower().startswith("please provide:"):
                normalized = q_text
            else:
                normalized = f"Please provide: {q_text}"
            if lang == "hi":
                normalized = _translate_followup_to_hindi(normalized)
            elif lang in {"mix", "mix-hi"}:
                normalized = _translate_followup_to_hinglish(normalized)
            elif lang in {"kn", "mix-kn"}:
                normalized = _translate_followup_to_kannada(normalized)
            elif lang in {"te", "mix-te"}:
                normalized = _translate_followup_to_telugu(normalized)
            formatted_followups.append(normalized)
        assistant_text = " | ".join(formatted_followups)
    elif result.get("complete") and result.get("intent"):
        if result.get("intent") == "WEATHER_ALERT" and result.get("weather_alert"):
            weather = result.get("weather_alert") or {}
            assistant_text = str(weather.get("summary") or "Weather alert prepared.")
        else:
            assistant_text = (
            "बहुत बढ़िया, मुझे सारी जानकारी मिल गई है। अंतिम JSON नीचे तैयार है।"
            if lang == "hi"
            else "ಚೆನ್ನಾಗಿದೆ, ನನಗೆ ಎಲ್ಲಾ ಮಾಹಿತಿ ಸಿಕ್ಕಿದೆ. ಅಂತಿಮ JSON ಕೆಳಗೆ ಸಿದ್ಧವಾಗಿದೆ."
            if lang in {"kn", "mix-kn"}
            else "చాలా బాగుంది, నాకు మొత్తం సమాచారం వచ్చింది. చివరి JSON కింద సిద్ధంగా ఉంది."
            if lang in {"te", "mix-te"}
            else "Badiya, mujhe sari jankari mil gayi hai. Final JSON neeche ready hai."
            if lang in {"mix", "mix-hi"}
            else "Great, I have everything I need. Final JSON is ready below."
            )
    else:
        assistant_text = (
            "ठीक है, आपकी जानकारी दर्ज कर ली गई है।"
            if lang == "hi"
            else "ಸರಿ, ನಿಮ್ಮ ಇನ್‌ಪುಟ್ ದಾಖಲಿಸಲಾಗಿದೆ."
            if lang in {"kn", "mix-kn"}
            else "సరే, మీ ఇన్‌పుట్‌ను నమోదు చేశాను."
            if lang in {"te", "mix-te"}
            else "Thik hai, maine aapka input capture kar liya."
            if lang in {"mix", "mix-hi"}
            else "Got it. I captured your input."
        )

    if lang in {"hi", "mix", "mix-hi"}:
        tts_lang = "hi"
    elif lang in {"kn", "mix-kn"}:
        tts_lang = "kn"
    elif lang in {"te", "mix-te"}:
        tts_lang = "te"
    else:
        tts_lang = "en"
    assistant_audio, tts_error = synthesize_speech(assistant_text, target_lang=tts_lang)
    st.session_state.last_assistant_audio = assistant_audio
    st.session_state.last_tts_error = tts_error
    msg = {"role": "assistant", "content": assistant_text}
    if assistant_audio:
        msg["audio"] = assistant_audio
    st.session_state.messages.append(msg)
    st.session_state.last_result = result


# Conversation view
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        if msg.get("role") == "assistant" and msg.get("audio"):
            st.audio(msg["audio"], format="audio/mp3")


# Text turn
text_query = st.chat_input("Type your message (or answer follow-up)")
if text_query:
    run_turn(user_text=text_query)
    st.rerun()


# Voice turn (including follow-up answers)
pending = []
if st.session_state.last_result:
    pending = st.session_state.last_result.get("follow_up_questions", []) or []

voice_label = "Record voice for next turn"
if pending:
    voice_label = "Record voice answer for follow-up"

st.subheader("Voice Turn")
if pending:
    st.caption("Follow-up pending: answer it by voice or text.")

audio = st.audio_input(voice_label)
if audio is not None:
    audio_bytes = audio.getvalue()
    st.audio(audio)
    current_hash = hashlib.sha256(audio_bytes).hexdigest()
    if st.session_state.last_voice_hash != current_hash:
        st.session_state.last_voice_hash = current_hash
        with st.spinner("Processing voice turn..."):
            run_turn(audio_bytes=audio_bytes)
        st.rerun()


st.subheader("Current Structured State")
st.json(get_session(session_id))

st.subheader("Last Pipeline Output")
if st.session_state.last_result:
    render_assistant_state(st.session_state.last_result)
else:
    st.info("No turns yet. Start with text or voice.")

st.subheader("Assistant Voice Output")
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


st.subheader("Weather Alert")
if st.session_state.weather_pref_farmer_id != farmer_id:
    st.session_state.weather_pref_farmer_id = farmer_id
    try:
        st.session_state.weather_pref_value = get_farmer_weather_location(farmer_id) or ""
    except Exception:
        st.session_state.weather_pref_value = ""

weather_location = st.text_input(
    "Enter pin code or location",
    value=st.session_state.weather_pref_value or "411001",
    key="weather_location_input",
)
weather_country = st.text_input("Country code", value="in")
weather_days = st.slider("Forecast horizon (days)", min_value=1, max_value=7, value=3)

col_w1, col_w2, col_w3 = st.columns([1, 1, 1])
if col_w1.button("Save as Default Location"):
    try:
        saved = set_farmer_weather_location(farmer_id, weather_location)
        st.session_state.weather_pref_value = saved
        st.success("Default weather location saved")
    except Exception as e:
        st.error(f"Failed to save default location: {e}")

if col_w2.button("Get Weather Alert"):
    with st.spinner("Fetching weather forecast and risk alerts..."):
        try:
            weather = fetch_weather_alert(
                location_or_pin=weather_location,
                country_code=weather_country,
                days=weather_days,
            )
            risk = str(weather.get("risk_level") or "low").lower()
            summary = weather.get("summary") or ""
            if risk == "high":
                st.error(summary)
            elif risk == "medium":
                st.warning(summary)
            else:
                st.success(summary)

            st.write(f"Location: {weather.get('resolved_location', {}).get('display_name', weather_location)}")

            alerts = weather.get("alerts") or []
            if alerts:
                st.markdown("**Alerts**")
                for a in alerts:
                    reasons = ", ".join(a.get("reasons") or [])
                    st.write(f"- {a.get('date')}: {a.get('level')} risk - {reasons}")
            else:
                st.info("No major weather alert for selected horizon.")

            st.markdown("**Forecast Snapshot**")
            st.json(weather.get("forecast_days") or [])

            st.session_state.last_weather_data = weather
        except Exception as e:
            st.error(f"Failed to fetch weather alert: {e}")

if col_w3.button("Get AI Recommendations"):
    if st.session_state.get("last_weather_data") is None:
        st.warning("Please fetch weather alert first.")
    else:
        with st.spinner("Generating AI recommendations based on weather forecast..."):
            try:
                w = st.session_state.last_weather_data
                loc_name = w.get("resolved_location", {}).get("display_name", weather_location)
                rec = get_weather_recommendation(w, location_display=loc_name)
                st.markdown("**AI Recommendation for Your Livestock**")
                st.success(rec)
            except Exception as e:
                st.error(f"Failed to generate recommendation: {e}")
