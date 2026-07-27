"""Simplified Farmer Onboarding API for standalone EC2 deployment."""
import json
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from typing import Any, Optional
import boto3

app = FastAPI(title="Farmer Onboarding API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class ProcessTurnIn(BaseModel):
    text: str
    existing: Optional[dict[str, Any]] = None
    language: str = "en"
    current_field: Optional[str] = None
    conversation_history: Optional[list[dict[str, str]]] = None

FARMER_FIELDS = ["name", "aadharNo", "gender", "fatherOrSpouseName", "phone", "alternateMobile",
                 "address_1", "city", "state", "pincode", "country", "hasPanCard", "panNo",
                 "dob", "religion", "caste", "education", "occupation", "farmingExperience",
                 "landHolding", "organizations", "hasGovernmentId"]
FARM_FIELDS = ["farmName", "email", "farmPhone", "alternatePhone", "address", "farmCity",
               "district", "farmPincode", "farmState", "country", "totalAnimalCapacity",
               "currentAnimalCount", "sheepCount", "goatCount", "notes"]

FIELD_QUESTIONS = {
    "name": "What is your name?",
    "aadharNo": "What is your Aadhar number?",
    "gender": "What is your gender?",
    "fatherOrSpouseName": "What is your father's or spouse's name?",
    "phone": "What is your phone number?",
    "city": "Which city do you live in?",
    "state": "Which state are you from?",
    "pincode": "What is your pincode?",
    "farmName": "What is your farm name?",
    "sheepCount": "How many sheep do you have?",
    "goatCount": "How many goats do you have?",
    "totalAnimalCapacity": "What is your total animal capacity?",
    "farmCity": "In which city is your farm?",
    "farmState": "Which state is your farm in?",
    "education": "What is your education level?",
    "occupation": "What is your occupation?",
}

def extract_fields_llm(text: str, existing: dict, language: str,
                       current_field: str = None, conversation_history: list = None) -> dict:
    prev_farmer = existing.get("farmer", {})
    prev_farm = existing.get("farm", {})
    filled_farmer = {k: v for k, v in prev_farmer.items() if v}
    filled_farm = {k: v for k, v in prev_farm.items() if v}
    all_missing = [f for f in FARMER_FIELDS if not filled_farmer.get(f)] + \
                  [f for f in FARM_FIELDS if not filled_farm.get(f)]

    # Build conversation context string
    history_str = "None - this is the first message."
    if conversation_history and len(conversation_history) > 0:
        lines = []
        for turn in conversation_history[-5:]:  # last 5 turns
            role = "Farmer" if turn.get("role") == "user" else "Assistant"
            lines.append(f"  {role}: {turn.get('content', '')}")
        history_str = "\n".join(lines)

    # Determine what was last asked
    last_question = FIELD_QUESTIONS.get(current_field, current_field or "unknown")
    field_hint = current_field or "unknown"

    prompt = f"""You are an intelligent form-filling assistant helping an Indian farmer register their details for sheep/goat farming.

CONVERSATION:
{history_str}

Last question asked by assistant: "{last_question}" (field: "{field_hint}")

Farmer's NEW answer: "{text}"

ALREADY COLLECTED - Farmer: {json.dumps(filled_farmer, ensure_ascii=False)}
ALREADY COLLECTED - Farm: {json.dumps(filled_farm, ensure_ascii=False)}

STILL NEEDED: {json.dumps(all_missing)}

=== EXTRACTION RULES ===

1. CONTEXT IS KEY: The farmer is ANSWERING the last question asked. If the last question was "What is your name?" and the farmer says "Ramu", that is their NAME — extract it as name.

2. SINGLE WORD / SHORT PHRASE answers are almost always the answer to the last question:
   - Last question was "What is your name?" → "Himanshu" = name
   - Last question was "Which city?" → "Bangalore" = city
   - Last question was "How many sheep?" → "200" = sheepCount
   - Last question was "What is your phone?" → "9876543210" = phone

3. REFERENCES TO PREVIOUS ANSWERS: If farmer says "I told you", "I already said", "already told", "I said before" — the farmer is repeating the answer to the CURRENT question. The value they mention is for the field currently being asked.

4. HINDI PATTERNS:
   - "mera naam X hai" / "Mujhe X bolte hain" → name = X
   - "X mein rehta hoon" / "X sheher" / "X se hoon" → city = X
   - "Mere paas X bhed/bakri hai" → sheepCount or goatCount = X
   - "Mera phone X hai" → phone = X
   - "X number hai mera" → phone = X
   - "Mera Aadhaar X hai" → aadharNo = X

5. KANNADA PATTERNS:
   - "Naanu X" / "Nanna hesaru X" → name = X
   - "X nalli irttene" → city = X
   - "X enna X sheep" → sheepCount = X

6. COMBINED ANSWERS: If the farmer gives multiple pieces of info at once, extract ALL of them. E.g. "I'm Ramu from Bangalore with 200 sheep" → name=Ramu, city=Bangalore, sheepCount=200.

7. NUMBERS: sheepCount, goatCount, totalAnimalCapacity must be integers. "200" or "do sau" or "two hundred" → 200.

8. PHONE/AADHAR: Keep as strings (preserve leading zeros). Indian phone = 10 digits. Aadhaar = 12 digits.

9. If the farmer says something that doesn't match ANY needed field, return empty extractions but still set the correct follow_up_question.

OUTPUT: Return ONLY valid JSON (no markdown, no explanation):
{{
  "farmer": {{"name": "...", "phone": "...", ...}},
  "farm": {{"sheepCount": 0, ...}},
  "confidence_notes": "brief note on what you extracted and why"
}}"""

    client = boto3.client("bedrock-runtime", region_name="ap-south-1")
    body = json.dumps({
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1024,
        "temperature": 0,
        "top_p": 0.9
    })
    resp = client.invoke_model(modelId="mistral.mistral-large-3-675b-instruct", body=body)
    result = json.loads(resp["body"].read())
    raw_text = result.get("choices", [{}])[0].get("message", {}).get("content", "{}")

    try:
        parsed = json.loads(raw_text)
    except Exception:
        # Try to find JSON in the response
        import re
        match = re.search(r'\{[\s\S]*\}', raw_text)
        if match:
            try:
                parsed = json.loads(match.group())
            except Exception:
                parsed = {}
        else:
            parsed = {}

    merged_farmer = dict(filled_farmer)
    merged_farm = dict(filled_farm)
    for k, v in parsed.get("farmer", {}).items():
        if v and k in FARMER_FIELDS:
            merged_farmer[k] = v
    for k, v in parsed.get("farm", {}).items():
        if v and k in FARM_FIELDS:
            merged_farm[k] = v

    still_missing = [f for f in FARMER_FIELDS if not merged_farmer.get(f)] + \
                    [f for f in FARM_FIELDS if not merged_farm.get(f)]

    # Determine next field to ask
    next_field = still_missing[0] if still_missing else None
    follow_up = FIELD_QUESTIONS.get(next_field, f"Please tell me your {next_field}") if next_field else None

    return {
        "farmer": merged_farmer,
        "farm": merged_farm,
        "missing_fields": still_missing,
        "follow_up_question": follow_up,
        "current_field": field_hint,
        "complete": len(still_missing) == 0,
    }

@app.post("/onboarding")
def onboarding_turn(req: ProcessTurnIn):
    try:
        return extract_fields_llm(
            req.text,
            req.existing or {},
            req.language,
            current_field=req.current_field,
            conversation_history=req.conversation_history
        )
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/onboarding/health")
def health():
    return {"status": "ok"}

@app.get("/health")
def root_health():
    return {"status": "ok"}

VOICE_HTML_PATH = os.path.join(os.path.dirname(__file__), "voice_page.html")

@app.get("/voice", response_class=HTMLResponse)
def voice_page():
    try:
        with open(VOICE_HTML_PATH, "r") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        raise HTTPException(404, "Voice page not found")

@app.get("/voice_done")
def voice_done(text: str = ""):
    streamlit_url = os.environ.get("STREAMLIT_URL", "https://65.0.181.84:8503")
    return RedirectResponse(url=f"{streamlit_url}?voice_text={text}")

if __name__ == "__main__":
    import uvicorn
    ssl_cert = os.path.join(os.path.dirname(__file__), "cert.pem")
    ssl_key = os.path.join(os.path.dirname(__file__), "key.pem")
    if os.path.exists(ssl_cert) and os.path.exists(ssl_key):
        uvicorn.run(app, host="0.0.0.0", port=8004, ssl_certfile=ssl_cert, ssl_keyfile=ssl_key)
    else:
        uvicorn.run(app, host="0.0.0.0", port=8004)
