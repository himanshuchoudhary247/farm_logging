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
import logging
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

from services.common.name_match import find_name_mentions
from services.llm_service.bedrock_adapter import TaskTier, model_for_task
from services.query_agent.db import execute_query
from services.query_agent.schema import generate_schema_for_prompt
from services.llm_service.adk_model import build_adk_model

logger = logging.getLogger(__name__)

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
# against animals/health_logs/appointments actually returns -- reuses the
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
    },
    "ta": {
        "species": "இனம்", "breed": "இனவகை", "sex": "பாலினம்", "tag_or_name": "டேக்/பெயர்",
        "status": "நிலை", "birth_date": "பிறந்த தேதி", "current_location": "இடம்",
        "age_years": "வயது (ஆண்டுகள்)", "issue": "பிரச்சினை", "notes": "குறிப்புகள்",
        "date": "தேதி", "time": "நேரம்",
    },
    "te": {
        "species": "జాతి", "breed": "బ్రీడ్", "sex": "లింగం", "tag_or_name": "ట్యాగ్/పేరు",
        "status": "స్థితి", "birth_date": "పుట్టిన తేదీ", "current_location": "స్థానం",
        "age_years": "వయస్సు (సంవత్సరాలు)", "issue": "సమస్య", "notes": "గమనికలు",
        "date": "తేదీ", "time": "సమయం",
    },
    "kn": {
        "species": "ಪ್ರಭೇದ", "breed": "ತಳಿ", "sex": "ಲಿಂಗ", "tag_or_name": "ಟ್ಯಾಗ್/ಹೆಸರು",
        "status": "ಸ್ಥಿತಿ", "birth_date": "ಜನನ ದಿನಾಂಕ", "current_location": "ಸ್ಥಳ",
        "age_years": "ವಯಸ್ಸು (ವರ್ಷಗಳು)", "issue": "ಸಮಸ್ಯೆ", "notes": "ಟಿಪ್ಪಣಿಗಳು",
        "date": "ದಿನಾಂಕ", "time": "ಸಮಯ",
    },
    "en": {
        "species": "Species", "breed": "Breed", "sex": "Sex", "tag_or_name": "Tag / Name",
        "status": "Status", "birth_date": "Date of birth", "current_location": "Location",
        "age_years": "Age (years)", "issue": "Issue", "notes": "Notes",
        "date": "Date", "time": "Time",
    },
    "mr": {
        "species": "प्रजाती", "breed": "जात", "sex": "लिंग", "tag_or_name": "टॅग/नाव",
        "status": "स्थिती", "birth_date": "जन्मतारीख", "current_location": "ठिकाण",
        "age_years": "वय (वर्षे)", "issue": "समस्या", "notes": "टिपा",
        "date": "तारीख", "time": "वेळ",
    },
    "ml": {
        "species": "വർഗ്ഗം", "breed": "ഇനം", "sex": "ലിംഗം", "tag_or_name": "ടാഗ്/പേര്",
        "status": "നില", "birth_date": "ജനനത്തീയതി", "current_location": "സ്ഥലം",
        "age_years": "പ്രായം (വർഷം)", "issue": "പ്രശ്നം", "notes": "കുറിപ്പുകൾ",
        "date": "തീയതി", "time": "സമയം",
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
- The database stores species/breed/status and other enum-like values in English only. Regardless of what language the farmer's question is in, any such value used in a WHERE clause must be the English database value, never translated or transliterated -- e.g. a Hindi question about "बकरी" must filter species = 'goat', not species = 'बकरी'.
- The section "Values in this farmer's records" below lists the exact species, breeds and animal names stored for this farmer. Map the farmer's words (in any language or script) to one of those exact values before writing SQL: a local-language species word to its English species value, a breed name to the listed breed spelling, and an animal name written in another script or spelling to the listed name as stored (names are usually stored in Latin capitals). Do not filter on a value that is not in that list; if nothing in the list matches, run a query to check before saying it does not exist.
- The farmer's message may end with a note saying which stored animal a word most likely refers to (found by comparing how the word sounds with the farmer's stored names, in any script). Treat that word as that animal's name and look the animal up -- do not read it as a species or another word that sounds alike. Only if the rest of the message clearly shows the farmer means something else, follow the farmer.
- Farmers often type their own language in English letters (e.g. "bakri", "aadu", "meka", "shelya", "mekegalu"). Treat such a word exactly like the same word in its own script: map an animal-kind word to its stored English species and filter on it. When the farmer asks about one kind of animal, never count or list all animals without that species filter.
- Some animal-kind words can mean more than one stored species (for example Tamil "aadu" / "ஆடு" on its own is used for both goats and sheep). When the farmer uses such a word with nothing saying which kind, do not pick one species yourself and do not list the whole farm: filter on exactly the species that word can mean (e.g. species IN ('goat', 'sheep')) and give each one's count separately (e.g. "you have 10 goats and 4 sheep"). When the word or the rest of the message does say which kind, filter on that one species only.
- When your answer names an animal's species, translate the English database value faithfully into the farmer's language (a buffalo is never a cow, a goat is never a sheep).
- If run_sql_query returns success=false, read the error and try a corrected query -- do not give up after one attempt, and do not repeat the exact same failing query.
- If asking for a single total/count, give just the number in your answer.
- If asking for a breakdown by category, show EACH group with its count -- never summarize or say "ranging from"/"most are" when specific data was requested.
- Otherwise, give a natural conversational answer.
- Never mention SQL, tables, columns, or any technical/database terms in your final answer -- speak like a farm advisor, not a database.
- A bare greeting ("hi", "hello", "hey") with NO real question attached gets a plain greeting back, under 10 words, e.g. "Hi! What would you like to know about your farm?" -- do NOT list your capabilities (animal counts, health records, appointments, etc.) unless the farmer's message actually asked what you can do.
- If the farmer's message contains a greeting word ("hello", "namaste", "hi") ALONGSIDE a real question (e.g. "hello, how many animals do I have"), answer the question directly -- do NOT prepend a greeting/"hello"/"namaste" to the answer. One farmer message, one direct answer; the greeting word was just how they opened their sentence, not a separate thing to reply to.
- Never open an answer with "thank you"/"धन्यवाद" or similar courtesy filler either -- go straight to the answer.
- You are a farm/livestock assistant ONLY -- not a general-purpose chatbot. If the farmer's message has nothing to do with their farm, animals, or records (general knowledge, world facts, other topics entirely), do NOT answer it from your own knowledge even if you know the answer. Say plainly that you can only help with questions about their farm, and ask what they'd like to know about it instead. This applies however confidently you could answer -- being able to answer something is not the same as it being in scope. BUT before deciding a message is off-topic, check the animal names listed under "Values in this farmer's records": if the message mentions one of them (in any script or spelling), it IS a question about the farmer's own animal, even when that name is also an everyday word (a name meaning "king" or "pearl" is still the farmer's animal) -- look it up and answer.

Your answer is shown as text AND read aloud by text-to-speech -- these can differ. The text answer can be as detailed as the question needs (full breakdowns, full lists). The spoken version must always be short, since a farmer listening doesn't want a list of 5+ numbers read out loud one by one.

So: after your full text answer, on its own line, write exactly `---SPOKEN---` followed by a short, spoken-friendly summary of the same answer -- one sentence, no itemized lists, no reading out every number in a breakdown (say "you have 53 animals across 5 species" instead of naming each species and count). If your text answer is already one short sentence, the spoken version can repeat it as-is. Always include the `---SPOKEN---` line, even for a greeting.
{farm_values}"""


# Values block for the prompt (see "Values in this farmer's records" in the
# instruction). Real bugs found by the evals suite (evals/, layer 1): the
# model never saw which values are actually stored, only column names and
# the example "'goat', 'sheep'". So it guessed: Kannada "how many chickens"
# came back "you only have goats and sheep" (3/3 runs), Marathi "how many
# buffaloes" came back 2 or 9 instead of 16, Telugu "గౌరి" never matched the
# stored 'GAURI', and "RAJA कौन सा जानवर है?" was refused as general
# knowledge because nothing told the model RAJA is one of the farmer's own
# animals. Built from the farmer's own rows on every turn (no hardcoded word
# lists), capped so a very large farm can't blow up the prompt, and fully
# skippable via QUERY_AGENT_VALUE_HINTS=0 as a kill switch. The block sits
# at the very END of the instruction, so the long schema + rules part stays
# an identical prefix for every farmer (prompt caching, see the note in
# bedrock_adapter.py, can only reuse an identical prefix).
_VALUE_HINTS_ENV = "QUERY_AGENT_VALUE_HINTS"
_MAX_HINT_NAMES = 150
_MAX_HINT_BREEDS = 60

# The farmer's word for each stored species, given to the model so it names
# the species correctly in its answer. Real bug found by the evals suite:
# asked "LAKSHMI ഏത് മൃഗമാണ്?" the model read species 'buffalo' from the
# database and still answered "...പശുവാണ്" ("is a cow") in 10 of 10 runs; a
# rule saying "translate faithfully" was not enough. Same idea as
# _COLUMN_LABELS above: a fixed catalog keyed by the English database value,
# not an LLM guess. Only used to word the answer -- never to match or filter
# what the farmer typed. A species missing here simply gets no hint (the
# model translates it itself, as before), and English needs none.
_SPECIES_WORDS = {
    "hi": {"goat": "बकरी", "sheep": "भेड़", "buffalo": "भैंस", "cow": "गाय", "chicken": "मुर्गी"},
    "mr": {"goat": "शेळी", "sheep": "मेंढी", "buffalo": "म्हैस", "cow": "गाय", "chicken": "कोंबडी"},
    "ta": {"goat": "வெள்ளாடு", "sheep": "செம்மறி ஆடு", "buffalo": "எருமை", "cow": "பசு", "chicken": "கோழி"},
    "te": {"goat": "మేక", "sheep": "గొర్రె", "buffalo": "గేదె", "cow": "ఆవు", "chicken": "కోడి"},
    "kn": {"goat": "ಮೇಕೆ", "sheep": "ಕುರಿ", "buffalo": "ಎಮ್ಮೆ", "cow": "ಹಸು", "chicken": "ಕೋಳಿ"},
    "ml": {"goat": "ആട്", "sheep": "ചെമ്മരിയാട്", "buffalo": "എരുമ", "cow": "പശു", "chicken": "കോഴി"},
}


def _reply_language(script_lang: str, labels_lang: str) -> str:
    """Language the answer will be written in, for the species words. The
    model answers in the language the farmer typed, so the query's script
    wins; the app's language only decides when the script can't (Roman
    letters look like English, and Devanagari can be Hindi or Marathi)."""
    if script_lang == "en":
        return labels_lang
    if script_lang == "hi" and labels_lang == "mr":
        return "mr"
    return script_lang


def _hint_values(farmer_id: str, sql: str, limit: int) -> "list[str]":
    """Distinct non-empty values from one SELECT, as strings. Any failure
    returns [] so the prompt just loses the hint instead of the turn failing."""
    try:
        result = execute_query(sql, farmer_id)
    except Exception as exc:
        logger.warning("query_agent value hints skipped farmer=%s: %s", farmer_id, exc)
        return []
    if not result.get("success"):
        logger.warning("query_agent value hints skipped farmer=%s: %s", farmer_id, result.get("error"))
        return []
    out: "list[str]" = []
    for row in result.get("rows") or []:
        if not row or row[0] is None:
            continue
        # ADK treats {name} in an instruction as a session-state variable, so
        # a stray brace in stored data must never reach the instruction text.
        value = str(row[0]).strip().replace("{", "").replace("}", "")
        if value and value not in out:
            out.append(value)
        if len(out) >= limit:
            break
    return out


def _farm_values_for_prompt(farmer_id: str, language: "str | None" = None) -> str:
    """'Values in this farmer's records' section of the instruction, or ''
    when disabled or when nothing could be read. `language` (a key of
    _SPECIES_WORDS) adds the farmer's word for each stored species."""
    if os.getenv(_VALUE_HINTS_ENV, "1").strip().lower() in ("0", "false", "no", "off"):
        return ""
    species = _hint_values(
        farmer_id, "SELECT DISTINCT LOWER(species) FROM animals ORDER BY 1", 30)
    breeds = _hint_values(
        farmer_id,
        "SELECT DISTINCT LOWER(species) || ': ' || breed FROM animals "
        "WHERE breed IS NOT NULL AND breed != '' ORDER BY 1",
        _MAX_HINT_BREEDS)
    names = _hint_values(
        farmer_id,
        "SELECT tag_or_name FROM animals WHERE tag_or_name IS NOT NULL "
        f"AND tag_or_name != '' ORDER BY 1 LIMIT {_MAX_HINT_NAMES + 1}",
        _MAX_HINT_NAMES + 1)
    if not (species or breeds or names):
        return ""
    lines = ["", "Values in this farmer's records (exact stored spellings):"]
    if species:
        lines.append("- species: " + ", ".join(species))
        words = _SPECIES_WORDS.get(language or "", {})
        pairs = [f"{s} = {words[s]}" for s in species if s in words]
        if pairs:
            lines.append(
                "- when your answer names a species, use exactly these words for it "
                "(for a male animal, the male word if the language has one): "
                + "; ".join(pairs))
    if breeds:
        lines.append("- breeds (species: breed): " + "; ".join(breeds))
    if names:
        more = len(names) > _MAX_HINT_NAMES
        shown = names[:_MAX_HINT_NAMES]
        lines.append("- animal names/tags: " + ", ".join(shown)
                     + (" (more exist; query to check others)" if more else ""))
    return "\n".join(lines) + "\n"


# Name notes for the farmer's message. Farmers type an animal's name in
# their own script and spelling (गोरी, గౌరి, கௌரி for a stored "GAURI"), and
# the model, even with the names listed above, often fails to connect them
# -- it may read the name as a similar-sounding word (a species) or answer
# that no such animal exists. Each word of the message is compared with the
# farmer's own stored names by sound (services/common/name_match.py); a
# confident match is added as a short note at the end of the message. No
# model call, no word lists. QUERY_AGENT_NAME_HINTS=0 turns it off.
_NAME_HINTS_ENV = "QUERY_AGENT_NAME_HINTS"
_MAX_NAME_NOTES = 3
# One row (group_concat) so the result is not cut at db._MAX_ROWS.
_ALL_NAMES_SQL = (
    "SELECT group_concat(tag_or_name, char(10)) FROM "
    "(SELECT DISTINCT tag_or_name FROM animals "
    "WHERE tag_or_name IS NOT NULL AND tag_or_name != '')"
)


def _stored_animal_names(farmer_id: str) -> "list[str]":
    """All of this farmer's animal names/tags. [] if they can't be read."""
    try:
        result = execute_query(_ALL_NAMES_SQL, farmer_id)
    except Exception as exc:
        logger.warning("query_agent name notes skipped farmer=%s: %s", farmer_id, exc)
        return []
    if not result.get("success"):
        logger.warning("query_agent name notes skipped farmer=%s: %s", farmer_id, result.get("error"))
        return []
    rows = result.get("rows") or []
    joined = rows[0][0] if rows and rows[0] else None
    return [n.strip() for n in str(joined or "").split("\n") if n.strip()]


def _with_name_notes(query: str, farmer_id: str) -> str:
    """`query` plus a note for each word that most likely names one of the
    farmer's animals, or `query` unchanged when nothing matches, the store
    can't be read, or the feature is turned off."""
    if os.getenv(_NAME_HINTS_ENV, "1").strip().lower() in ("0", "false", "no", "off"):
        return query
    names = _stored_animal_names(farmer_id)
    if not names:
        return query
    mentions = find_name_mentions(query, names)[:_MAX_NAME_NOTES]
    if not mentions:
        return query
    logger.info(
        "query_agent name notes farmer=%s %s", farmer_id,
        ", ".join(f"{m.word!r}->{m.name} ({m.score})" for m in mentions),
    )
    notes = "; ".join(f'"{m.word}" most likely means the farmer\'s animal {m.name}' for m in mentions)
    return f"{query}\n\n(Note: {notes}.)"


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


def build_query_agent(farmer_id: str, language: "str | None" = None) -> LlmAgent:
    """One Agent per farmer_id -- farmer_id is baked into the tool closure
    above, not passed through the model, so no prompt can ever redirect a
    query at a different farmer's data. `language` is the answer's language
    (see _reply_language); it only adds the species words to the prompt."""
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
        instruction=_INSTRUCTION_TEMPLATE.format(
            schema=schema, farm_values=_farm_values_for_prompt(farmer_id, language)),
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


async def _run_query_async(
    query: str,
    farmer_id: str,
    session_id: str | None = None,
    app_language: str | None = None,
) -> dict[str, Any]:
    lang = detect_language(query)
    labels_lang = _labels_language(lang, app_language)
    agent = build_query_agent(farmer_id, _reply_language(lang, labels_lang))
    service = _session_service()
    runner = Runner(agent=agent, app_name=_APP_NAME, session_service=service)
    user_id = f"farmer-{farmer_id}"
    session = await _get_or_create_session(service, user_id, session_id)
    message = types.Content(role="user", parts=[types.Part(text=_with_name_notes(query, farmer_id))])

    answer_text: str | None = None
    last_successful_result: dict[str, Any] | None = None

    try:
        async for event in runner.run_async(
            user_id=user_id, session_id=session.id, new_message=message,
            run_config=RunConfig(max_llm_calls=_MAX_LLM_CALLS),
        ):
            for fr in event.get_function_responses():
                if fr.name == "run_sql_query" and isinstance(fr.response, dict) and fr.response.get("success"):
                    last_successful_result = fr.response
            if event.is_final_response() and event.content and event.content.parts:
                answer_text = "".join(p.text for p in event.content.parts if p.text)
    except LlmCallsLimitExceededError:
        fallback = "I encountered an error trying to answer that. Please try rephrasing your question."
        return {"answer": fallback, "sql": None, "data": None, "speech_text": fallback}

    if not answer_text:
        return {"answer": "I couldn't understand the query. Please rephrase.", "sql": None, "data": None, "speech_text": "I couldn't understand the query. Please rephrase."}

    text_answer, speech_text = _split_text_and_speech(answer_text)

    text_answer, speech_text = _localize_answer_digits(text_answer, speech_text, labels_lang)

    if last_successful_result is None:
        return {"answer": text_answer, "sql": None, "data": None, "speech_text": speech_text}

    # Raw data payload stays machine-readable (English column identifiers,
    # native int/float scalars, tag/ID/date strings unchanged) -- reviewers
    # found the previous always-translate behavior corrupted IDs and dates
    # so they no longer round-tripped to the DB. Localized copies for UI
    # display live in data["display"], keyed the same way, so the frontend
    # can pick one or the other without ambiguity.
    raw_data = {
        "columns": last_successful_result.get("columns"),
        "rows": last_successful_result.get("rows"),
        "row_count": last_successful_result.get("row_count"),
        "truncated": last_successful_result.get("truncated", False),
    }
    # Headings and row digits both follow labels_lang (computed above,
    # now also used for the text/speech answer's digits) so the whole
    # response is internally consistent in one language -- not "English
    # headings over Devanagari digits" when the app's language and the
    # query's script differ (found in deep-review of PR #41).
    if labels_lang in _COLUMN_LABELS:
        raw_data["display"] = {
            "columns": _localize_columns(raw_data["columns"], labels_lang),
            "rows": _localize_numbers(raw_data["rows"], labels_lang),
        }
    return {
        "answer": text_answer,
        "sql": last_successful_result.get("sql"),
        "data": raw_data,
        "speech_text": speech_text,
    }


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
