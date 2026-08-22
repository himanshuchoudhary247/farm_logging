#!/usr/bin/env python3
"""Test Qwen with all 5 Indic languages."""
import boto3
import json
import time

c = boto3.client("bedrock-runtime", region_name="ap-south-1")

tests = [
    {"lang": "Hindi", "text": "पशु का नाम है सीमा, खाना नहीं खा रही है और कल अपॉइंटमेंट चाहिए"},
    {"lang": "Tamil", "text": "இதன் பெயர் செல்வி, சாப்பிடவில்லை காய்ச்சல் உள்ளது, நாளை காலை 10 மணி சந்திப்பு வேண்டும்"},
    {"lang": "Telugu", "text": "దీని పేరు లక్ష్మి, తినడం లేదు, నీరసంగా ఉంది, రేపు ఉదయం 10 గంటలకు అపాయింట్ కావాలి"},
    {"lang": "Kannada", "text": "ಇದರ ಹೆಸರು ಗೌರಿ, ತಿನ್ನುತ್ತಿಲ್ಲ, ಜ್ವರ ಬಂದಿದೆ, ನಾಳೆ ಬೆಳಗ್ಗೆ 10 ಗಂಟೆ ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ಬೇಕು"},
    {"lang": "Hindi-code-mixed", "text": "पशु का नाम है मतलब टैग है मेरे पास वन टू थ्री फोर और उसको भूख नहीं लग रही है वो खाना नहीं खा रहा है"},
]

prompt_template = """Extract structured entities from this {lang} farmer voice transcription. The text may contain filler words and code-mixed English words.
Text: {text}

Return ONLY valid JSON (no backticks, no markdown):
{{
  "intent": "CREATE_APPOINTMENT or LOG_HEALTH or null",
  "entities": {{
    "animal_name": "actual animal name or null if not given",
    "animal_tag": "tag number as digits or null",
    "animal_identifier": "name or tag-XXXX",
    "issue": "primary issue in English",
    "symptoms": ["list of symptoms in English"],
    "duration": "e.g. 2 days or null",
    "severity": "mild/moderate/severe or null",
    "date": "YYYY-MM-DD or null",
    "time": "HH:MM or null"
  }},
  "missing_fields": ["list of missing required fields"],
  "confidence": 0.0
}}

IMPORTANT: "मतलब" is a filler word meaning "that is", NOT an animal name.
If tomorrow/नाळै/रेपु/ನಾಳೆ/कल is mentioned, set date to tomorrow's date: 2026-08-21.
"""

model = "qwen.qwen3-32b-v1:0"

for test in tests:
    prompt = prompt_template.format(lang=test["lang"], text=test["text"])
    body = {
        "messages": [{"role": "user", "content": [{"text": prompt}]}],
        "inferenceConfig": {"maxTokens": 512, "temperature": 0},
    }
    try:
        t0 = time.time()
        resp = c.converse(modelId=model, **body)
        elapsed = time.time() - t0
        out = resp["output"]["message"]["content"][0]["text"]
        clean = out.strip()
        if "```" in clean:
            parts = clean.split("```")
            clean = max(parts, key=len).strip()
            if clean.startswith("json"):
                clean = clean[4:].strip()
        parsed = json.loads(clean)
        ent = parsed.get("entities", {})
        print(f"=== {test['lang']} ({elapsed:.1f}s) ===")
        print(f"  animal_name={ent.get('animal_name')}  tag={ent.get('animal_tag')}  issue={ent.get('issue')}")
        print(f"  symptoms={ent.get('symptoms')}  date={ent.get('date')}  time={ent.get('time')}")
        print(f"  missing={parsed.get('missing_fields')}  confidence={parsed.get('confidence')}")
    except Exception as e:
        print(f"=== {test['lang']} FAILED: {str(e)[:200]}")
    print()
