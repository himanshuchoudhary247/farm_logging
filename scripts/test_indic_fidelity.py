#!/usr/bin/env python3
"""Test Indic fidelity across Bedrock models — does the model preserve native script?"""
import boto3
import json
import time

c = boto3.client("bedrock-runtime", region_name="ap-south-1")

tests = [
    {"lang": "Hindi", "text": "इसका नाम है सीमा, खाना नहीं खा रही है और कल अपॉइंटमेंट चाहिए", "expected_name": "सीमा"},
    {"lang": "Tamil", "text": "இதன் பெயர் செல்வி, சாப்பிடவில்லை காய்ச்சல் உள்ளது, நாளை காலை 10 மணி சந்திப்பு வேண்டும்", "expected_name": "செல்வி"},
    {"lang": "Telugu", "text": "దీని పేరు లక్ష్మి, తినడం లేదు, నీరసంగా ఉంది, రేపు ఉదయం 10 గంటలకు అపాయింట్ కావాలి", "expected_name": "లక్ష్మి"},
    {"lang": "Kannada", "text": "ಇದರ ಹೆಸರು ಗೌರಿ, ತಿನ್ನುತ್ತಿಲ್ಲ, ಜ್ವರ ಬಂದಿದೆ, ನಾಳೆ ಬೆಳಗ್ಗೆ 10 ಗಂಟೆ ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ಬೇಕು", "expected_name": "ಗೌರಿ"},
    {"lang": "Hindi-code-mixed", "text": "पशु का नाम है मतलब टैग है मेरे पास वन टू थ्री फोर और उसको भूख नहीं लग रही है वो खाना नहीं खा रहा है", "expected_name": "None (tag=1234)"},
]

prompt_template = """Extract structured entities from this {lang} farmer voice transcription.

Text: {text}

Return ONLY valid JSON (no backticks, no markdown):
{{
  "intent": "CREATE_APPOINTMENT or LOG_HEALTH or null",
  "entities": {{
    "animal_name": "animal name in ORIGINAL SCRIPT (Devanagari/Tamil/Telugu/Kannada) or null",
    "animal_tag": "tag number as digits or null",
    "animal_identifier": "name or tag-XXXX",
    "issue": "primary issue in English",
    "symptoms": ["list in English"],
    "date": "YYYY-MM-DD or null",
    "time": "HH:MM or null"
  }},
  "missing_fields": [],
  "confidence": 0.0
}}

RULES:
- Keep animal_name in the ORIGINAL native script (e.g. सीमा, செல்வி, లక్ష్మి, ಗೌರಿ). Do NOT transliterate to Latin.
- "मतलब" is a filler word — NOT an animal name.
- Convert English number words (वन टू थ्री फोर) to digits for tag.
- If tomorrow/कल/நாளை/రేపు/ನಾಳೆ is mentioned, date = 2026-08-22.
"""

models = [
    "qwen.qwen3-235b-a22b-2507-v1:0",
    "qwen.qwen3-32b-v1:0",
    "qwen.qwen3-next-80b-a3b",
    "deepseek.v3.2",
    "mistral.mistral-large-3-675b-instruct",
    "nvidia.nemotron-super-3-120b",
    "google.gemma-3-12b-it",
]

print(f"{'Model':<42} {'Lang':<18} {'Name':<16} {'Script?':<8} {'Issue':<16} {'Time':<6}")
print("-" * 110)

for model in models:
    for test in tests:
        prompt = prompt_template.format(lang=test["lang"], text=test["text"])
        body = {
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "inferenceConfig": {"maxTokens": 400, "temperature": 0},
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
            name = str(ent.get("animal_name", ""))
            # Check if name contains non-Latin chars (native script preserved)
            has_native = any(ord(ch) > 127 for ch in name) if name and name != "None" else False
            script_ok = "YES" if (has_native or name in ("None", "", "null")) else "NO"
            issue = str(ent.get("issue", ""))[:14]
            tag = str(ent.get("animal_tag", ""))
            if tag and tag != "None":
                name_display = f"{name} (tag={tag})"
            else:
                name_display = name[:14]
            print(f"{model:<42} {test['lang']:<18} {name_display:<16} {script_ok:<8} {issue:<16} {ent.get('time',''):<6}")
        except Exception as e:
            err = str(e)[:80]
            print(f"{model:<42} {test['lang']:<18} FAILED: {err}")
    print()
