import json
import re
from typing import Any

from services.llm_service.bedrock_adapter import BedrockTextAdapter
from services.query_agent.db import execute_query, validate_sql
from services.query_agent.schema import generate_schema_for_prompt

_SQL_SYSTEM = """You are a livestock data analyst. Given a farmer's natural language question and a database schema, you generate SQLite SQL queries.

Rules:
- Return ONLY valid SQL. No markdown, no backticks, no explanation.
- The query MUST be a single SELECT statement.
- Use SQLite-compatible syntax.
- When counting, use COUNT(*).
- When filtering text, use LIKE with lowercase (SQLite is case-sensitive by default, so use LOWER() for case-insensitive matching).
- Use single quotes for string literals (double quotes for identifiers).
- Do NOT use LIMIT unless the question asks for a specific number.
- Use column names exactly as shown in the schema.
- Join tables using the foreign key relationships described in the schema.
- Return only the SQL query text, nothing else."""

_FORMAT_SYSTEM = """You are a livestock data assistant. Format query results into a clear, conversational answer for a farmer.

Rules:
- Keep it short, 1-3 sentences.
- Use the farmer's language naturally.
- If the result is a count, say "You have N animals" or similar.
- If the result is a list, summarize the key items.
- Do NOT mention SQL, columns, or technical details.
- If there are no results, say so simply.
- Return only the answer text, nothing else."""


def _generate_sql(query: str, farmer_id: str, schema: str, adapter: BedrockTextAdapter) -> str:
    prompt = f"""Database schema for a livestock farm management system:

{schema}

Farmer context:
- farmer_id = '{farmer_id}'
- Tables with farmer_id are automatically scoped to this farmer. Do NOT add farmer_id in your WHERE clause.

Farmer question: "{query}"

Generate a SQLite SQL query to answer this question."""
    try:
        raw = adapter.complete(messages=[{"role": "user", "content": prompt}], system=_SQL_SYSTEM)
        sql = raw.strip()
        sql = re.sub(r"^```(sql)?\s*", "", sql, flags=re.IGNORECASE)
        sql = re.sub(r"\s*```$", "", sql)
        return sql.strip()
    except Exception:
        return ""


def _format_result(query: str, result: dict, adapter: BedrockTextAdapter) -> str:
    data_str = json.dumps(result, indent=2, default=str)
    prompt = f"""Farmer asked: "{query}"

Query result:
{data_str}

Give a short, clear answer in natural language."""
    try:
        raw = adapter.complete(messages=[{"role": "user", "content": prompt}], system=_FORMAT_SYSTEM)
        return raw.strip()
    except Exception:
        rows = result.get("rows", [])
        if rows:
            return f"Found {len(rows)} result(s)."
        return "No results found."


MAX_RETRIES = 2


def process_query(query: str, farmer_id: str) -> dict[str, Any]:
    """
    Main entry point. Takes a natural language query and farmer_id,
    generates SQL, executes it, and returns a natural language answer.
    """
    schema = generate_schema_for_prompt()
    adapter = BedrockTextAdapter()

    sql = _generate_sql(query, farmer_id, schema, adapter)
    if not sql:
        return {"answer": "I couldn't understand the query. Please rephrase.", "sql": None, "data": None}

    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            result = execute_query(sql, farmer_id)
        except ValueError as e:
            return {"answer": str(e), "sql": sql, "data": None}

        if result.get("success"):
            answer = _format_result(query, result, adapter)
            return {
                "answer": answer,
                "sql": result.get("sql"),
                "data": {
                    "columns": result.get("columns"),
                    "rows": result.get("rows"),
                    "row_count": result.get("row_count"),
                    "truncated": result.get("truncated", False),
                },
            }

        last_error = result.get("error", "Unknown error")

        if attempt < MAX_RETRIES - 1:
            prompt = f"""The previous SQL query failed with error: {last_error}

Original question: "{query}"
Failed SQL: {sql}

Schema:
{schema}

Generate a corrected SQLite SQL query that fixes the error."""
            try:
                raw = adapter.complete(
                    messages=[{"role": "user", "content": prompt}],
                    system=_SQL_SYSTEM,
                )
                sql = raw.strip()
                sql = re.sub(r"^```(sql)?\s*", "", sql, flags=re.IGNORECASE)
                sql = re.sub(r"\s*```$", "", sql)
            except Exception:
                break

    return {
        "answer": f"I encountered an error: {last_error}",
        "sql": sql,
        "data": None,
    }
