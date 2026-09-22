"""ADK-native rebuild of query_agent's orchestration.
Supported languages (matching UI): English, Hindi, Kannada, Telugu, Tamil, Malayalam.
No Marathi.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any

from google.adk import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import InMemoryRunner
from google.genai import types

from services.llm_service.bedrock_adapter import TaskTier, model_for_task
from services.query_agent.db import execute_query
from services.query_agent.schema import generate_schema_for_prompt

_INSTRUCTION_TEMPLATE = """You are a livestock data analyst answering one farmer's questions about \
their own farm records.

Database schema:
{schema}

Rules:
- Use the run_sql_query tool to answer. Never answer from memory/guesswork.
- The query MUST be a single SQLite SELECT statement.
- Use COUNT(*) when counting; GROUP BY when the farmer wants a breakdown by category; ORDER BY for listing/sorting.
- Use LOWER() for case-insensitive text filtering.
- CRITICAL DATABASE MATCHING RULE: The database stores species names strictly in English lowercase (e.g., 'cow', 'goat', 'chicken', 'buffalo', 'sheep'). Regardless of the input language (Hindi, Kannada, Telugu, Tamil, Malayalam), ALWAYS translate non-English animal/species names to their exact English equivalents in SQL filters. NEVER put non-English text inside SQL WHERE string comparisons!
- NEVER ask the farmer for their farmer_id or tenant ID! You already have full access to their scoped farm database automatically via your tool.
- If run_sql_query returns success=false, read the error carefully and try a corrected query.

CRITICAL LANGUAGE & FORMATTING RULES:
- Always respond in the EXACT language requested by the user.
- Keep your text reply brief and conversational. DO NOT output long formatted text lists or tables in your text answer if run_sql_query returns structured rows, as the frontend will render the result table automatically.
- Your answer is shown as text AND read aloud by text-to-speech -- these can differ.
- After your short text answer, on its own line, write exactly `---SPOKEN---` followed by a short, spoken-friendly summary."""

LANG_NAMES = {
    "hi": "Hindi",
    "kn": "Kannada",
    "ta": "Tamil",
    "te": "Telugu",
    "ml": "Malayalam",
    "en": "English",
}

# Native numeral systems for full localization of numbers
NATIVE_DIGITS = {
    "hi": "०१२३४५६७८९",   # Devanagari (Hindi)
    "ta": "௦௧௨௩௪௫௬௭௮௯",   # Tamil
    "te": "౦౧౨౩౪౫౬౭౮౯",   # Telugu
    "kn": "೦೧೨೩೪೫೬೭೮೯",   # Kannada
    "ml": "൦൧൨൩൪൫൬൭൮൯",   # Malayalam
    "en": "0123456789",
}


def detect_language(text: str) -> str:
    """Detect language from Unicode script. Only languages present in UI."""
    if re.search(r"[\u0900-\u097F]", text):          # Devanagari → Hindi
        return "hi"
    if re.search(r"[\u0C80-\u0CFF]", text):          # Kannada
        return "kn"
    if re.search(r"[\u0B80-\u0BFF]", text):          # Tamil
        return "ta"
    if re.search(r"[\u0C00-\u0C7F]", text):          # Telugu
        return "te"
    if re.search(r"[\u0D00-\u0D7F]", text):          # Malayalam
        return "ml"
    return "en"


def _to_native_digits(text: str, lang_code: str) -> str:
    """Convert every Western digit (0-9) to the native numeral of the target language."""
    if not isinstance(text, str) or lang_code == "en":
        return text
    digits = NATIVE_DIGITS.get(lang_code)
    if not digits:
        return text
    return text.translate(str.maketrans("0123456789", digits))


def _localize_numbers(obj: Any, lang_code: str) -> Any:
    """
    Recursively convert:
    - All digit sequences inside strings → native numerals
    - Pure int / float values → native-digit strings
    """
    if lang_code == "en":
        return obj

    if isinstance(obj, str):
        return _to_native_digits(obj, lang_code)

    if isinstance(obj, (int, float)) and not isinstance(obj, bool):
        return _to_native_digits(str(obj), lang_code)

    if isinstance(obj, dict):
        return {k: _localize_numbers(v, lang_code) for k, v in obj.items()}

    if isinstance(obj, list):
        return [_localize_numbers(item, lang_code) for item in obj]

    return obj


def _flatten_cell(val: Any) -> Any:
    if not isinstance(val, str):
        return val
    v_str = val.strip()
    if not (v_str.startswith("{") and v_str.endswith("}")):
        return val
    try:
        parsed = json.loads(v_str)
        if not isinstance(parsed, dict):
            return val
        parts = []
        for k, v in parsed.items():
            if v is None or v == [] or v == "":
                continue
            if isinstance(v, list):
                v_text = ", ".join(str(i) for i in v if i is not None)
            else:
                v_text = str(v)
            if v_text:
                parts.append(f"{k}: {v_text}")
        return " | ".join(parts) if parts else "—"
    except Exception:
        return val


def _flatten_table_payload(data: dict[str, Any] | None) -> dict[str, Any] | None:
    if not data or "rows" not in data:
        return data
    clean_rows = []
    for row in data.get("rows", []):
        if isinstance(row, dict):
            clean_rows.append({k: _flatten_cell(v) for k, v in row.items()})
        elif isinstance(row, (list, tuple)):
            clean_rows.append([_flatten_cell(item) for item in row])
        else:
            clean_rows.append(row)
    return {
        "columns": data.get("columns"),
        "rows": clean_rows,
        "row_count": data.get("row_count"),
        "truncated": data.get("truncated", False),
    }


async def _localize_table_data_with_llm(
    data: dict[str, Any] | None, lang_code: str, max_attempts: int = 1
) -> dict[str, Any] | None:
    if not data or lang_code == "en":
        return data

    flat_data = _flatten_table_payload(data)
    target_lang = LANG_NAMES.get(lang_code, "Hindi")
    model_spec = model_for_task(TaskTier.GENERATION)

    translator = Agent(
        name="json_table_translator",
        description="Translates SQL JSON table payload to target language.",
        model=LiteLlm(model=f"bedrock/{model_spec['id']}", temperature=0.0),
        instruction=f"""You are a strict JSON payload translator for a farm management web UI table.

YOUR TASK:
1. Receive a JSON object containing 'columns' and 'rows'.
2. Translate ALL column header strings into {target_lang}.
3. Translate ALL cell string values inside rows strictly into {target_lang}.
4. DO NOT translate tag IDs, timestamps/dates, numbers, or null values.
5. Return ONLY valid JSON with exact structure: {{"columns": [...], "rows": [...], "row_count": ..., "truncated": ...}}.
6. DO NOT wrap in markdown codeblocks.""",
    )

    try:
        runner = InMemoryRunner(agent=translator, app_name="table_translator")
        session = await runner.session_service.create_session(
            app_name="table_translator", user_id="system"
        )
        msg = types.Content(
            role="user", parts=[types.Part(text=json.dumps(flat_data, ensure_ascii=False))]
        )

        res_text = ""
        async for event in runner.run_async(
            user_id="system", session_id=session.id, new_message=msg
        ):
            if event.is_final_response() and event.content and event.content.parts:
                res_text = "".join(p.text for p in event.content.parts if p.text)

        clean_json = res_text.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(clean_json)
        if isinstance(parsed, dict) and "columns" in parsed and "rows" in parsed:
            return _localize_numbers(parsed, lang_code)
    except Exception as exc:
        print(f"[WARNING] Table localization failed/skipped: {exc}")

    # Fallback: flatten and strictly convert numbers to target language digits
    return _localize_numbers(flat_data, lang_code)


def _make_run_sql_query_tool(farmer_id: str):
    def run_sql_query(sql: str) -> dict[str, Any]:
        try:
            print(f"[DEBUG SQL EXECUTING] farmer_id={farmer_id} | sql={sql}")
            res = execute_query(sql, farmer_id)
            print(f"[DEBUG SQL RESULT] success={res.get('success')} | rows={res.get('row_count')}")
            return res
        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {str(exc)}"
            print(f"[DEBUG SQL ERROR] farmer_id={farmer_id} | error={error_msg}")
            return {"success": False, "error": error_msg, "sql": sql}

    return run_sql_query


def build_query_agent(farmer_id: str) -> Agent:
    model_spec = model_for_task(TaskTier.GENERATION)
    schema = generate_schema_for_prompt()
    return Agent(
        name="query_agent",
        description="Answers a farmer's questions about their own livestock data.",
        model=LiteLlm(
            model=f"bedrock/{model_spec['id']}", temperature=model_spec["temperature"]
        ),
        instruction=_INSTRUCTION_TEMPLATE.format(schema=schema),
        tools=[_make_run_sql_query_tool(farmer_id)],
    )


_SPOKEN_MARKER = "---SPOKEN---"


def _split_text_and_speech(answer_text: str) -> tuple[str, str]:
    if _SPOKEN_MARKER in answer_text:
        text_part, _, speech_part = answer_text.partition(_SPOKEN_MARKER)
        return text_part.strip(), (speech_part.strip() or text_part.strip())
    return answer_text, answer_text


async def _run_query_async(query: str, farmer_id: str) -> dict[str, Any]:
    start_time = time.time()

    agent = build_query_agent(farmer_id)
    runner = InMemoryRunner(agent=agent, app_name="farmer_chat_query_agent")
    user_id = f"farmer-{farmer_id}"
    session = await runner.session_service.create_session(
        app_name="farmer_chat_query_agent", user_id=user_id
    )
    message = types.Content(role="user", parts=[types.Part(text=query)])

    answer_text: str | None = None
    last_successful_result: dict[str, Any] | None = None
    last_error_result: dict[str, Any] | None = None

    try:
        async for event in runner.run_async(
            user_id=user_id, session_id=session.id, new_message=message
        ):
            for fr in event.get_function_responses():
                if fr.name == "run_sql_query" and isinstance(fr.response, dict):
                    if fr.response.get("success"):
                        last_successful_result = fr.response
                    else:
                        last_error_result = fr.response
            if event.is_final_response() and event.content and event.content.parts:
                parts_text = "".join(p.text for p in event.content.parts if p.text)
                if parts_text.strip():
                    answer_text = parts_text
    except Exception as exc:
        print(f"[ERROR] ADK execution exception: {exc}")

    elapsed_ms = int((time.time() - start_time) * 1000)
    lang_code = detect_language(query)

    if last_successful_result and not answer_text:
        answer_text = "आपके फार्म का विवरण नीचे तालिका में दिया गया है।"

    if not answer_text and not last_successful_result:
        fallback = "क्षमा करें, अभी मेरे पास इसका उत्तर नहीं है।"
        return {
            "agent": "query_agent",
            "intent": "query",
            "reply_text": fallback,
            "speech_text": fallback,
            "result": None,
            "sql": None,
            "timing": {"total_ms": elapsed_ms},
        }

    text_answer, speech_text = _split_text_and_speech(answer_text)

    # Localize text answer numbers as well
    text_answer = _localize_numbers(text_answer, lang_code)
    speech_text = _localize_numbers(speech_text, lang_code)

    if last_successful_result is None:
        return {
            "agent": "query_agent",
            "intent": "query",
            "reply_text": text_answer,
            "speech_text": speech_text,
            "result": None,
            "sql": last_error_result.get("sql") if last_error_result else None,
            "timing": {"total_ms": elapsed_ms},
        }

    raw_data = {
        "columns": last_successful_result.get("columns"),
        "rows": last_successful_result.get("rows"),
        "row_count": last_successful_result.get("row_count"),
        "truncated": last_successful_result.get("truncated", False),
    }

    try:
        localized_data = await _localize_table_data_with_llm(raw_data, lang_code)
    except Exception as exc:
        flat_data = _flatten_table_payload(raw_data)
        localized_data = _localize_numbers(flat_data, lang_code)

    return {
        "agent": "query_agent",
        "intent": "query",
        "reply_text": text_answer,
        "speech_text": speech_text,
        "result": localized_data,
        "sql": last_successful_result.get("sql"),
        "timing": {"total_ms": elapsed_ms},
    }


def process_query_adk(query: str, farmer_id: str) -> dict[str, Any]:
    return asyncio.run(_run_query_async(query, farmer_id))