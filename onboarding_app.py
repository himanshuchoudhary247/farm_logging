"""Farmer Onboarding Streamlit App."""
import os
import json
import time
import hashlib
import subprocess
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

def api_call_raw(endpoint: str, params: dict) -> bytes | None:
    try:
        r = http.get(f"{API_BASE}{endpoint}", params=params, timeout=30, verify=False)
        r.raise_for_status()
        return r.content
    except Exception:
        return None

def transcribe_audio(audio_bytes, language="en-US"):
    recognizer = sr.Recognizer()
    lang_map = {
        "en-US": "en-US", "hi-IN": "hi-IN", "kn-IN": "kn-IN",
        "te-IN": "te-IN", "ta-IN": "ta-IN", "mr-IN": "mr-IN", "pa-IN": "pa-IN"
    }
    sr_lang = lang_map.get(language, "en-US")

    wav_path = None
    with tempfile.NamedTemporaryFile(suffix=".rec", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        if audio_bytes[:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE":
            wav_path = tmp_path
        else:
            wav_path = tmp_path + ".wav"
            subprocess.run(["ffmpeg", "-y", "-i", tmp_path, "-ar", "16000", "-ac", "1", wav_path],
                           capture_output=True, timeout=30)
            if not os.path.exists(wav_path) or os.path.getsize(wav_path) < 100:
                return None
        with sr.AudioFile(wav_path) as source:
            audio = recognizer.record(source)
        text = recognizer.recognize_google(audio, language=sr_lang)
        return text
    except sr.UnknownValueError:
        return None
    except sr.RequestError as e:
        return f"ERROR: Speech service unavailable: {e}"
    except Exception as e:
        return f"ERROR: {e}"
    finally:
        os.unlink(tmp_path)
        if wav_path and wav_path != tmp_path and os.path.exists(wav_path):
            os.unlink(wav_path)

def process_text(text: str, language: str = "en-US"):
    if not text.strip():
        return
    st.session_state.chat_history.append({"role": "user", "content": text})
    t0 = time.time()
    with st.spinner("Processing with AI..."):
        result = api_call("/onboarding", {
            "text": text,
            "existing": {
                "farmer": st.session_state.farmer_data,
                "farm": st.session_state.farm_data
            },
            "current_field": st.session_state.get("current_field"),
            "conversation_history": st.session_state.chat_history[-6:],
            "language": language,
        })
    api_elapsed = (time.time() - t0) * 1000

    if result and not result.get("error"):
        prev_field = st.session_state.get("current_field")
        st.session_state.farmer_data = result.get("farmer", {})
        st.session_state.farm_data = result.get("farm", {})
        st.session_state.missing_fields = result.get("missing_fields", [])
        st.session_state.complete = result.get("complete", False)
        new_field = result.get("current_field")
        st.session_state.current_field = new_field
        response = result.get("follow_up_question", "All details collected!")
        st.session_state.chat_history.append({"role": "assistant", "content": response})

        timing = result.get("timing", {})
        st.session_state.last_timing = {
            "api_total_ms": round(api_elapsed, 1),
            "model_ms": timing.get("model_ms", 0),
            "pre_model_ms": timing.get("pre_model_ms", 0),
            "post_model_ms": timing.get("post_model_ms", 0),
            "json_parse_ms": timing.get("json_parse_ms", 0),
        }

        if prev_field and new_field != prev_field:
            st.session_state.awaiting_feedback = True
            st.session_state.feedback_field = prev_field
        else:
            st.session_state.awaiting_feedback = False
            st.session_state.feedback_field = None
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
if "awaiting_feedback" not in st.session_state:
    st.session_state.awaiting_feedback = False
if "feedback_field" not in st.session_state:
    st.session_state.feedback_field = None
if "last_timing" not in st.session_state:
    st.session_state.last_timing = None

tab1, tab2 = st.tabs(["💬 Chat Mode", "📝 Manual Form"])

with tab1:
    st.subheader("Chat-based Registration")
    st.caption("Type naturally or use voice — the system will extract your details.")

    lang = st.selectbox("Language", ["en-US", "hi-IN", "kn-IN", "te-IN", "ta-IN", "mr-IN", "pa-IN"],
                        format_func=lambda x: {"en-US":"English","hi-IN":"हिन्दी","kn-IN":"ಕನ್ನಡ",
                                               "te-IN":"తెలుగు","ta-IN":"தமிழ்","mr-IN":"मराठी",
                                               "pa-IN":"ਪੰਜਾਬੀ"}[x], key="voice_lang")

    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    if st.session_state.get("awaiting_feedback") and not st.session_state.get("complete"):
        fb_field = st.session_state.get("feedback_field")
        st.markdown(f"**Was the detected value for `{fb_field}` correct?**")
        fb_col1, fb_col2 = st.columns([1, 1])
        with fb_col1:
            if st.button("👍 Thumbs Up", key="thumbs_up", use_container_width=True):
                st.session_state.awaiting_feedback = False
                st.session_state.feedback_field = None
                st.rerun()
        with fb_col2:
            if st.button("👎 Thumbs Down", key="thumbs_down", use_container_width=True):
                lang_code = lang.split("-")[0] if lang else "en"
                lang_questions = {
                    "en": {"name": "What is your name?", "phone": "What is your phone number?",
                           "city": "Which city do you live in?", "state": "Which state are you from?",
                           "pincode": "What is your pincode?", "gender": "What is your gender?",
                           "aadharNo": "What is your Aadhar number?", "fatherOrSpouseName": "What is your father's or spouse's name?",
                           "education": "What is your education level?", "occupation": "What is your occupation?",
                           "farmName": "What is your farm name?", "sheepCount": "How many sheep do you have?",
                           "goatCount": "How many goats do you have?", "totalAnimalCapacity": "What is your total animal capacity?",
                           "farmCity": "In which city is your farm?", "farmState": "Which state is your farm in?"},
                }
                questions = lang_questions.get(lang_code, lang_questions["en"])
                reask_q = questions.get(fb_field, f"Please re-enter: {fb_field}")

                if fb_field in st.session_state.farmer_data:
                    st.session_state.farmer_data[fb_field] = ""
                elif fb_field in st.session_state.farm_data:
                    st.session_state.farm_data[fb_field] = ""

                if fb_field in st.session_state.missing_fields:
                    pass
                else:
                    st.session_state.missing_fields = [fb_field] + st.session_state.missing_fields

                st.session_state.current_field = fb_field
                st.session_state.chat_history.append({"role": "assistant", "content": reask_q})
                st.session_state.awaiting_feedback = False
                st.session_state.feedback_field = None
                st.rerun()

    if st.session_state.get("last_timing"):
        t = st.session_state.last_timing
        with st.expander("⏱️ Last Request Latency"):
            st.write(f"**API total:** {t['api_total_ms']:.0f}ms")
            st.write(f"**Model inference:** {t['model_ms']:.0f}ms")
            st.write(f"**Pre-model (prompt build + network):** {t['pre_model_ms']:.0f}ms")
            st.write(f"**Post-model (parse + merge + validate):** {t['post_model_ms']:.0f}ms")
            if t.get("json_parse_ms"):
                st.write(f"**JSON parse:** {t['json_parse_ms']:.1f}ms")
            network_est = t['api_total_ms'] - t['model_ms'] - t['pre_model_ms'] - t['post_model_ms']
            st.write(f"**Network overhead (est):** {network_est:.0f}ms")

    input_col, voice_col = st.columns([5, 1])
    with input_col:
        text_input = st.text_input("Message", placeholder="Tell me about yourself and your farm...",
                                   label_visibility="collapsed", key="chat_text_input")
    with voice_col:
        audio_data = st.audio_input("Mic", key="audio_recorder")
    st.caption("Allow microphone access when prompted.")

    if text_input:
        process_text(text_input, lang)
        st.rerun()

    if audio_data is not None:
        try:
            audio_data.seek(0)
            audio_bytes = audio_data.read()
        except Exception:
            audio_bytes = None
        if not audio_bytes or len(audio_bytes) < 100:
            st.warning("Recording too short. Try again.")
        else:
            audio_hash = hashlib.md5(audio_bytes).hexdigest()
            if audio_hash != st.session_state.get("last_audio_hash"):
                st.session_state.last_audio_hash = audio_hash
                with st.spinner("Transcribing..."):
                    text = transcribe_audio(audio_bytes, lang)
                if text and not str(text).startswith("ERROR:"):
                    st.success(f"Transcribed: {text}")
                    process_text(text, lang)
                elif str(text).startswith("ERROR:"):
                    st.error(str(text))
                else:
                    st.warning("Could not understand. Try again or type below.")
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
