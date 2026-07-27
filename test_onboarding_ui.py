"""Streamlit test UI for Farmer Onboarding Service with queue-based flow."""

import hashlib
import json
import os

import requests
import streamlit as st

from services.voice_agent.transcribe import transcribe_audio
from services.voice_agent.tts import synthesize_speech

os.environ.setdefault("AWS_REGION", "ap-south-1")
os.environ.setdefault("TTS_ENABLED", "true")
os.environ.setdefault("AWS_POLLY_VOICE_HI", "Aditi")
os.environ.setdefault("AWS_POLLY_VOICE_EN", "Raveena")
os.environ.setdefault("TRANSCRIBE_MODE", "aws")
os.environ.setdefault("VOICE_S3_BUCKET", "farmer-chat-audio-bucket-198799425726")
os.environ.setdefault("AWS_TRANSCRIBE_MULTILINGUAL", "true")
os.environ.setdefault("AWS_TRANSCRIBE_LANGUAGE_OPTIONS", "en-IN,hi-IN,kn-IN,te-IN")

API_URL = os.environ.get("ONBOARDING_API_URL", "http://localhost:8004")

# ── Queues (bins) ──────────────────────────────────────────────

QUEUES = [
    {
        "name": "🧑 Personal Info",
        "fields": [
            ("farmer", "name", "What is your name?"),
            ("farmer", "fatherOrSpouseName", "What is your father's or spouse's name?"),
            ("farmer", "gender", "What is your gender?"),
            ("farmer", "dob", "What is your date of birth?"),
        ],
    },
    {
        "name": "📞 Contact",
        "fields": [
            ("farmer", "phone", "What is your mobile number?"),
            ("farmer", "alternateMobile", "Do you have an alternate mobile number?"),
            ("farmer", "email", "What is your email address?"),
        ],
    },
    {
        "name": "📍 Residence Address",
        "fields": [
            ("farmer", "address_1", "What is your residential address?"),
            ("farmer", "city", "Which city do you live in?"),
            ("farmer", "state", "Which state are you from?"),
            ("farmer", "pincode", "What is your pincode?"),
        ],
    },
    {
        "name": "🆔 Identity Documents",
        "fields": [
            ("farmer", "aadharNo", "What is your Aadhar number?"),
            ("farmer", "hasPanCard", "Do you have a PAN card?"),
            ("farmer", "panNo", "What is your PAN number?"),
        ],
    },
    {
        "name": "👥 Demographics",
        "fields": [
            ("farmer", "education", "What is your highest education?"),
            ("farmer", "occupation", "What is your occupation?"),
            ("farmer", "religion", "What is your religion?"),
            ("farmer", "caste", "What is your caste category?"),
        ],
    },
    {
        "name": "🌾 Farming Background",
        "fields": [
            ("farmer", "farmingExperience", "How many years of farming experience do you have?"),
            ("farmer", "landHolding", "How much land do you hold (in acres)?"),
        ],
    },
    {
        "name": "🏠 Farm Details",
        "fields": [
            ("farm", "name", "What is your farm name?"),
            ("farm", "phone", "What is your farm phone number?"),
            ("farm", "address", "What is your farm address?"),
            ("farm", "city", "Which city is your farm in?"),
            ("farm", "district", "Which district is your farm in?"),
            ("farm", "state", "Which state is your farm in?"),
            ("farm", "pincode", "What is your farm pincode?"),
        ],
    },
    {
        "name": "🐏 Livestock",
        "fields": [
            ("farm", "totalAnimalCapacity", "How many animals can your farm hold?"),
            ("farm", "sheepCount", "How many sheep do you have?"),
            ("farm", "goatCount", "How many goats do you have?"),
        ],
    },
]

ALL_FIELDS_FLAT = []
for q in QUEUES:
    for f in q["fields"]:
        ALL_FIELDS_FLAT.append(f)

_QUESTIONS_HI = {e[1]: f"कृपया अपना {e[1]} बताएं" for e in ALL_FIELDS_FLAT}
_QUESTIONS_HI.update({
    "name": "आपका नाम क्या है?",
    "fatherOrSpouseName": "आपके पिता या पति का नाम क्या है?",
    "gender": "आपका लिंग क्या है?",
    "dob": "आपकी जन्म तिथि क्या है?",
    "phone": "आपका मोबाइल नंबर क्या है?",
    "email": "आपका ईमेल क्या है?",
    "address_1": "आपका पता क्या है?",
    "city": "आप किस शहर में रहते हैं?",
    "state": "आप किस राज्य से हैं?",
    "pincode": "आपका पिनकोड क्या है?",
    "aadharNo": "आपका आधार नंबर क्या है?",
    "education": "आपकी शिक्षा क्या है?",
    "occupation": "आपका व्यवसाय क्या है?",
    "farmingExperience": "आपको कितने वर्षों का खेती का अनुभव है?",
    "landHolding": "आपके पास कितनी ज़मीन है (एकड़ में)?",
})

_QUESTIONS_KN = {e[1]: f"ದಯವಿಟ್ಟು ನಿಮ್ಮ {e[1]} ತಿಳಿಸಿ" for e in ALL_FIELDS_FLAT}
_QUESTIONS_KN.update({
    "name": "ನಿಮ್ಮ ಹೆಸರೇನು?",
    "phone": "ನಿಮ್ಮ ಮೊಬೈಲ್ ಸಂಖ್ಯೆ ಎಷ್ಟು?",
    "city": "ನೀವು ಯಾವ ಊರಿನಲ್ಲಿ ವಾಸಿಸುತ್ತೀರಿ?",
    "state": "ನೀವು ಯಾವ ರಾಜ್ಯದವರು?",
    "aadharNo": "ನಿಮ್ಮ ಆಧಾರ್ ಸಂಖ್ಯೆ ಎಷ್ಟು?",
})

_QUESTIONS_TE = {e[1]: f"దయచేసి మీ {e[1]} తెలపండి" for e in ALL_FIELDS_FLAT}
_QUESTIONS_TE.update({
    "name": "మీ పేరు ఏమిటి?",
    "phone": "మీ ఫోన్ నంబర్ ఏమిటి?",
    "city": "మీరు ఏ నగరంలో నివసిస్తున్నారు?",
    "state": "మీరు ఏ రాష్ట్రం నుండి వచ్చారు?",
    "aadharNo": "మీ ఆధార్ నంబర్ ఏమిటి?",
})

_QUESTION_TEXTS = {"en": {e[1]: e[2] for e in ALL_FIELDS_FLAT}, "hi": _QUESTIONS_HI, "kn": _QUESTIONS_KN, "te": _QUESTIONS_TE}

LANG_MAP = {"hi": "hi", "kn": "kn", "te": "te", "en": "en", "mix": "hi"}

_FARM_FIELDS_SET = {"name", "phone", "email", "alternate_phone", "address", "city", "district", "pincode", "state", "country", "total_animal_capacity", "current_animal_count", "sheep_count", "goat_count", "notes", "image"}

# ── Session checkpoint ─────────────────────────────────────────

_CHECKPOINT_FILE = os.path.join(os.path.dirname(__file__), "data", "onboarding_checkpoint.json")


def _save_checkpoint(state, queue_idx, messages, lang, completed=False):
    import pathlib
    pathlib.Path(_CHECKPOINT_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(_CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "onboard_state": state,
            "current_queue": queue_idx,
            "messages": messages,
            "lang": lang,
            "completed": completed,
        }, f, ensure_ascii=False, indent=2)


def _load_checkpoint():
    if not os.path.exists(_CHECKPOINT_FILE):
        return None
    with open(_CHECKPOINT_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _clear_checkpoint():
    if os.path.exists(_CHECKPOINT_FILE):
        os.remove(_CHECKPOINT_FILE)


st.set_page_config(page_title="Farmer Onboarding", layout="wide")
st.title("🧑‍🌾 Farmer Onboarding")
st.caption("Voice + text onboarding service")

# ── Session state ──────────────────────────────────────────────

if "onboard_state" not in st.session_state:
    st.session_state.onboard_state = {"farmer": {}, "farm": {}}
if "messages" not in st.session_state:
    st.session_state.messages = []
if "started" not in st.session_state:
    st.session_state.started = False
if "completed" not in st.session_state:
    st.session_state.completed = False
if "saved" not in st.session_state:
    st.session_state.saved = False
if "current_queue" not in st.session_state:
    st.session_state.current_queue = 0
if "last_voice_hash" not in st.session_state:
    st.session_state.last_voice_hash = None
if "_just_transitioned" not in st.session_state:
    st.session_state._just_transitioned = False

# ── Helpers ────────────────────────────────────────────────────

def _total_field_count():
    return sum(len(q["fields"]) for q in QUEUES)


def _field_progress(state):
    filled = 0
    for section, field, _ in ALL_FIELDS_FLAT:
        v = state.get(section, {}).get(field)
        if v not in (None, "", 0, "0"):
            filled += 1
    return filled, _total_field_count()


def _next_missing_in_queue(state, queue_idx):
    if queue_idx >= len(QUEUES):
        return None, None, None
    for section, field, q in QUEUES[queue_idx]["fields"]:
        v = state.get(section, {}).get(field)
        if v in (None, "", 0, "0"):
            return section, field, q
    return None, None, None


def _find_next_queue(state, start_idx=0):
    for i in range(start_idx, len(QUEUES)):
        sec, fld, q = _next_missing_in_queue(state, i)
        if sec is not None:
            return i, sec, fld, q
    return None, None, None, None


def _question_for(field, lang):
    return _QUESTION_TEXTS.get(lang, _QUESTION_TEXTS["en"]).get(field) or _QUESTION_TEXTS["en"].get(field, "")


def _call_api(text, existing, lang="en", current_field=None, current_section=None):
    try:
        body = {"text": text, "existing": existing, "language": lang}
        if current_field:
            body["current_field"] = current_field
        if current_section:
            body["current_section"] = current_section
        resp = requests.post(f"{API_URL}/onboarding", json=body, timeout=30)
        return resp.json()
    except Exception as e:
        return {"farmer": {}, "farm": {}, "follow_up_question": f"Error: {e}", "complete": False}


def _process(user_text=None, audio_bytes=None):
    lang = st.session_state.get("lang", "en")
    qi = st.session_state.current_queue

    if audio_bytes:
        with st.spinner("🎤 Transcribing..."):
            user_text = transcribe_audio(audio_bytes)
        if not user_text or not user_text.strip():
            st.warning("Could not transcribe audio. Try again.")
            return
        st.session_state.messages.append({"role": "user", "content": f"🎤 {user_text}"})
    else:
        st.session_state.messages.append({"role": "user", "content": user_text})

    # Determine current field and section being asked
    cs, cf, _ = _next_missing_in_queue(st.session_state.onboard_state, qi)
    if cf is None:
        nqi, cs, cf, _ = _find_next_queue(st.session_state.onboard_state, qi)

    # Call extraction API (pass both field + section for disambiguation)
    with st.spinner("🤖 Processing..."):
        result = _call_api(user_text, st.session_state.onboard_state, lang, current_field=cf, current_section=cs)

    # Merge API results
    for section in ("farmer", "farm"):
        new_vals = result.get(section, {})
        for k, v in new_vals.items():
            if v not in (None, "", 0, "0"):
                st.session_state.onboard_state[section][k] = v

    # UI-side fallback: if current field still empty, assign raw text (with correct section)
    if cf and cs and user_text and user_text.strip():
        cur = st.session_state.onboard_state[cs].get(cf) if cs else None
        if cur in (None, "", 0, "0"):
            st.session_state.onboard_state[cs][cf] = user_text.strip()

    # Check if current queue is complete → advance
    _, _, _ = _next_missing_in_queue(st.session_state.onboard_state, qi)
    nqi, nsec, nfld, nq = _find_next_queue(st.session_state.onboard_state, qi)

    if nqi is None:
        st.session_state.completed = True
        st.session_state.messages.append({"role": "assistant", "content": "✅ All queues complete! Review and save below."})
    elif nqi > qi:
        st.session_state.current_queue = nqi
        st.session_state._just_transitioned = True
        msg = f"✅ **{QUEUES[qi]['name']}** complete! Moving to **{QUEUES[nqi]['name']}**."
        st.session_state.messages.append({"role": "assistant", "content": msg})
        question = _question_for(nfld, lang)
        if question:
            st.session_state.messages.append({"role": "assistant", "content": question})
            tts_lang = LANG_MAP.get(lang, "en")
            audio, err = synthesize_speech(question, target_lang=tts_lang)
            if audio:
                st.session_state._play_audio = audio
    else:
        question = _question_for(nfld, lang)
        st.session_state.messages.append({"role": "assistant", "content": question})
        tts_lang = LANG_MAP.get(lang, "en")
        audio, err = synthesize_speech(question, target_lang=tts_lang)
        if audio:
            st.session_state._play_audio = audio

    st.rerun()


# ── UI ─────────────────────────────────────────────────────────

if not st.session_state.started:
    saved = _load_checkpoint()

    st.markdown("### 👋 Welcome! Click Start to begin onboarding.")
    col1, col2 = st.columns([1, 3])
    with col1:
        st.selectbox("Language", ["en", "hi", "kn", "te"], key="lang")
    with col2:
        st.write("")
        st.write("")
        bcol1, bcol2 = st.columns(2)
        with bcol1:
            if st.button("🚀 Start Fresh", type="primary", use_container_width=True):
                _clear_checkpoint()
                st.session_state.started = True
                lang = st.session_state.get("lang", "en")
                q = _question_for(QUEUES[0]["fields"][0][1], lang) or "Hello! Let's get started. What is your name?"
                st.session_state.messages.append({"role": "assistant", "content": q})
                st.rerun()
        with bcol2:
            if saved:
                cp_lang = saved.get("lang", "en")
                if st.button(f"↩️ Resume Last Session ({cp_lang.upper()})", use_container_width=True, type="secondary"):
                    st.session_state.started = True
                    st.session_state.lang = cp_lang
                    st.session_state.onboard_state = saved.get("onboard_state", {"farmer": {}, "farm": {}})
                    st.session_state.current_queue = saved.get("current_queue", 0)
                    st.session_state.messages = saved.get("messages", [])
                    st.session_state.completed = saved.get("completed", False)
                    _clear_checkpoint()
                    st.rerun()
else:
    qi = st.session_state.current_queue
    current_queue_name = QUEUES[qi]["name"] if qi < len(QUEUES) else "Done"

    with st.sidebar:
        st.subheader("📊 Progress")
        filled, total = _field_progress(st.session_state.onboard_state)
        st.progress(filled / total if total else 0, text=f"{filled}/{total}")

        st.subheader("🗂️ Queues")
        for i, q in enumerate(QUEUES):
            q_filled = 0
            q_total = len(q["fields"])
            for sec, fld, _ in q["fields"]:
                v = st.session_state.onboard_state.get(sec, {}).get(fld)
                if v not in (None, "", 0, "0"):
                    q_filled += 1
            icon = "✅" if q_filled == q_total else ("⏳" if i == qi else "⭕")
            st.caption(f"{icon} {q['name']} ({q_filled}/{q_total})")

        st.selectbox("Language", ["en", "hi", "kn", "te"], key="lang")

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("💾 Checkpoint", use_container_width=True):
                _save_checkpoint(
                    st.session_state.onboard_state,
                    st.session_state.current_queue,
                    [m for m in st.session_state.messages if "Moving to" not in m.get("content", "")],
                    st.session_state.get("lang", "en"),
                    completed=st.session_state.completed,
                )
                st.toast("✅ Session saved!")
        with col_b:
            if st.button("🗑️ Clear & Restart", use_container_width=True):
                _clear_checkpoint()
                for k in ("onboard_state", "messages", "started", "completed", "saved", "current_queue", "farmer_id", "farm_id", "_just_transitioned"):
                    st.session_state.pop(k, None)
                st.rerun()

        if st.session_state.completed:
            st.success("✅ Complete!")
            with st.expander("📄 Final JSON"):
                st.json(st.session_state.onboard_state)

            if not st.session_state.get("saved"):
                if st.button("💾 Save to Database", type="primary"):
                    with st.spinner("Saving..."):
                        try:
                            resp = requests.post(
                                f"{API_URL}/onboarding/save",
                                json={
                                    "farmer": st.session_state.onboard_state["farmer"],
                                    "farm": st.session_state.onboard_state["farm"],
                                },
                                timeout=15,
                            )
                            if resp.status_code == 200:
                                data = resp.json()
                                st.session_state.saved = True
                                st.session_state.farmer_id = data["farmer_id"]
                                st.session_state.farm_id = data["farm_id"]
                            else:
                                st.error(f"Save failed: {resp.text}")
                        except Exception as e:
                            st.error(f"Save error: {e}")
                    st.rerun()
            else:
                st.info(f"✅ Saved!\nFarmer ID: `{st.session_state.farmer_id}`\nFarm ID: `{st.session_state.farm_id}`")
                if st.button("🔄 Start Over"):
                    _clear_checkpoint()
                    for k in ("onboard_state", "messages", "started", "completed", "saved", "current_queue", "farmer_id", "farm_id", "_just_transitioned"):
                        st.session_state.pop(k, None)
                    st.rerun()

    # Chat area
    chat = st.container(height=400)
    with chat:
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])

    # Play audio if queued
    if st.session_state.get("_play_audio"):
        st.audio(st.session_state._play_audio, format="audio/mp3", autoplay=True)
        st.session_state._play_audio = None

    # Input
    if not st.session_state.completed:
        inp = st.chat_input("Type your answer here...")
        if inp:
            st.session_state._just_transitioned = False
            _process(user_text=inp)

        audio = st.audio_input("🎤 Or record your answer")
        if audio is not None:
            b = audio.getvalue()
            h = hashlib.sha256(b).hexdigest()
            if st.session_state.last_voice_hash != h:
                st.session_state.last_voice_hash = h
                st.session_state._just_transitioned = False
                _process(audio_bytes=b)
    else:
        st.success("✅ Onboarding complete! Use the sidebar to save to database.")
