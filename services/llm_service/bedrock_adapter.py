import os
import json
import boto3


class BedrockTextAdapter:
    def __init__(self):
        self.client = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION", "us-east-1"))
        self.model_id = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-sonnet-20240229-v1:0")

    def complete(self, messages, system=None):
        prompt = ""
        if system:
            prompt += f"System: {system}\n"
        for m in messages:
            prompt += f"{m['role'].capitalize()}: {m['content']}\n"
        prompt += "Assistant:"

        # Anthropic models via invoke_model
        if self.model_id.startswith("anthropic."):
            body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 512,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
            }
            resp = self.client.invoke_model(
                modelId=self.model_id,
                body=json.dumps(body),
            )
            out = json.loads(resp["body"].read())
            return out.get("content", [{"text": ""}])[0]["text"]

        # Non-anthropic models via Converse API
        req = {
            "modelId": self.model_id,
            "messages": [
                {
                    "role": "user",
                    "content": [{"text": prompt}],
                }
            ],
            "inferenceConfig": {
                "maxTokens": 512,
                "temperature": 0,
            },
        }
        if system:
            req["system"] = [{"text": system}]

        resp = self.client.converse(**req)
        content = resp.get("output", {}).get("message", {}).get("content", [])
        if content and isinstance(content, list):
            return content[0].get("text", "")
        return ""


# ---- Voice Extraction Wrapper ----
_SYSTEM_PROMPT = (
    "You are an information extraction system for a livestock app.\n"
    "Return ONLY valid JSON. No backticks. No markdown. No preamble. No trailing text.\n"
    "The response MUST be a single JSON object with EXACT keys: intent, entities, confidence.\n"
    "- intent: one of [CREATE_ANIMAL, UPDATE_ANIMAL, LOG_HEALTH, CREATE_APPOINTMENT] or null\n"
    "- entities: a JSON object (can be empty)\n"
    "- confidence: number between 0 and 1\n"
    "If information is missing, leave fields null or empty; do not invent values."
)

def build_prompt(text: str) -> str:
    # Conversational extraction with missing fields + follow-ups
    return f"""
You are an AI assistant for a livestock management system.

User said:
"{text}"

Your job:
1. Identify intent
2. Extract entities
3. Identify missing required fields
4. Suggest follow-up questions

Intents:
- CREATE_ANIMAL
- UPDATE_ANIMAL
- LOG_HEALTH
- CREATE_APPOINTMENT
- null

Return ONLY valid JSON (no extra text):
{{
  "intent": "...",
  "entities": {{}},
  "missing_fields": [],
  "follow_up_questions": [],
  "confidence": 0.0
}}
"""


def _safe_json_parse(s: str):
    s = s.strip()
    # Remove code fences like ```json ... ```
    if "```" in s:
        parts = s.split("```")
        # pick the largest chunk that likely contains JSON
        s = max(parts, key=len).strip()
        if s.startswith("json"):
            s = s[4:].strip()
    # Try direct parse
    try:
        return json.loads(s)
    except Exception:
        pass

    # If no braces at all but contains intent key, wrap whole string
    if '{' not in s and '"intent"' in s:
        try:
            candidate = '{' + s.strip().strip(',') + '}'
            return json.loads(candidate)
        except Exception:
            pass

    # Handle case where model returns key-values without outer braces
    if s.startswith('"intent"') or s.startswith("'intent'") or '"intent"' in s:
        try:
            candidate = '{' + s + '}'
            return json.loads(candidate)
        except Exception:
            pass

    # Aggressive extraction: find first valid JSON object
    start = s.find("{")
    while start != -1:
        end = s.rfind("}")
        if end == -1 or end <= start:
            break
        candidate = s[start:end+1]
        try:
            return json.loads(candidate)
        except Exception:
            start = s.find("{", start + 1)
            continue

    # Fallback
    return {
        "intent": None,
        "entities": {},
        "confidence": 0.0,
        "_raw": s,
    }


def call_bedrock(text: str):
    adapter = BedrockTextAdapter()

    messages = [
        {"role": "user", "content": build_prompt(text)}
    ]

    raw = adapter.complete(messages=messages, system=_SYSTEM_PROMPT)

    parsed = _safe_json_parse(raw)

    # Ensure shape
    return {
        "intent": parsed.get("intent"),
        "entities": parsed.get("entities", {}),
        "confidence": float(parsed.get("confidence", 0.0) or 0.0),
        "_raw": raw,
    }
