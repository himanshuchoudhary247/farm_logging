import os
import hashlib
import streamlit as st

from gateways import (
    create_animal_for_farmer,
    create_health_log,
    create_preconsult_appointment,
    list_animals_for_farmer,
    update_animal_for_farmer,
)
from services.voice_agent.orchestrator import process_text_input, process_voice
from services.voice_agent.session_store import clear_session, get_session


st.set_page_config(page_title="Livestock Multi-turn Assistant", layout="centered")

# Runtime defaults
os.environ.setdefault("AWS_REGION", "ap-south-1")
os.environ.setdefault("TRANSCRIBE_MODE", "aws")
os.environ.setdefault("VOICE_S3_BUCKET", "farmer-chat-audio-bucket-198799425726")
os.environ.setdefault("BEDROCK_MODEL_ID", "deepseek.v3-v1:0")
os.environ.setdefault("AWS_TRANSCRIBE_LANGUAGE_CODE", "en-IN")
os.environ.setdefault("TRANSCRIBE_FALLBACK_TO_LOCAL", "true")

st.title("Livestock Assistant (Multi-turn)")
st.caption(
    f"mode={os.getenv('TRANSCRIBE_MODE')} stt=amazon-transcribe lang={os.getenv('AWS_TRANSCRIBE_LANGUAGE_CODE')} fallback_local={os.getenv('TRANSCRIBE_FALLBACK_TO_LOCAL')} region={os.getenv('AWS_REGION')} model={os.getenv('BEDROCK_MODEL_ID')}"
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
    if followups:
        formatted_followups = []
        for q in followups:
            q_text = str(q).strip()
            if q_text.lower().startswith("please provide:"):
                formatted_followups.append(q_text)
            else:
                formatted_followups.append(f"Please provide: {q_text}")
        assistant_text = " | ".join(formatted_followups)
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
