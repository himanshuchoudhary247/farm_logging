"""Farmer Onboarding Streamlit App."""
import os
import json
import tempfile
from typing import Any
import streamlit as st
import requests as http
import speech_recognition as sr
import warnings
warnings.filterwarnings("ignore", message="Unverified HTTPS request")

API_BASE = os.environ.get("ONBOARDING_API_URL", "https://localhost:8004")

def api_call(endpoint: str, payload: dict) -> dict | None:
    try:
        r = http.post(f"{API_BASE}{endpoint}", json=payload, timeout=60, verify=False)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def transcribe_audio(audio_bytes, language="en-US"):
    recognizer = sr.Recognizer()
    lang_map = {
        "en-US": "en-US", "hi-IN": "hi-IN", "kn-IN": "kn-IN",
        "te-IN": "te-IN", "ta-IN": "ta-IN", "mr-IN": "mr-IN", "pa-IN": "pa-IN"
    }
    sr_lang = lang_map.get(language, "en-US")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        with sr.AudioFile(tmp_path) as source:
            audio = recognizer.record(source)
        text = recognizer.recognize_google(audio, language=sr_lang)
        return text
    except sr.UnknownValueError:
        return None
    except sr.RequestError as e:
        return f"ERROR: Speech service unavailable: {e}"
    finally:
        os.unlink(tmp_path)

def process_text(text: str):
    if not text.strip():
        return
    st.session_state.chat_history.append({"role": "user", "content": text})
    with st.spinner("Processing with AI..."):
        result = api_call("/onboarding", {
            "text": text,
            "existing": {
                "farmer": st.session_state.farmer_data,
                "farm": st.session_state.farm_data
            },
            "current_field": st.session_state.get("current_field"),
            "conversation_history": st.session_state.chat_history[-6:],
        })
    if result and not result.get("error"):
        st.session_state.farmer_data = result.get("farmer", {})
        st.session_state.farm_data = result.get("farm", {})
        st.session_state.missing_fields = result.get("missing_fields", [])
        st.session_state.complete = result.get("complete", False)
        st.session_state.current_field = result.get("current_field")
        response = result.get("follow_up_question", "All details collected!")
        st.session_state.chat_history.append({"role": "assistant", "content": response})
    else:
        error_msg = result.get("error", "Unknown error") if result else "No response"
        st.error(f"Error: {error_msg}")

st.set_page_config(page_title="Farmer Onboarding", page_icon="🌾", layout="centered")
st.title("🌾 Farmer Onboarding Form")

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "farmer_data" not in st.session_state:
    st.session_state.farmer_data = {}
if "farm_data" not in st.session_state:
    st.session_state.farm_data = {}
if "missing_fields" not in st.session_state:
    st.session_state.missing_fields = []
if "complete" not in st.session_state:
    st.session_state.complete = False
if "last_audio_id" not in st.session_state:
    st.session_state.last_audio_id = None
if "current_field" not in st.session_state:
    st.session_state.current_field = None

tab1, tab2 = st.tabs(["💬 Chat Mode", "📝 Manual Form"])

with tab1:
    st.subheader("Chat-based Registration")
    st.caption("Type naturally or use voice — the system will extract your details.")

    st.markdown("##### 🎤 Voice Input")

    lang = st.selectbox("Language", ["en-US", "hi-IN", "kn-IN", "te-IN", "ta-IN", "mr-IN", "pa-IN"],
                        format_func=lambda x: {"en-US":"English","hi-IN":"Hindi","kn-IN":"Kannada",
                                               "te-IN":"Telugu","ta-IN":"Tamil","mr-IN":"Marathi",
                                               "pa-IN":"Punjabi"}[x], key="voice_lang")

    audio_data = st.audio_input("🎙️ Record your voice", key="audio_recorder")

    if audio_data is not None:
        audio_id = id(audio_data)
        if audio_id != st.session_state.last_audio_id:
            st.session_state.last_audio_id = audio_id
            st.audio(audio_data, format="audio/wav")
            with st.spinner("Transcribing your speech..."):
                text = transcribe_audio(audio_data.read(), lang)
            if text and not str(text).startswith("ERROR:"):
                st.success(f"✓ Transcribed: **{text}**")
                process_text(text)
            elif str(text).startswith("ERROR:"):
                st.error(str(text))
            else:
                st.warning("Could not understand the audio. Please try again or type below.")

    st.divider()

    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    if prompt := st.chat_input("Tell me about yourself and your farm..."):
        process_text(prompt)
        st.rerun()

with tab2:
    st.subheader("Manual Form Entry")

    with st.form("manual_form"):
        st.markdown("### Farmer Details")
        c1, c2 = st.columns(2)
        with c1:
            name = st.text_input("Name", st.session_state.farmer_data.get("name", ""))
            phone = st.text_input("Phone", st.session_state.farmer_data.get("phone", ""))
            city = st.text_input("City", st.session_state.farmer_data.get("city", ""))
            state = st.text_input("State", st.session_state.farmer_data.get("state", ""))
            pincode = st.text_input("Pincode", st.session_state.farmer_data.get("pincode", ""))
        with c2:
            gender_opts = ["", "male", "female", "other"]
            gender_idx = 0
            if st.session_state.farmer_data.get("gender") in gender_opts:
                gender_idx = gender_opts.index(st.session_state.farmer_data["gender"])
            gender = st.selectbox("Gender", gender_opts, index=gender_idx)
            father_name = st.text_input("Father/Spouse Name", st.session_state.farmer_data.get("fatherOrSpouseName", ""))
            aadhar = st.text_input("Aadhar No", st.session_state.farmer_data.get("aadharNo", ""))
            education = st.text_input("Education", st.session_state.farmer_data.get("education", ""))
            occupation = st.text_input("Occupation", st.session_state.farmer_data.get("occupation", ""))

        st.markdown("### Farm Details")
        c3, c4 = st.columns(2)
        with c3:
            farm_name = st.text_input("Farm Name", st.session_state.farm_data.get("farmName", ""))
            farm_city = st.text_input("Farm City", st.session_state.farm_data.get("farmCity", ""))
            farm_state = st.text_input("Farm State", st.session_state.farm_data.get("farmState", ""))
        with c4:
            sheep = st.number_input("Sheep Count", value=int(st.session_state.farm_data.get("sheepCount", 0)))
            goat = st.number_input("Goat Count", value=int(st.session_state.farm_data.get("goatCount", 0)))
            capacity = st.number_input("Total Capacity", value=int(st.session_state.farm_data.get("totalAnimalCapacity", 0)))

        submitted = st.form_submit_button("Save Details")

    if submitted:
        st.session_state.farmer_data = {
            "name": name, "phone": phone, "city": city, "state": state, "pincode": pincode,
            "gender": gender, "fatherOrSpouseName": father_name, "aadharNo": aadhar,
            "education": education, "occupation": occupation
        }
        st.session_state.farm_data = {
            "farmName": farm_name, "farmCity": farm_city, "farmState": farm_state,
            "sheepCount": sheep, "goatCount": goat, "totalAnimalCapacity": capacity
        }
        st.success("Details saved!")

st.markdown("---")
st.subheader("Collected Data")

col1, col2 = st.columns(2)
with col1:
    st.markdown("**Farmer:**")
    if st.session_state.farmer_data:
        for k, v in st.session_state.farmer_data.items():
            if v:
                st.write(f"- {k}: {v}")
    else:
        st.caption("No data yet")

with col2:
    st.markdown("**Farm:**")
    if st.session_state.farm_data:
        for k, v in st.session_state.farm_data.items():
            if v:
                st.write(f"- {k}: {v}")
    else:
        st.caption("No data yet")

if st.session_state.missing_fields:
    st.warning(f"Missing: {', '.join(st.session_state.missing_fields[:5])}")

st.caption("Powered by AWS Bedrock Mistral + FastAPI + Google Speech")
