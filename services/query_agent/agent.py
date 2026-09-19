import json
import re
from typing import Any

from services.llm_service.bedrock_adapter import BedrockTextAdapter, TaskTier
from services.query_agent.db import execute_query, validate_sql
from services.query_agent.schema import generate_schema_for_prompt

_SQL_SYSTEM = """You are a livestock data analyst. Generate SQLite SQL queries from farmer questions.

SMART QUERY RULES:
- "how many animals" (total) → SELECT COUNT(*) FROM animals
- "animals by age" / "age distribution" / "for each age" / "count by" → SELECT age_years, COUNT(*) FROM animals WHERE age_years IS NOT NULL GROUP BY age_years ORDER BY age_years
- "by category" / "grouped by" / "per" → use GROUP BY
- "list all" / "show me" → SELECT without GROUP BY

General Rules:
- Return ONLY valid SQL, no markdown or explanation
- Use COUNT(*) when counting
- Use GROUP BY when farmer wants breakdown by category
- Use ORDER BY for listing/sorting
- Return only the SQL query text"""

_FORMAT_SYSTEM = """You are a livestock data assistant. Analyze the farmer's question and data, then present it intelligently.

DECISION TREE:
1. If asking for a SINGLE total → give just the number
   Example: "How many animals?" → "You have 38 animals."

2. If asking for BREAKDOWN by category (ages, groups, types) → show EACH group
   Examples: "age distribution", "by age", "for each", "list all ages", "show by category"
   Format: List each group with its count, one per line
   Example: Age 0.7: 1 animal, Age 1.2: 3 animals, Age 1.7: 4 animals...

3. Other questions → conversational answer

NEVER use vague summaries when specific data was requested."""


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


def _format_result(query: str, result: dict, schema: str, adapter: BedrockTextAdapter) -> str:
    """Format query result based on what user asked for."""
    data_str = json.dumps(result, indent=2, default=str)
    
    # Simple instruction - let LLM decide based on context
    prompt = f"""Database schema:

{schema}

Farmer asked: "{query}"

Query result:
{data_str}

Instructions:
- If asking for total/count only → give just the number
- If asking for breakdown by category → show EACH group with count (list format)
- Otherwise → conversational answer

Give a clear answer:"""
    try:
        return adapter.complete(messages=[{"role": "user", "content": prompt}], system=_FORMAT_SYSTEM).strip()
    except Exception:
        return "I found the data but had trouble putting it into words. Please try asking again."


MAX_RETRIES = 2


def process_query(query: str, farmer_id: str) -> dict[str, Any]:
    """
    Main entry point. Takes a natural language query and farmer_id,
    generates SQL, executes it, and returns a natural language answer.
    """
    schema = generate_schema_for_prompt()
    adapter = BedrockTextAdapter(task=TaskTier.GENERATION)

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
            answer = _format_result(query, result, schema, adapter)
            response = {
                "answer": answer,
                "sql": result.get("sql"),
                "data": {
                    "columns": result.get("columns"),
                    "rows": result.get("rows"),
                    "row_count": result.get("row_count"),
                    "truncated": result.get("truncated", False),
                },
            }
            
            # Smart detection: SQL with GROUP BY indicates structured/breakdown data
            sql_upper = (result.get("sql") or "").upper()
            has_group_by = "GROUP BY" in sql_upper
            has_multiple_rows = len(result.get("rows", [])) > 1
            
            if has_group_by and has_multiple_rows:
                response["display_mode"] = "structured"
                response["title"] = query.strip(".?").capitalize()
            
            return response

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
