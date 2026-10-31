"""ADK-native rebuild of query_agent's orchestration (Phase 1 of the plan at
/Users/sudhanshu/.claude/plans/elegant-roaming-river.md).

Deliberately does NOT touch db.py or schema.py -- those are the deterministic,
already-hardened data layer (thread-safety fix, LRU cache, blocked-keyword
fix, all from this session's robustness audit) and have nothing to do with
orchestration. The old agent.py this was built alongside (which had unrelated
uncommitted work from another concurrent session) has since been removed --
this is the only implementation now.

farmer_id is bound into the tool closure, never exposed as a parameter the
model could pass -- same principle as every other scoping fix this session
(auth/tenant-scoping is a correctness invariant, not something to trust an
LLM-driven tool call with).
"""
from __future__ import annotations

import asyncio
import os
import threading
import uuid
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.agents.invocation_context import LlmCallsLimitExceededError
from google.adk.agents.run_config import RunConfig
from google.adk.runners import InMemoryRunner, Runner
from google.adk.sessions import BaseSessionService, InMemorySessionService
from google.genai import types

from services.llm_service.bedrock_adapter import TaskTier, model_for_task
from services.query_agent.db import execute_query
from services.query_agent.schema import generate_schema_for_prompt
from services.llm_service.adk_model import build_adk_model

# Native digits per language. Kept in step with SUPPORTED_LANGUAGES
# (appointment_supervisor, animal_registration), which now has all 7
# languages. Malayalam is supported but has no entry here on purpose:
# Malayalam text today uses Western digits (0-9), not ൦-൯, so its answers
# keep 0-9 (_to_native_digits finds no entry and returns the text as is).
_NATIVE_DIGITS = {
    "hi": "०१२३४५६७८९",
    "ta": "௦௧௨௩௪௫௬௭௮௯",
    "te": "౦౧౨౩౪౫౬౭౮౯",
    "kn": "೦೧೨೩೪೫೬೭೮೯",
    "mr": "०१२३४५६७८९",
}

# Unicode script ranges, checked in order -- first match wins. A query with
# no script-specific characters (Latin/English, or a bare number) falls
# through to "en", where digit conversion is a no-op.
_SCRIPT_RANGES = (
    ("hi", (0x0900, 0x097F)),  # Devanagari
    ("ta", (0x0B80, 0x0BFF)),
    ("te", (0x0C00, 0x0C7F)),
    ("kn", (0x0C80, 0x0CFF)),
    ("ml", (0x0D00, 0x0D7F)),  # Malayalam: no _NATIVE_DIGITS entry, so digits stay 0-9
    # Marathi shares Devanagari with Hindi -- detect_language() still
    # returns "hi" for this range (first match wins, script alone can't
    # tell them apart), but _answer_is_native_script needs its own "mr"
    # entry so labels_lang="mr" (from _labels_language/app_language) is
    # recognized as native script too, not just "hi".
    ("mr", (0x0900, 0x097F)),
)


def detect_language(text: str) -> str:
    """Script-based detection for the one thing the model can't be trusted
    to do consistently on its own: converting digits to native numerals
    within an otherwise-correct-language reply (verified live -- the model
    replies in Hindi/Tamil/etc fine, but leaves numbers as plain Western
    digits inconsistently). Deterministic post-processing, not a second
    LLM call -- same "LLM for judgment, code for correctness" split this
    codebase already uses for dates, PINs, and breed validation."""
    for lang, (lo, hi) in _SCRIPT_RANGES:
        if any(lo <= ord(ch) <= hi for ch in text):
            return lang
    return "en"


def _to_native_digits(text: str, lang: str) -> str:
    digits = _NATIVE_DIGITS.get(lang)
    if not digits or not isinstance(text, str):
        return text
    return text.translate(str.maketrans("0123456789", digits))


def _localize_numbers(value: Any, lang: str) -> Any:
    """Recurse through a query result (string / int / float / dict / list)
    converting every digit to the target language's native numerals. A
    no-op for English.

    Intended for display-only strings (text/speech answer, and cells in a
    parallel data.display copy used by the UI). MUST NOT be applied to
    the machine-readable data payload -- doing so silently corrupted
    tag/ID/date strings (e.g. 'G-1122' -> 'G-११२२', '2025-09-25' ->
    '२०२५-०९-२५') and changed numeric row cells to strings, breaking DB
    round-trip and the API's numeric type contract for any downstream
    consumer that sorts/sums/compares. Found in review of PR #15's
    original always-translate behavior."""
    if lang == "en" or lang not in _NATIVE_DIGITS:
        return value
    if isinstance(value, str):
        return _to_native_digits(value, lang)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return _to_native_digits(str(value), lang)
    if isinstance(value, dict):
        return {k: _localize_numbers(v, lang) for k, v in value.items()}
    if isinstance(value, list):
        return [_localize_numbers(v, lang) for v in value]
    return value


def _answer_is_native_script(answer: str, lang: str) -> bool:
    """Confirm the model's answer is actually in the same script as the
    query language before running digit conversion. Real bug found in
    review: a Hindi query whose model reply came back English (fallback,
    off-topic, model quirk) still got its digits translated -- producing
    'You have १२ animals', mixed-script gibberish. If the answer contains
    no character from the language's own script range, skip localization
    entirely rather than force a mismatch."""
    if lang == "en" or not answer:
        return False
    for detected_lang, (lo, hi) in _SCRIPT_RANGES:
        if detected_lang == lang:
            return any(lo <= ord(ch) <= hi for ch in answer)
    return False


# Static translation catalog for the fixed, known column names a SELECT
# against animals/health_logs/appointments (and the health tables:
# ai_health_logs, vaccination_records) actually returns -- reuses the
# same labels already established in animal_registration/appointment_
# supervisor's own _LABELS catalogs for the overlapping fields, so a
# farmer sees the identical word for "breed" everywhere in the app.
# Deliberately NOT an LLM call: an aggregate/alias column (COUNT(*), AS
# total, ...) isn't in this dict and is left as-is in English rather than
# guessed at -- same "don't invent, leave it out" principle used
# throughout this codebase. Covers the common case (a farmer asking for
# raw fields); an aliased query is the one case this doesn't localize.
_COLUMN_LABELS = {
    "hi": {
        "species": "प्रजाति", "breed": "नस्ल", "sex": "लिंग", "tag_or_name": "टैग/नाम",
        "status": "स्थिति", "birth_date": "जन्म तिथि", "current_location": "स्थान",
        "age_years": "उम्र (वर्ष)", "issue": "समस्या", "notes": "नोट्स",
        "date": "तारीख", "time": "समय",
        "vaccine_name": "टीका", "due_date": "नियत तारीख", "administered_date": "टीका लगने की तारीख",
        "recorded_at": "दर्ज तारीख", "log_timestamp": "दर्ज तारीख", "risk_level": "जोखिम",
        "symptoms_reported": "लक्षण", "potential_ailments": "संभावित बीमारियाँ",
        "ai_diagnosis_suggestion": "AI सुझाव", "first_aid_advice": "प्राथमिक उपचार",
        "issue_summary": "समस्या", "veterinarian_notes": "डॉक्टर के नोट्स",
    },
    "ta": {
        "species": "இனம்", "breed": "இனவகை", "sex": "பாலினம்", "tag_or_name": "டேக்/பெயர்",
        "status": "நிலை", "birth_date": "பிறந்த தேதி", "current_location": "இடம்",
        "age_years": "வயது (ஆண்டுகள்)", "issue": "பிரச்சினை", "notes": "குறிப்புகள்",
        "date": "தேதி", "time": "நேரம்",
        "vaccine_name": "தடுப்பூசி", "due_date": "போட வேண்டிய தேதி", "administered_date": "போட்ட தேதி",
        "recorded_at": "பதிவு தேதி", "log_timestamp": "பதிவு தேதி", "risk_level": "ஆபத்து",
        "symptoms_reported": "அறிகுறிகள்", "potential_ailments": "சாத்தியமான நோய்கள்",
        "ai_diagnosis_suggestion": "AI பரிந்துரை", "first_aid_advice": "முதலுதவி",
        "issue_summary": "பிரச்சினை", "veterinarian_notes": "மருத்துவர் குறிப்புகள்",
    },
    "te": {
        "species": "జాతి", "breed": "బ్రీడ్", "sex": "లింగం", "tag_or_name": "ట్యాగ్/పేరు",
        "status": "స్థితి", "birth_date": "పుట్టిన తేదీ", "current_location": "స్థానం",
        "age_years": "వయస్సు (సంవత్సరాలు)", "issue": "సమస్య", "notes": "గమనికలు",
        "date": "తేదీ", "time": "సమయం",
        "vaccine_name": "టీకా", "due_date": "వేయవలసిన తేదీ", "administered_date": "వేసిన తేదీ",
        "recorded_at": "నమోదు తేదీ", "log_timestamp": "నమోదు తేదీ", "risk_level": "ప్రమాదం",
        "symptoms_reported": "లక్షణాలు", "potential_ailments": "సాధ్యమైన వ్యాధులు",
        "ai_diagnosis_suggestion": "AI సూచన", "first_aid_advice": "ప్రథమ చికిత్స",
        "issue_summary": "సమస్య", "veterinarian_notes": "డాక్టర్ గమనికలు",
    },
    "kn": {
        "species": "ಪ್ರಭೇದ", "breed": "ತಳಿ", "sex": "ಲಿಂಗ", "tag_or_name": "ಟ್ಯಾಗ್/ಹೆಸರು",
        "status": "ಸ್ಥಿತಿ", "birth_date": "ಜನನ ದಿನಾಂಕ", "current_location": "ಸ್ಥಳ",
        "age_years": "ವಯಸ್ಸು (ವರ್ಷಗಳು)", "issue": "ಸಮಸ್ಯೆ", "notes": "ಟಿಪ್ಪಣಿಗಳು",
        "date": "ದಿನಾಂಕ", "time": "ಸಮಯ",
        "vaccine_name": "ಲಸಿಕೆ", "due_date": "ನೀಡಬೇಕಾದ ದಿನಾಂಕ", "administered_date": "ನೀಡಿದ ದಿನಾಂಕ",
        "recorded_at": "ದಾಖಲಿಸಿದ ದಿನಾಂಕ", "log_timestamp": "ದಾಖಲಿಸಿದ ದಿನಾಂಕ", "risk_level": "ಅಪಾಯ",
        "symptoms_reported": "ಲಕ್ಷಣಗಳು", "potential_ailments": "ಸಂಭವನೀಯ ರೋಗಗಳು",
        "ai_diagnosis_suggestion": "AI ಸಲಹೆ", "first_aid_advice": "ಪ್ರಥಮ ಚಿಕಿತ್ಸೆ",
        "issue_summary": "ಸಮಸ್ಯೆ", "veterinarian_notes": "ವೈದ್ಯರ ಟಿಪ್ಪಣಿಗಳು",
    },
    "en": {
        "species": "Species", "breed": "Breed", "sex": "Sex", "tag_or_name": "Tag / Name",
        "status": "Status", "birth_date": "Date of birth", "current_location": "Location",
        "age_years": "Age (years)", "issue": "Issue", "notes": "Notes",
        "date": "Date", "time": "Time",
        "vaccine_name": "Vaccine", "due_date": "Due date", "administered_date": "Given on",
        "recorded_at": "Recorded on", "log_timestamp": "Recorded on", "risk_level": "Risk",
        "symptoms_reported": "Symptoms", "potential_ailments": "Possible illnesses",
        "ai_diagnosis_suggestion": "AI suggestion", "first_aid_advice": "First aid",
        "issue_summary": "Issue", "veterinarian_notes": "Vet notes",
    },
    "mr": {
        "species": "प्रजाती", "breed": "जात", "sex": "लिंग", "tag_or_name": "टॅग/नाव",
        "status": "स्थिती", "birth_date": "जन्मतारीख", "current_location": "ठिकाण",
        "age_years": "वय (वर्षे)", "issue": "समस्या", "notes": "टिपा",
        "date": "तारीख", "time": "वेळ",
        "vaccine_name": "लस", "due_date": "नियोजित तारीख", "administered_date": "लस दिल्याची तारीख",
        "recorded_at": "नोंद तारीख", "log_timestamp": "नोंद तारीख", "risk_level": "धोका",
        "symptoms_reported": "लक्षणे", "potential_ailments": "संभाव्य आजार",
        "ai_diagnosis_suggestion": "AI सूचना", "first_aid_advice": "प्रथमोपचार",
        "issue_summary": "समस्या", "veterinarian_notes": "डॉक्टरांच्या टिपा",
    },
    "ml": {
        "species": "വർഗ്ഗം", "breed": "ഇനം", "sex": "ലിംഗം", "tag_or_name": "ടാഗ്/പേര്",
        "status": "നില", "birth_date": "ജനനത്തീയതി", "current_location": "സ്ഥലം",
        "age_years": "പ്രായം (വർഷം)", "issue": "പ്രശ്നം", "notes": "കുറിപ്പുകൾ",
        "date": "തീയതി", "time": "സമയം",
        "vaccine_name": "വാക്സിൻ", "due_date": "നൽകേണ്ട തീയതി", "administered_date": "നൽകിയ തീയതി",
        "recorded_at": "രേഖപ്പെടുത്തിയ തീയതി", "log_timestamp": "രേഖപ്പെടുത്തിയ തീയതി", "risk_level": "അപകടസാധ്യത",
        "symptoms_reported": "ലക്ഷണങ്ങൾ", "potential_ailments": "സാധ്യതയുള്ള രോഗങ്ങൾ",
        "ai_diagnosis_suggestion": "AI നിർദ്ദേശം", "first_aid_advice": "പ്രഥമശുശ്രൂഷ",
        "issue_summary": "പ്രശ്നം", "veterinarian_notes": "ഡോക്ടറുടെ കുറിപ്പുകൾ",
    },
}


def _localize_columns(columns: "list[str] | None", lang: str) -> "list[str] | None":
    if not columns or lang not in _COLUMN_LABELS:
        return columns
    labels = _COLUMN_LABELS[lang]
    return [labels.get(c, c) for c in columns]


def _labels_language(script_lang: str, app_language: "str | None") -> str:
    """Language for table headings: the app's language when we have labels
    for it, else the language detected from the query's script. The script
    alone can't tell Marathi from Hindi (both Devanagari), and a farmer
    typing in Roman script looks like English, so the app's choice wins.

    Normalizes both "-" and "_" locale separators ("mr-IN", "mr_IN") --
    without this, an underscore-style tag silently fell through to
    script_lang, reinstating the exact Hindi-for-Marathi bug this
    function exists to fix (found in deep-review of PR #41)."""
    app = (app_language or "").strip().replace("_", "-").split("-")[0].lower()
    return app if app in _COLUMN_LABELS else script_lang


def _localize_answer_digits(text_answer: str, speech_text: str, labels_lang: str) -> "tuple[str, str]":
    """Convert native-script digits in the model's text/speech answer.
    Deterministic post-processing: the model replies in the right
    language but is inconsistent about native-digit numerals within it
    (verified live) -- fix in code, not the model. Only runs if the
    answer really IS in that script; a Hindi query with an English
    fallback answer previously came back as "You have १२ animals"
    (mixed script) without this guard.

    Takes labels_lang (the same app-language-aware choice the
    data["display"] block uses, from _labels_language), not the raw
    script-detected query language. Real bug, found in whole-dev-branch
    review: using the raw script-detected language meant an en-IN app
    user typing a query in Hindi script could get Devanagari digits in
    the text/speech answer while data["display"] (correctly) showed
    Latin digits in the same response. _answer_is_native_script("en",
    ...) already no-ops unconditionally (see its own guard), so this is
    safe for every labels_lang value, not just the hi/mr case that
    motivated it."""
    if _answer_is_native_script(text_answer, labels_lang):
        text_answer = _localize_numbers(text_answer, labels_lang)
    if _answer_is_native_script(speech_text, labels_lang):
        speech_text = _localize_numbers(speech_text, labels_lang)
    return text_answer, speech_text


_INSTRUCTION_TEMPLATE = """You are a livestock data analyst answering one farmer's questions about \
their own farm records.

Database schema:
{schema}

Rules:
- Use the run_sql_query tool to answer. Never answer from memory/guesswork.
- The query MUST be a single SQLite SELECT statement.
- Use COUNT(*) when counting; GROUP BY when the farmer wants a breakdown by category; ORDER BY for listing/sorting.
- Use LOWER() for case-insensitive text filtering.
- The database stores species/breed/status and other enum-like values in English only (e.g. 'goat', 'sheep', 'active'). Regardless of what language the farmer's question is in, any such value used in a WHERE clause must be the English database value, never translated or transliterated -- e.g. a Hindi question about "बकरी" must filter species = 'goat', not species = 'बकरी'.
- If run_sql_query returns success=false, read the error and try a corrected query -- do not give up after one attempt, and do not repeat the exact same failing query.
- If asking for a single total/count, give just the number in your answer.
- If asking for a breakdown by category, show EACH group with its count -- never summarize or say "ranging from"/"most are" when specific data was requested.
- A general word for the farmer's animals ("cattle", "livestock", "animals", or the same in any language) means ALL of their animals: filter by species only when the farmer clearly names one species. If a filter by species finds nothing, check whether the farmer has animals of other species before saying they have none.
- A request for a "health report", or how the farmer's animals are doing health-wise, is about their health records, not the animal list: look in ai_health_logs (risk level, symptoms), health_logs (recorded problems) and vaccination_records (pending vaccines), joined to animals for each animal's name, newest first. Select the records themselves (one query per table), not only how many there are. If there are no health records, say so plainly.
- Otherwise, give a natural conversational answer.
- Never mention SQL, tables, columns, or any technical/database terms in your final answer -- speak like a farm advisor, not a database.
- A bare greeting ("hi", "hello", "hey") with NO real question attached gets a plain greeting back, under 10 words, e.g. "Hi! What would you like to know about your farm?" -- do NOT list your capabilities (animal counts, health records, appointments, etc.) unless the farmer's message actually asked what you can do.
- If the farmer's message contains a greeting word ("hello", "namaste", "hi") ALONGSIDE a real question (e.g. "hello, how many animals do I have"), answer the question directly -- do NOT prepend a greeting/"hello"/"namaste" to the answer. One farmer message, one direct answer; the greeting word was just how they opened their sentence, not a separate thing to reply to.
- Never open an answer with "thank you"/"धन्यवाद" or similar courtesy filler either -- go straight to the answer.
- You are a farm/livestock assistant ONLY -- not a general-purpose chatbot. If the farmer's message has nothing to do with their farm, animals, or records (general knowledge, world facts, other topics entirely), do NOT answer it from your own knowledge even if you know the answer. Say plainly that you can only help with questions about their farm, and ask what they'd like to know about it instead. This applies however confidently you could answer -- being able to answer something is not the same as it being in scope.

Your answer is shown as text AND read aloud by text-to-speech -- these can differ. The text answer can be as detailed as the question needs (full breakdowns, full lists). The spoken version must always be short, since a farmer listening doesn't want a list of 5+ numbers read out loud one by one.

So: after your full text answer, on its own line, write exactly `---SPOKEN---` followed by a short, spoken-friendly summary of the same answer -- one sentence, no itemized lists, no reading out every number in a breakdown (say "you have 53 animals across 5 species" instead of naming each species and count). If your text answer is already one short sentence, the spoken version can repeat it as-is. Always include the `---SPOKEN---` line, even for a greeting."""


def _make_run_sql_query_tool(farmer_id: str):
    def run_sql_query(sql: str) -> dict[str, Any]:
        """Run a single read-only SQL SELECT query against this farmer's own livestock database.

        Args:
            sql: A single SQLite SELECT statement. Do not add a farmer_id
                filter -- the database already contains only this farmer's rows.

        Returns:
            On success: {"success": true, "columns": [...], "rows": [...], "row_count": int, "truncated": bool}.
            On failure: {"success": false, "error": "..."} -- read the error and retry with a corrected query.
        """
        try:
            return execute_query(sql, farmer_id)
        except ValueError as exc:
            return {"success": False, "error": str(exc)}

    return run_sql_query


def build_query_agent(farmer_id: str) -> LlmAgent:
    """One Agent per farmer_id -- farmer_id is baked into the tool closure
    above, not passed through the model, so no prompt can ever redirect a
    query at a different farmer's data."""
    model_spec = model_for_task(TaskTier.GENERATION)
    schema = generate_schema_for_prompt()

    from services.common.adk_telemetry import make_adk_callbacks
    return LlmAgent(
        name="query_agent",
        description=(
            "Answers a farmer's questions about their own livestock data -- "
            "animal counts, health logs, appointments, vaccination records, "
            "farm details -- by querying the farm database. Use this for any "
            "'how many'/'list'/'show me'/'when was'/data-lookup question "
            "about the farmer's own animals or records."
        ),
        model=build_adk_model(TaskTier.GENERATION, model_spec["id"], temperature=model_spec["temperature"]),
        instruction=_INSTRUCTION_TEMPLATE.format(schema=schema),
        tools=[_make_run_sql_query_tool(farmer_id)],
        # Saves the final answer into the session state, so the next turn
        # (and later, other agents) can read what was last answered.
        output_key="last_query_answer",
        **make_adk_callbacks("query_agent"),
    )


_SPOKEN_MARKER = "---SPOKEN---"


def _split_text_and_speech(answer_text: str) -> tuple[str, str]:
    """Text and audio can legitimately differ (full breakdown in text, one
    short sentence spoken) -- the instruction asks the model to emit both
    in one call, separated by a marker, rather than a second LLM call per
    turn. Degrades gracefully if the model ever omits the marker: the full
    text is used for speech too rather than crashing or losing the answer."""
    if _SPOKEN_MARKER in answer_text:
        text_part, _, speech_part = answer_text.partition(_SPOKEN_MARKER)
        text_part = text_part.strip()
        speech_part = speech_part.strip()
        return text_part, (speech_part or text_part)
    return answer_text, answer_text


# Real bug, found in code review: the old hand-rolled loop had
# MAX_RETRIES=2 (at most 3 SQL-generation attempts) with a clean fallback
# message on exhaustion. The ADK migration dropped that cap entirely --
# ADK's own default is 500 LLM calls per run, and process_query_adk never
# caught the exception it raises on exceeding it, so a persistently
# failing/ambiguous query could drive up to 500 calls before crashing
# unhandled instead of failing cleanly. Explicit, much lower cap here,
# matching the old bound's spirit (a handful of real attempts, not
# hundreds) while still allowing for ADK's own tool-call/response
# round-trips per attempt.
_MAX_LLM_CALLS = 8


_APP_NAME = "farmer_chat_query_agent"

# One session store for the whole process. Previously a fresh InMemoryRunner
# (and so a fresh, empty session) was built on every turn, so the agent had
# no memory of the chat and follow-ups like "and sheep?" had no context.
_IN_MEMORY_SESSIONS = InMemorySessionService()

# Upper bound on events kept in one ADK session. Past this the session is
# restarted, so a long chat does not keep growing every LLM call's prompt.
_MAX_SESSION_EVENTS = 40

# Per-session lock, same two-level pattern as pincode_store's _build_locks
# and weather_alert's own copy of this fix: without it, two concurrent
# turns for the same user_id+session_id (e.g. a duplicate webhook delivery)
# can race get/delete/create on the shared InMemorySessionService -- one
# turn's delete_session can land between the other's get_session and
# create_session, so that turn's create_session then collides with (or
# silently clobbers) the one just made, losing the session's history
# mid-conversation.
_session_locks: dict[str, threading.Lock] = {}
_session_locks_guard = threading.Lock()


def _session_lock(key: str) -> threading.Lock:
    with _session_locks_guard:
        return _session_locks.setdefault(key, threading.Lock())


def _db_engine_kwargs(db_url: str) -> dict:
    """Engine settings for DatabaseSessionService. NullPool for real
    databases (see _session_service). An in-memory SQLite URL gets nothing
    extra: ADK gives it a StaticPool itself, and NullPool there would hand
    every connection a new, empty database. An unparseable URL also gets
    nothing extra, so ADK raises its own error with the password redacted."""
    from sqlalchemy.engine import make_url
    from sqlalchemy.pool import NullPool

    try:
        url = make_url(db_url)
    except Exception:
        return {}
    if url.get_backend_name() == "sqlite" and url.database in (None, "", ":memory:"):
        return {}
    return {"poolclass": NullPool}


def _session_service() -> BaseSessionService:
    """In-memory by default. Setting ADK_SESSION_DB_URL (a SQLAlchemy URL)
    keeps sessions across server restarts. A new DatabaseSessionService is
    built per call because each process_query_adk call runs in its own
    asyncio.run event loop and a DB engine must not be shared across event
    loops; the data itself lives in the database, so nothing is lost.

    NullPool (finding 8 of the PR #28 review): a pooled engine per call
    meant a new connection pool on every turn, which on Postgres can use up
    the database's connections. With NullPool each call opens a connection
    and closes it as soon as it is released, so nothing piles up. Cost is
    about 10ms of connect time per turn on Postgres and none on SQLite,
    small next to 1-5s of LLM work. Revisit with one shared event loop (or
    one per worker thread) only when /chat/turn latency is the bottleneck
    AND sessions are on Postgres AND traffic is above ~5 requests/second."""
    db_url = os.getenv("ADK_SESSION_DB_URL", "").strip()
    if db_url:
        from google.adk.sessions import DatabaseSessionService
        return DatabaseSessionService(db_url=db_url, **_db_engine_kwargs(db_url))
    return _IN_MEMORY_SESSIONS


async def _get_or_create_session(service: BaseSessionService, user_id: str, session_id: str | None):
    """Reuses the chat's own session when the caller passes its session_id,
    so the agent sees the earlier turns of that chat. Sessions are keyed by
    user_id (farmer-<id>) as well, so one farmer can never read another
    farmer's session even with the same session_id. With no session_id the
    old behaviour is kept: a fresh one-off session."""
    if not session_id:
        return await service.create_session(app_name=_APP_NAME, user_id=user_id)

    with _session_lock(f"{user_id}:{session_id}"):
        session = await service.get_session(app_name=_APP_NAME, user_id=user_id, session_id=session_id)
        if session is not None and len(session.events) <= _MAX_SESSION_EVENTS:
            return session
        if session is not None:
            await service.delete_session(app_name=_APP_NAME, user_id=user_id, session_id=session_id)
        return await service.create_session(app_name=_APP_NAME, user_id=user_id, session_id=session_id)


# Lookups kept for one answer's data_sets: the last few distinct ones (a
# retried, identical query counts once). The records card shows up to 3 of
# them; a few more are kept because a single count adds nothing there.
_MAX_DATA_SETS = 5


def _distinct_lookups(results: "list[dict[str, Any]]") -> "list[dict[str, Any]]":
    """The turn's successful lookups without repeats (same columns and rows),
    last _MAX_DATA_SETS, in the order they were made."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for r in results:
        key = repr((r.get("columns"), r.get("rows")))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out[-_MAX_DATA_SETS:]


def _data_payload(sql_result: "dict[str, Any]", labels_lang: str) -> "dict[str, Any]":
    """One lookup's rows for the API response.

    Raw data payload stays machine-readable (English column identifiers,
    native int/float scalars, tag/ID/date strings unchanged) -- reviewers
    found the previous always-translate behavior corrupted IDs and dates so
    they no longer round-tripped to the DB. Localized copies for UI display
    live in data["display"], keyed the same way, so the frontend can pick one
    or the other without ambiguity. Headings and row digits both follow
    labels_lang so the whole response is internally consistent in one
    language (found in deep-review of PR #41)."""
    raw_data = {
        "columns": sql_result.get("columns"),
        "rows": sql_result.get("rows"),
        "row_count": sql_result.get("row_count"),
        "truncated": sql_result.get("truncated", False),
    }
    if labels_lang in _COLUMN_LABELS:
        raw_data["display"] = {
            "columns": _localize_columns(raw_data["columns"], labels_lang),
            "rows": _localize_numbers(raw_data["rows"], labels_lang),
        }
    return raw_data


async def _run_query_async(
    query: str,
    farmer_id: str,
    session_id: str | None = None,
    app_language: str | None = None,
) -> dict[str, Any]:
    agent = build_query_agent(farmer_id)
    service = _session_service()
    runner = Runner(agent=agent, app_name=_APP_NAME, session_service=service)
    user_id = f"farmer-{farmer_id}"
    session = await _get_or_create_session(service, user_id, session_id)
    message = types.Content(role="user", parts=[types.Part(text=query)])

    answer_text: str | None = None
    last_successful_result: dict[str, Any] | None = None
    # Every successful lookup of this turn, in order: a health report needs
    # several (AI health checks, health problems, pending vaccines), and the
    # app's records card shows each of them (data_sets below).
    successful_results: list[dict[str, Any]] = []

    try:
        async for event in runner.run_async(
            user_id=user_id, session_id=session.id, new_message=message,
            run_config=RunConfig(max_llm_calls=_MAX_LLM_CALLS),
        ):
            for fr in event.get_function_responses():
                if fr.name == "run_sql_query" and isinstance(fr.response, dict) and fr.response.get("success"):
                    last_successful_result = fr.response
                    successful_results.append(fr.response)
            if event.is_final_response() and event.content and event.content.parts:
                answer_text = "".join(p.text for p in event.content.parts if p.text)
    except LlmCallsLimitExceededError:
        fallback = "I encountered an error trying to answer that. Please try rephrasing your question."
        return {"answer": fallback, "sql": None, "data": None, "speech_text": fallback}

    if not answer_text:
        return {"answer": "I couldn't understand the query. Please rephrase.", "sql": None, "data": None, "speech_text": "I couldn't understand the query. Please rephrase."}

    text_answer, speech_text = _split_text_and_speech(answer_text)

    lang = detect_language(query)
    labels_lang = _labels_language(lang, app_language)
    text_answer, speech_text = _localize_answer_digits(text_answer, speech_text, labels_lang)

    if last_successful_result is None:
        return {"answer": text_answer, "sql": None, "data": None, "speech_text": speech_text}

    raw_data = _data_payload(last_successful_result, labels_lang)
    result = {
        "answer": text_answer,
        "sql": last_successful_result.get("sql"),
        "data": raw_data,
        "speech_text": speech_text,
    }
    data_sets = _distinct_lookups(successful_results)
    if len(data_sets) >= 2:
        result["data_sets"] = [_data_payload(r, labels_lang) for r in data_sets]
    return result


def process_query_adk(
    query: str,
    farmer_id: str,
    session_id: str | None = None,
    app_language: str | None = None,
) -> dict[str, Any]:
    """Drop-in replacement for agent.py's process_query(), same return shape
    ({"answer", "sql", "data"}), routed through an ADK Agent instead of the
    hand-rolled generate-SQL/execute/format/retry loop. Sync wrapper because
    every caller in this codebase (chat_orchestrator, appointment_supervisor's
    off-topic probe) is itself sync.

    session_id (optional): the chat's session id. When given, the same ADK
    session is reused across turns so the agent remembers the conversation.
    When omitted, behaviour is unchanged (one-off session)."""
    return asyncio.run(_run_query_async(query, farmer_id, session_id, app_language))
