import os
import hashlib
import streamlit as st

from services.voice_agent.orchestrator import process_text_input, process_voice
from services.voice_agent.session_store import clear_session, get_session


st.set_page_config(page_title="Livestock Multi-turn Assistant", layout="centered")

# Runtime defaults
os.environ.setdefault("AWS_REGION", "ap-south-1")
os.environ.setdefault("TRANSCRIBE_MODE", "local")
os.environ.setdefault("VOICE_S3_BUCKET", "farmer-chat-audio-bucket-198799425726")
os.environ.setdefault("BEDROCK_MODEL_ID", "deepseek.v3-v1:0")

st.title("Livestock Assistant (Multi-turn)")
st.caption(
    f"mode={os.getenv('TRANSCRIBE_MODE')} region={os.getenv('AWS_REGION')} model={os.getenv('BEDROCK_MODEL_ID')}"
)

with st.sidebar:
    st.subheader("Session")
    session_id = st.text_input("Session ID", value="farmer-demo-1")
    if st.button("Reset Conversation"):
        clear_session(session_id)
        st.session_state.messages = []
        st.session_state.last_result = None
        st.success("Session reset")

    st.subheader("Demo Queries")
    st.code("I want to add details about my goat")
    st.code("female")
    st.code("my goat is not eating since yesterday")
    st.code("book a vet appointment tomorrow at 5 pm")


if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_result" not in st.session_state:
    st.session_state.last_result = None
if "last_voice_hash" not in st.session_state:
    st.session_state.last_voice_hash = None


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


def run_turn(user_text=None, audio_bytes=None):
    if user_text is not None:
        result = process_text_input(user_text, session_id=session_id)
        user_view_text = user_text
    else:
        result = process_voice(audio_bytes, session_id=session_id)
        user_view_text = result.get("meta", {}).get("raw_text", "<voice input>")

    st.session_state.messages.append({"role": "user", "content": user_view_text})

    followups = result.get("follow_up_questions", [])
    if followups:
        assistant_text = "Please provide: " + " | ".join(followups)
    elif result.get("complete") and result.get("intent"):
        assistant_text = "Great, I have everything I need. Final JSON is ready below."
    else:
        assistant_text = "Got it. I captured your input."

    st.session_state.messages.append({"role": "assistant", "content": assistant_text})
    st.session_state.last_result = result


# Conversation view
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])


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
