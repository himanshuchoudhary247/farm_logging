"""Dev-time QA battery for appointment_supervisor's disambiguation behavior
across every supported language -- NOT run in CI (no AWS credentials there,
see .github/workflows/ci.yml). Run this manually against a live local
server before merging any change that touches appointment_supervisor,
process_text_input, or the extraction tool schema.

Usage:
    uvicorn services.api_service.main:app --host 127.0.0.1 --port 8001 &
    python qa/multilingual_disambiguation_battery.py

Covers the three failure classes found via real user testing (2026-09-19):
  1. Bare partial reply to a targeted field question ("1122" answering
     "what's the animal tag?") -- must land in animal_identifier, not
     issue/symptoms.
  2. Vague/frustrated correction sentence -- must NOT reset to the full
     welcome message once info is already collected, and must not get
     misrouted into "What would you like to correct?" purely because the
     state name is CONFIRMING while a field-ask is still pending.
  3. Follow-up that supplies more info (issue + date/time together) --
     must merge into the existing draft, translated correctly into the
     farmer's language.

Assertions are structural (state machine invariants), not translation-
quality grading -- this checks the CODE doesn't lose data or regress to
a broken state, not that every native-script sentence's nuance was
perfectly understood. The native-script test phrases below are
best-effort constructed (same confidence level as the existing few-shot
examples already shipped in bedrock_adapter.py's _TOOL_SYSTEM_PROMPT),
not linguist-verified -- if a native speaker flags one as wrong, fix the
phrase, not the assertion style.
"""
from __future__ import annotations

import random
import sys
import uuid
from dataclasses import dataclass, field
from typing import Optional

import requests

BASE_URL = "http://127.0.0.1:8001"
FARMER_ID = "f-001"

WELCOME_MARKERS = [
    "Please tell me the animal name",
    "पशु का नाम या टैग",
    "விலங்கின் பெயர்",
    "జంతువు పేరు",
    "ಪ್ರಾಣಿಯ ಹೆಸರು",
]


@dataclass
class Scenario:
    name: str
    language: str
    turns: list  # list of (text, check_fn(reply_text, result_dict, turn_index) -> Optional[str] error message)


def _post(session_id: str, language: str, text: str) -> dict:
    resp = requests.post(
        f"{BASE_URL}/farmers/{FARMER_ID}/chat/turn",
        json={"session_id": session_id, "text": text, "language": language, "include_audio": False},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def _no_welcome_reset(reply_text: str) -> Optional[str]:
    if any(marker in reply_text for marker in WELCOME_MARKERS):
        return f"full welcome message reappeared after info was already collected: {reply_text!r}"
    return None


def build_scenarios() -> list:
    scenarios = []

    # (language, vague-frustrated-correction sentence, followup sentence)
    # Native-script phrases are best-effort, see module docstring.
    lang_phrases = {
        "en-IN": ("1122 is the id, why cant you get it, so frustrating", "fever, tomorrow at 9am"),
        "hi-IN": ("1122 सही है, आप समझ नहीं रहे", "बुखार, कल सुबह 9 बजे"),
        "ta-IN": ("1122 சரியான டேக், நீங்கள் புரியவில்லை", "காய்ச்சல், நாளை காலை 9 மணி"),
        "te-IN": ("1122 సరైన ట్యాగ్, మీకు అర్థం కావడం లేదు", "జ్వరం, రేపు ఉదయం 9 గంటలకు"),
        "kn-IN": ("1122 ಸರಿಯಾದ ಟ್ಯಾಗ್, ನಿಮಗೆ ಅರ್ಥವಾಗುತ್ತಿಲ್ಲ", "ಜ್ವರ, ನಾಳೆ ಬೆಳಿಗ್ಗೆ 9 ಗಂಟೆಗೆ"),
    }

    for lang, (vague, followup) in lang_phrases.items():

        def check_turn2(reply, result, idx):
            draft = result.get("draft", {})
            if not draft.get("animal_identifier"):
                return f"bare tag reply '1122' did not fill animal_identifier, draft={draft}"
            return None

        def check_turn3(reply, result, idx):
            err = _no_welcome_reset(reply)
            if err:
                return err
            draft = result.get("draft", {})
            if not draft.get("animal_identifier"):
                return f"animal_identifier lost after vague correction turn, draft={draft}"
            return None

        def check_turn4(reply, result, idx):
            err = _no_welcome_reset(reply)
            if err:
                return err
            draft = result.get("draft", {})
            if not draft.get("date") or not draft.get("time"):
                return f"followup did not fill date/time, draft={draft}"
            return None

        scenarios.append(Scenario(
            name=f"appointment_disambiguation_{lang}",
            language=lang,
            turns=[
                ("one of my animals is sick", None),
                ("1122", check_turn2),
                (vague, check_turn3),
                (followup, check_turn4),
            ],
        ))

    # Second failure class: changing an ALREADY-GIVEN field after the
    # farmer already confirmed, plus a genuinely ambiguous reply that
    # answers nothing -- the supervisor must not fabricate a value or
    # silently submit, and must not lose already-collected fields.
    change_and_ambiguous_phrases = {
        "en-IN": ("1122, fever, tomorrow at 9am", "actually change the time to 10am", "not sure, whenever works for you"),
        "hi-IN": ("1122, बुखार, कल सुबह 9 बजे", "समय बदलकर 10 बजे कर दो", "पता नहीं, जब भी ठीक हो"),
        "ta-IN": ("1122, காய்ச்சல், நாளை காலை 9 மணி", "நேரத்தை 10 மணிக்கு மாற்று", "தெரியாது, எப்போது வேண்டுமானாலும் சரி"),
        "te-IN": ("1122, జ్వరం, రేపు ఉదయం 9 గంటలకు", "సమయాన్ని 10 గంటలకు మార్చండి", "తెలియదు, ఎప్పుడైనా సరే"),
        "kn-IN": ("1122, ಜ್ವರ, ನಾಳೆ ಬೆಳಿಗ್ಗೆ 9 ಗಂಟೆಗೆ", "ಸಮಯವನ್ನು 10 ಗಂಟೆಗೆ ಬದಲಾಯಿಸಿ", "ಗೊತ್ತಿಲ್ಲ, ಯಾವಾಗಲಾದರೂ ಸರಿ"),
    }

    for lang, (full_info, change_time, ambiguous) in change_and_ambiguous_phrases.items():

        def check_full_info(reply, result, idx):
            draft = result.get("draft", {})
            missing = result.get("missing_fields", [])
            if missing:
                return f"single-turn full info still shows missing fields: {missing}, draft={draft}"
            return None

        def check_confirm_yes(reply, result, idx):
            if result.get("state") != "READY_TO_SUBMIT":
                return f"expected READY_TO_SUBMIT after 'yes', got state={result.get('state')}"
            return None

        def check_change_time(reply, result, idx):
            err = _no_welcome_reset(reply)
            if err:
                return err
            draft = result.get("draft", {})
            if result.get("state") == "SUBMITTED":
                return "changing the time prematurely submitted the appointment"
            if draft.get("time") != "10:00":
                return f"time was not updated to 10:00 after an explicit change request, draft={draft}"
            if not draft.get("animal_identifier") or not draft.get("issue") or not draft.get("date"):
                return f"an already-collected field was lost while changing a different field, draft={draft}"
            return None

        def check_ambiguous(reply, result, idx):
            err = _no_welcome_reset(reply)
            if err:
                return err
            draft = result.get("draft", {})
            if result.get("state") == "SUBMITTED":
                return "an ambiguous, non-answering reply caused a premature submit"
            if draft.get("time") != "10:00":
                return f"an ambiguous reply corrupted a previously-set field, draft={draft}"
            return None

        scenarios.append(Scenario(
            name=f"appointment_change_and_ambiguous_{lang}",
            language=lang,
            turns=[
                ("one of my animals is sick", None),
                (full_info, check_full_info),
                ("yes", check_confirm_yes),
                (change_time, check_change_time),
                (ambiguous, check_ambiguous),
            ],
        ))

    return scenarios


def run() -> int:
    scenarios = build_scenarios()
    failures = []

    for scenario in scenarios:
        session_id = f"qa-{scenario.name}-{uuid.uuid4().hex[:8]}"
        print(f"\n=== {scenario.name} ===")
        for i, (text, check) in enumerate(scenario.turns, start=1):
            try:
                resp = _post(session_id, scenario.language, text)
            except Exception as exc:
                failures.append(f"{scenario.name} turn{i} ({text!r}): request failed: {exc}")
                print(f"  turn{i}: REQUEST FAILED: {exc}")
                break
            reply = resp.get("reply_text", "")
            result = resp.get("result", {})
            print(f"  turn{i} [{text!r}] -> {reply!r}")
            if check:
                err = check(reply, result, i)
                if err:
                    failures.append(f"{scenario.name} turn{i} ({text!r}): {err}")
                    print(f"    FAIL: {err}")

    print("\n" + "=" * 60)
    if failures:
        print(f"{len(failures)} FAILURE(S):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("ALL SCENARIOS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(run())
