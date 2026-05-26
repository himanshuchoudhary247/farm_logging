from __future__ import annotations

import os
from typing import Any, List, Optional

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from utils.env_check import validate_env

validate_env()

from gateways import (
    complete_text,
    create_consultation,
    create_health_log,
    list_animals_for_farmer,
    list_consultations_for_farmer,
    list_farmer_accounts,
    list_health_logs_for_farmer,
    login,
)
import requests
from llm.config import load_llm_config
from llm.prompts import GENERAL_SYSTEM, TRIAGE_SYSTEM
from models import Animal


def _init_session() -> None:
    if "farmer_id" not in st.session_state:
        st.session_state.farmer_id = None
    if "farmer_name" not in st.session_state:
        st.session_state.farmer_name = None
    if "is_admin" not in st.session_state:
        st.session_state.is_admin = False
    if "general_messages" not in st.session_state:
        st.session_state.general_messages = []
    if "triage_messages" not in st.session_state:
        st.session_state.triage_messages = []
    if "triage_animal_id" not in st.session_state:
        st.session_state.triage_animal_id = None


def _animal_selectbox(label: str, animals: List[Animal], key: str) -> Optional[Animal]:
    if not animals:
        st.warning("No animals registered. Contact support to add animals.")
        return None
    return st.selectbox(
        label,
        animals,
        format_func=lambda a: f"{a.tag_or_name} — {a.species}",
        key=key,
    )


def _animal_selectbox_optional(
    label: str, animals: list[Animal], key: str
) -> Optional[Animal]:
    if not animals:
        return None
    options: List[Optional[Animal]] = [None] + animals

    def fmt(a: Optional[Animal]) -> str:
        if a is None:
            return "— Not linked —"
        return f"{a.tag_or_name} — {a.species}"

    return st.selectbox(label, options, format_func=fmt, key=key)


def _render_login() -> None:
    st.title("Farmer livestock assistant")
    st.caption("Sign in to continue.")
    with st.form("login"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Log in")
    if submit:
        f = login(username, password)
        if f is None:
            st.error("Invalid username or password.")
        else:
            st.session_state.farmer_id = f.id
            st.session_state.farmer_name = f.name
            st.session_state.is_admin = f.role == "admin"
            st.session_state.general_messages = []
            st.session_state.triage_messages = []
            st.session_state.triage_animal_id = None
            if st.session_state.is_admin:
                st.session_state.pop("admin_farmer_pick", None)
            st.rerun()


def _logout() -> None:
    st.session_state.farmer_id = None
    st.session_state.farmer_name = None
    st.session_state.is_admin = False
    st.session_state.general_messages = []
    st.session_state.triage_messages = []
    st.session_state.triage_animal_id = None
    st.session_state.pop("admin_farmer_pick", None)


def _llm_status_warning() -> None:
    try:
        cfg = load_llm_config().text
    except Exception as e:
        st.warning(f"LLM config issue: {e}")
        return

    provider = cfg.provider.strip().lower()
    if provider in ("openai", "gemini", "google"):
        env_name = (cfg.api_key_env or "").strip()
        if not env_name:
            st.warning(f"`text.api_key_env` is missing for provider `{provider}`.")
            return
        if not os.environ.get(env_name):
            st.warning(
                f"Missing `{env_name}` in environment. Chat replies will fail until it is set."
            )


def _send_general_prompt(prompt: str) -> None:
    st.session_state.general_messages.append({"role": "user", "content": prompt})
    try:
        reply = complete_text(
            [{"role": x["role"], "content": x["content"]} for x in st.session_state.general_messages],
            system=GENERAL_SYSTEM,
        )
        st.session_state.general_messages.append({"role": "assistant", "content": reply})
    except Exception as e:
        st.session_state.general_messages.pop()
        st.error(f"LLM error: {e}")
    st.rerun()


def _send_triage_prompt(prompt: str) -> None:
    st.session_state.triage_messages.append({"role": "user", "content": prompt})
    try:
        reply = complete_text(
            [
                {"role": x["role"], "content": x["content"]}
                for x in st.session_state.triage_messages
            ],
            system=TRIAGE_SYSTEM,
        )
        st.session_state.triage_messages.append({"role": "assistant", "content": reply})
    except Exception as e:
        st.session_state.triage_messages.pop()
        st.error(f"LLM error: {e}")
    st.rerun()


def _general_qa_tab(farmer_id: str, animals: list[Animal]) -> None:
    st.subheader("General Q&A")
    st.caption("Quick suggestions")
    general_suggestions = [
        "What should I do if my animal has fever?",
        "How to improve milk yield naturally?",
        "Signs that need urgent vet visit",
        "Daily feed plan for lactating cattle",
    ]
    g_cols = st.columns(2)
    for i, text in enumerate(general_suggestions):
        with g_cols[i % 2]:
            if st.button(text, key=f"general_suggest_{i}", use_container_width=True):
                _send_general_prompt(text)

    for m in st.session_state.general_messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    prompt = st.chat_input("Ask a question…", key="general_chat_input")
    if prompt:
        _send_general_prompt(prompt)

    if st.button("Clear chat", key="clear_general"):
        st.session_state.general_messages = []
        st.rerun()


def _health_log_tab(farmer_id: str, animals: list[Animal]) -> None:
    st.subheader("Health log")
    st.caption("Quick symptom templates")

    st.markdown("### 🎤 Voice input")
    st.caption("Upload a WAV audio file to test real voice input")
    audio_file = st.file_uploader("Upload audio (.wav)", type=["wav"], key="voice_audio")

    # conversational state
    if "voice_ctx" not in st.session_state:
        st.session_state.voice_ctx = {"base_text": "", "state": {}, "missing": []}

    if st.button("Process audio") and audio_file is not None:
        try:
            # save temp file
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                tmp.write(audio_file.read())
                tmp_path = tmp.name
            # --- Real AWS flow ---
            from services.voice_agent.s3_upload import upload_file_to_s3
            from services.voice_agent.transcribe import TranscribeService

            bucket = os.getenv("VOICE_BUCKET", "farmer-chat-audio-temp")
            key = f"audio/{farmer_id}_{os.path.basename(tmp_path)}"

            s3_uri = upload_file_to_s3(tmp_path, bucket, key)

            transcriber = TranscribeService()
            transcript = transcriber.transcribe_file(s3_uri)

            st.info(f"Transcript: {transcript}")

            # reset conversation
            st.session_state.voice_ctx = {"base_text": transcript, "state": {}, "missing": []}

            resp = requests.post(
                f"http://localhost:8000/farmers/{farmer_id}/voice/health-log",
                json={"text": transcript},
                timeout=20,
            ).json()

            extracted = resp.get("extracted", {})
            missing = resp.get("missing_fields", [])
            st.session_state.voice_ctx["missing"] = missing
            st.session_state.voice_ctx["state"] = extracted

            # prefill form fields
            st.session_state.hl_issue = extracted.get("issue", "")
            st.session_state.hl_appetite = extracted.get("appetite", "")
            st.session_state.hl_temp = str(extracted.get("temperature_c", ""))
            st.session_state.hl_duration = extracted.get("duration", "")
            st.session_state.hl_feces = extracted.get("feces", "")
            st.session_state.hl_notes = extracted.get("notes", "")

            if missing:
                st.warning(f"Missing fields: {', '.join(missing)}")
                followups = {
                    "animal_id": "Which animal is this for?",
                    "issue": "Describe the issue more clearly",
                    "temperature_c": "Tell me the temperature",
                }

                # voice follow-up (audio upload per missing field)
                for m in missing:
                    if m in followups:
                        st.caption(followups[m])
                        fu_audio = st.file_uploader(
                            f"Answer for {m} (.wav)", type=["wav"], key=f"voice_fu_{m}"
                        )
                        if fu_audio is not None and st.button(f"Process answer for {m}", key=f"btn_fu_{m}"):
                            import tempfile
                            from services.voice_agent.s3_upload import upload_file_to_s3
                            from services.voice_agent.transcribe import TranscribeService

                            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                                tmp.write(fu_audio.read())
                                tmp_path = tmp.name

                            bucket = os.getenv("VOICE_BUCKET", "farmer-chat-audio-temp")
                            key = f"audio/fu_{farmer_id}_{os.path.basename(tmp_path)}"
                            s3_uri = upload_file_to_s3(tmp_path, bucket, key)
                            transcript_fu = TranscribeService().transcribe_file(s3_uri)
                            st.info(f"Answer transcript: {transcript_fu}")

                            # stateful merge: only update the missing field using LLM extraction on the answer
                            resp_fu = requests.post(
                                f"http://localhost:8000/farmers/{farmer_id}/voice/health-log",
                                json={"text": transcript_fu},
                                timeout=20,
                            ).json()
                            extracted_fu = resp_fu.get("extracted", {})
                            if m in extracted_fu and extracted_fu.get(m) is not None:
                                st.session_state.voice_ctx["state"][m] = extracted_fu.get(m)

                if st.button("Apply updates"):
                    s = st.session_state.voice_ctx.get("state", {})
                    st.session_state.hl_issue = s.get("issue", "")
                    st.session_state.hl_appetite = s.get("appetite", "")
                    st.session_state.hl_temp = str(s.get("temperature_c", ""))
                    st.session_state.hl_duration = s.get("duration", "")
                    st.session_state.hl_feces = s.get("feces", "")
                    st.session_state.hl_notes = s.get("notes", "")
                    st.success("Updated from voice follow-ups")

            st.success("Audio processed. Review below.")
        except Exception as e:
            st.error(f"Audio processing failed: {e}")
    if st.button("Low appetite + fever", key="hl_tpl_1"):
        st.session_state.hl_issue = "Reduced feed intake with fever signs"
        st.session_state.hl_appetite = "reduced"
        st.session_state.hl_temp = "39.8"
        st.session_state.hl_duration = "1 day"
        st.session_state.hl_feces = "normal"
        st.session_state.hl_notes = "Isolated for monitoring."
    if st.button("Loose stool / diarrhea", key="hl_tpl_2"):
        st.session_state.hl_issue = "Loose stool and weakness"
        st.session_state.hl_appetite = "reduced"
        st.session_state.hl_temp = "39.2"
        st.session_state.hl_duration = "2 days"
        st.session_state.hl_feces = "loose"
        st.session_state.hl_notes = "Started oral rehydration."

    q = st.text_input("Search your animals", key="health_filter")
    filtered = [
        a
        for a in animals
        if q.lower() in f"{a.tag_or_name} {a.species} {a.breed}".lower()
    ]
    animal = _animal_selectbox("Animal", filtered, key="hl_animal") if filtered else None
    if animal is None:
        return

    with st.form("health_log_form"):
        issue = st.text_area(
            "Issue / symptoms",
            placeholder="e.g. Loose droppings since 2 days",
            key="hl_issue",
        )
        appetite = st.selectbox(
            "Appetite",
            ["", "normal", "reduced", "off_feed"],
            format_func=lambda x: x or "— select —",
            key="hl_appetite",
        )
        feces = st.text_input(
            "Feces (optional)",
            placeholder="normal / loose / bloody",
            key="hl_feces",
        )
        temp = st.text_input("Temperature °C (if measured)", placeholder="", key="hl_temp")
        duration = st.text_input("Duration (e.g. 2 days)", placeholder="", key="hl_duration")
        notes = st.text_area("Other notes", placeholder="", key="hl_notes")
        submit = st.form_submit_button("Save health record")

    if submit:
        if not issue.strip():
            st.warning("Please describe the issue.")
        else:
            params: dict[str, Any] = {}
            if appetite:
                params["appetite"] = appetite
            if feces.strip():
                params["feces"] = feces.strip()
            if temp.strip():
                try:
                    params["temperature_c"] = float(temp.strip())
                except ValueError:
                    params["temperature_c_raw"] = temp.strip()
            if duration.strip():
                params["duration"] = duration.strip()
            try:
                row = create_health_log(
                    farmer_id,
                    animal.id,
                    issue.strip(),
                    params,
                    notes.strip(),
                )
                st.success(f"Saved record {row.id}")
            except ValueError as e:
                st.error(str(e))


def _triage_tab(farmer_id: str, animals: list[Animal]) -> None:
    st.subheader("Describe an issue (chat)")
    st.caption("Quick starters")
    triage_suggestions = [
        "My cow is not eating since morning.",
        "Goat has diarrhea for 2 days.",
        "Buffalo has fever and low milk output.",
        "Animal is limping and not standing properly.",
    ]
    t_cols = st.columns(2)
    for i, text in enumerate(triage_suggestions):
        with t_cols[i % 2]:
            if st.button(text, key=f"triage_suggest_{i}", use_container_width=True):
                _send_triage_prompt(text)

    c1, c2 = st.columns(2)
    with c1:
        if st.button("New consultation"):
            st.session_state.triage_messages = []
            st.session_state.triage_animal_id = None
            st.session_state.pop("triage_summary_field", None)
            st.rerun()
    with c2:
        linked = _animal_selectbox_optional(
            "Link to animal (optional)",
            animals,
            key="triage_animal_pick",
        )
        if linked is not None:
            st.session_state.triage_animal_id = linked.id
        else:
            st.session_state.triage_animal_id = None

    for m in st.session_state.triage_messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    prompt = st.chat_input("Describe what you see…", key="triage_input")
    if prompt:
        _send_triage_prompt(prompt)

    summary = st.text_input(
        "Summary for records (optional)",
        placeholder="Short label for this chat",
        key="triage_summary_field",
    )
    if st.button("Save consultation to records"):
        if not st.session_state.triage_messages:
            st.warning("Nothing to save yet.")
        else:
            aid = st.session_state.triage_animal_id
            first_user = next(
                (m["content"] for m in st.session_state.triage_messages if m["role"] == "user"),
                "",
            )
            auto = (first_user[:200] + "…") if len(first_user) > 200 else first_user
            final_summary = summary.strip() or auto or "Consultation"
            try:
                create_consultation(
                    farmer_id,
                    aid,
                    list(st.session_state.triage_messages),
                    final_summary,
                )
                st.success("Consultation saved.")
                st.session_state.triage_messages = []
                st.session_state.triage_animal_id = None
                st.session_state.pop("triage_summary_field", None)
                st.rerun()
            except ValueError as e:
                st.error(str(e))


def _animal_label(animals: list[Animal], aid: str) -> str:
    for a in animals:
        if a.id == aid:
            return f"{a.tag_or_name} ({a.species})"
    return aid


def _records_tab(farmer_id: str, animals: list[Animal]) -> None:
    st.subheader("Your records")
    animal_options: list[str | None] = [None] + [a.id for a in animals]
    labels = {None: "All animals"}
    for a in animals:
        labels[a.id] = f"{a.tag_or_name} — {a.species}"

    pick = st.selectbox(
        "Filter by animal",
        animal_options,
        format_func=lambda x: labels[x],
        key="records_animal",
    )

    logs = list_health_logs_for_farmer(farmer_id)
    if pick:
        logs = [h for h in logs if h.animal_id == pick]

    st.markdown("#### Health logs")
    if not logs:
        st.caption("No health logs match this filter.")
    else:
        rows = [
            {
                "id": h.id,
                "when": h.recorded_at,
                "animal": _animal_label(animals, h.animal_id),
                "issue": h.issue,
                "params": str(h.params) if h.params else "",
            }
            for h in sorted(logs, key=lambda x: x.recorded_at, reverse=True)
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)

    cons = list_consultations_for_farmer(farmer_id)
    if pick:
        cons = [c for c in cons if c.get("animal_id") == pick]

    st.markdown("#### Consultations (describe issue chats)")
    if not cons:
        st.caption("No consultations match this filter.")
    else:
        for c in sorted(cons, key=lambda x: x.get("started_at", ""), reverse=True):
            aid = c.get("animal_id")
            title = c.get("summary") or c.get("id")
            animal_lbl = _animal_label(animals, aid) if aid else "Not linked"
            with st.expander(f"{c.get('started_at', '')} — {title} — {animal_lbl}"):
                for m in c.get("messages", []):
                    st.markdown(f"**{m.get('role')}**: {m.get('content', '')}")


def main() -> None:
    st.set_page_config(page_title="Farmer livestock assistant", page_icon="🐄", layout="wide")
    _init_session()

    if not st.session_state.farmer_id:
        _render_login()
        return

    auth_id = st.session_state.farmer_id

    with st.sidebar:
        role_note = " (admin)" if st.session_state.is_admin else ""
        st.write(f"Signed in as **{st.session_state.farmer_name or auth_id}**{role_note}")
        if st.session_state.is_admin:
            accs = list_farmer_accounts()
            if not accs:
                st.error("No farmer accounts in the database.")
                if st.button("Log out", key="out_admin_empty"):
                    _logout()
                    st.rerun()
                return
            picked = st.selectbox(
                "View / edit as farmer",
                options=accs,
                format_func=lambda a: f"{a.name} ({a.login_username})",
                key="admin_farmer_pick",
            )
            scope_farmer_id = picked.id
        else:
            scope_farmer_id = auth_id

        if st.button("Log out"):
            _logout()
            st.rerun()
        st.caption(f"LLM config: `{os.environ.get('LLM_CONFIG_PATH', 'config/llm.yaml')}`")
        _llm_status_warning()

    animals = list_animals_for_farmer(scope_farmer_id)

    tab_general, tab_log, tab_triage, tab_records = st.tabs(
        ["General Q&A", "Health log", "Describe issue", "Records"]
    )

    with tab_general:
        _general_qa_tab(scope_farmer_id, animals)
    with tab_log:
        _health_log_tab(scope_farmer_id, animals)
    with tab_triage:
        _triage_tab(scope_farmer_id, animals)
    with tab_records:
        _records_tab(scope_farmer_id, animals)


if __name__ == "__main__":
    main()
