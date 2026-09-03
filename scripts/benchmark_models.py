"""Benchmark Bedrock models for extraction latency + quality.

Run on the server (needs AWS creds + bedrock access):
    python3 scripts/benchmark_models.py

Tests each candidate model against code-mixed farmer utterances,
measures p50/p95 latency, and validates the JSON extraction shape.
"""
import json
import os
import statistics
import time

import boto3
from botocore.config import Config

REGION = os.getenv("AWS_REGION", "ap-south-1")
MODELS = [
    "mistral.mistral-large-3-675b-instruct",
    # add candidates available in ap-south-1, e.g.:
    # "mistral.mistral-7b-instruct-v0.2",
    # "meta.llama3-8b-instruct-v1:0",
    # "cohere.command-r-v1:0",
]

SAMPLES = [
    "My goat Lakshmi is not eating since 2 days, book appointment tomorrow 10am",
    "मेरी भेड़ सीमा को बुखार है, कल डॉक्टर का अपॉइंटमेंट बुक करो",
    "tag 1234 walе bakri ko lag hai, day after tomorrow sham ko vet dikhana hai",
    "Lakshmi has fever and swelling, severe, 3 days",
    "எனது ஆட்டிற்கு காய்ச்சல், நாளை மாலை 5 மணி சிகிச்சை",
]

REQUIRED_KEYS = {"intent", "entities", "missing_fields", "follow_up_questions", "confidence"}
ENTITY_KEYS = {"animal_name", "issue", "date", "time", "symptoms", "duration", "severity"}

SYSTEM = (
    "Extract livestock vet info from farmer voice (Hindi/Tamil/Telugu/Kannada/English). "
    "Return ONLY JSON with keys: intent, entities, missing_fields, follow_up_questions, confidence. "
    "intent: WEATHER_ALERT|FETCH_ANIMAL_DETAILS|CREATE_ANIMAL|UPDATE_ANIMAL|LOG_HEALTH|CREATE_APPOINTMENT|null. "
    "entities keys: animal_name, animal_tag, animal_identifier, issue, symptoms[], duration, severity, date, time. "
    "Translate issue/symptoms to English. Keep animal_name in original script. "
    "मतलब is filler, NOT an animal name. "
    "If info missing, use null. Do not invent values."
)


def build_prompt(text: str) -> str:
    from datetime import datetime, timedelta, timezone
    today = datetime.now(timezone.utc).date()
    tomorrow = (today + timedelta(days=1)).isoformat()
    return f'User: "{text}"\nContext: intent=null entities={{}} pending=[]\nToday: {today.isoformat()} Tomorrow: {tomorrow}\nExtract intent+entities. Return ONLY JSON.'


def run_model(client, model_id: str):
    results = []
    for text in SAMPLES:
        t0 = time.time()
        try:
            resp = client.converse(
                modelId=model_id,
                system=[{"text": SYSTEM}],
                messages=[{"role": "user", "content": [{"text": build_prompt(text)}]}],
                inferenceConfig={"maxTokens": 256, "temperature": 0},
            )
            ms = (time.time() - t0) * 1000
            raw = resp["output"]["message"]["content"][0]["text"]
            parsed = json.loads(raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip())
            valid_keys = REQUIRED_KEYS.issubset(parsed.keys())
            entities = parsed.get("entities") or {}
            entity_hits = sum(1 for k in ENTITY_KEYS if entities.get(k))
            results.append({
                "ms": ms,
                "ok": valid_keys,
                "entity_hits": entity_hits,
                "intent": parsed.get("intent"),
            })
        except Exception as exc:
            results.append({"ms": (time.time() - t0) * 1000, "ok": False, "error": str(exc)[:120]})
    return results


def main():
    client = boto3.client(
        "bedrock-runtime",
        region_name=REGION,
        config=Config(connect_timeout=2, read_timeout=30, retries={"max_attempts": 2}),
    )
    for model_id in MODELS:
        rows = run_model(client, model_id)
        lat = [r["ms"] for r in rows]
        ok = sum(1 for r in rows if r.get("ok"))
        hits = sum(r.get("entity_hits", 0) for r in rows)
        print(f"\n=== {model_id} ===")
        print(f"  valid JSON : {ok}/{len(rows)}")
        print(f"  entity hits: {hits}/{len(rows) * len(ENTITY_KEYS)}")
        if lat:
            print(f"  latency    : p50={statistics.median(lat):.0f}ms max={max(lat):.0f}ms avg={statistics.mean(lat):.0f}ms")
        for r in rows:
            if "error" in r:
                print(f"  ERROR: {r['error']}")


if __name__ == "__main__":
    main()
