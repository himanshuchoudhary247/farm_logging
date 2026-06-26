import streamlit as st

from services.voice_agent.transcribe import transcribe_audio
from services.voice_agent.orchestrator import process_voice, process_text_input
import json
import os


st.set_page_config(page_title="Voice Test", layout="centered")

st.title("Voice → Full Pipeline Test")

st.write("Test voice or text input and inspect structured JSON output.")

# Ensure required env vars are present for AWS mode (dev convenience)
os.environ.setdefault("AWS_REGION", "ap-south-1")
os.environ.setdefault("VOICE_S3_BUCKET", "farmer-chat-audio-bucket-198799425726")
os.environ.setdefault("TRANSCRIBE_MODE", "aws")
os.environ["BEDROCK_MODEL_ID"] = "deepseek.v3-v1:0"
os.environ.setdefault("AWS_TRANSCRIBE_LANGUAGE_CODE", "en-IN")
os.environ.setdefault("AWS_TRANSCRIBE_MULTILINGUAL", "true")
os.environ.setdefault("AWS_TRANSCRIBE_LANGUAGE_OPTIONS", "en-IN,hi-IN,kn-IN,te-IN")
os.environ.setdefault("TRANSCRIBE_FALLBACK_TO_LOCAL", "false")

st.caption(
    f"Using stt=amazon-transcribe mode={os.getenv('TRANSCRIBE_MODE')} multi={os.getenv('AWS_TRANSCRIBE_MULTILINGUAL')} lang_opts={os.getenv('AWS_TRANSCRIBE_LANGUAGE_OPTIONS')} fallback_local={os.getenv('TRANSCRIBE_FALLBACK_TO_LOCAL')} bucket={os.getenv('VOICE_S3_BUCKET')} region={os.getenv('AWS_REGION')} model={os.getenv('BEDROCK_MODEL_ID')}"
)

session_id = st.text_input("Session ID", value="demo-user-1")

st.subheader("Demo Queries")
demo_queries = [
    "I want to add details about my goat",
    "my goat is not eating since yesterday",
    "book a vet appointment tomorrow at 5 pm",
    "female",
]
for q in demo_queries:
    st.code(q)


def safe_json_display(data):
    try:
        if isinstance(data, str):
            data = json.loads(data)
        st.json(data)
    except Exception as e:
        st.warning("Failed to render JSON")
        st.code(str(data))
        st.text(f"Error: {e}")


def show_result(result):
    st.success("Pipeline complete")

    st.subheader("Transcript / Input")
    st.write(result.get("meta", {}).get("raw_text"))

    st.subheader("Intent")
    st.write(result.get("intent"))

    st.subheader("Target Tables")
    st.write(result.get("target_tables"))

    st.subheader("Entities")
    safe_json_display(result.get("entities"))

    st.subheader("Follow-up Questions")
    safe_json_display(result.get("follow_up_questions"))

    st.subheader("Disambiguation")
    safe_json_display(result.get("disambiguation"))

    st.subheader("Full JSON Output")
    safe_json_display(result)

    st.subheader("RAW LLM OUTPUT")
    st.code(result.get("_raw", "<no raw captured>"))


st.subheader("Text Test")
text_input = st.text_input("Enter text query")
if st.button("Run Text Pipeline"):
    try:
        result = process_text_input(text_input, session_id=session_id)
        show_result(result)
    except Exception:
        import traceback
        st.error("Full Error:")
        st.text(traceback.format_exc())

audio = st.audio_input("Record your voice")

if audio is not None:
    st.audio(audio)

    col1, col2 = st.columns(2)

    if col1.button("Transcribe Only"):
        with st.spinner("Transcribing..."):
            try:
                text = transcribe_audio(audio.getvalue())
                st.success("Transcription complete")
                st.subheader("Transcript")
                st.write(text)
            except Exception as e:
                st.error(f"Error: {e}")

    if col2.button("Run Full Pipeline"):
        with st.spinner("Running full pipeline..."):
            try:
                result = process_voice(audio.getvalue(), session_id=session_id)
                show_result(result)

            except Exception as e:
                import traceback
                st.error("Full Error:")
                st.text(traceback.format_exc())
