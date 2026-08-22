#!/usr/bin/env python3
"""Generate audio via gTTS (Google Translate TTS) and test the voice appointment audio endpoint.

gTTS supports all 5 languages (en, hi, ta, te, kn). The generated MP3 is
POSTed to the /api/farmers/demo-farmer/appointments/voice/turn endpoint.
"""
import json
import os
import subprocess
import sys
import tempfile

from gtts import gTTS

# One query per language — same text as the text-based tests
QUERIES = [
    {
        "lang": "en-IN",
        "gtts_lang": "en",
        "text": "My sheep Lakshmi has foot swelling for three days. It is moderate. Book appointment tomorrow at 11:30 AM.",
        "session": "a-en-01",
    },
    {
        "lang": "hi-IN",
        "gtts_lang": "hi",
        "text": "इसका नाम है सीमा, खाना नहीं खा रही है और कल अपॉइंटमेंट चाहिए",
        "session": "a-hi-01",
    },
    {
        "lang": "ta-IN",
        "gtts_lang": "ta",
        "text": "இதன் பெயர் செல்வி, சாப்பிடவில்லை காய்ச்சல் உள்ளது, நாளை காலை 10 மணி சந்திப்பு வேண்டும்",
        "session": "a-ta-01",
    },
    {
        "lang": "te-IN",
        "gtts_lang": "te",
        "text": "దీని పేరు లక్ష్మి, తినడం లేదు, నీరసంగా ఉంది, రేపు ఉదయం 10 గంటలకు అపాయింట్ కావాలి",
        "session": "a-te-01",
    },
    {
        "lang": "kn-IN",
        "gtts_lang": "kn",
        "text": "ಇದರ ಹೆಸರು ಗೌರಿ, ತಿನ್ನುತ್ತಿಲ್ಲ, ಜ್ವರ ಬಂದಿದೆ, ನಾಳೆ ಬೆಳಗ್ಗೆ 10 ಗಂಟೆ ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ಬೇಕು",
        "session": "a-kn-01",
    },
]

URL = "https://65.0.181.84/api/farmers/demo-farmer/appointments/voice/turn"


def generate_audio(query: dict) -> "str | None":
    """Use gTTS to synthesize speech and return the temp file path."""
    text = query["text"]
    lang = query["gtts_lang"]

    try:
        tts = gTTS(text=text, lang=lang, slow=False)
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp.close()
        tts.save(tmp.name)
        size = os.path.getsize(tmp.name)
        print(f"  gTTS OK: lang={lang} size={size} bytes")
        if size < 3000:
            print(f"  WARNING: audio very small ({size} bytes)")
        return tmp.name
    except Exception as e:
        print(f"  gTTS failed: {e}")
        return None


def send_audio(file_path: str, query: dict) -> "dict | None":
    """Send audio file to the voice turn endpoint via curl."""
    session = query["session"]
    lang = query["lang"]

    result = subprocess.run(
        [
            "curl", "-k", "-sS", "--max-time", "120",
            "-X", "POST",
            f"{URL}?session_id={session}&language={lang}",
            "-F", f"audio=@{file_path};type=audio/mpeg",
        ],
        capture_output=True,
        text=True,
        timeout=130,
    )

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"error": "non-JSON response", "stdout": result.stdout[:500], "stderr": result.stderr[:500]}


def main():
    print("=" * 70)
    print("AUDIO VOICE APPOINTMENT TEST — 5 languages via gTTS → AWS Transcribe")
    print("=" * 70)
    print()

    results = []

    for q in QUERIES:
        print(f"--- {q['lang']} / session={q['session']} ---")
        print(f"  Text: {q['text'][:80]}...")

        # Generate audio
        audio_path = generate_audio(q)
        if not audio_path:
            print("  FAILED to generate audio\n")
            results.append({"lang": q["lang"], "status": "audio_gen_failed"})
            continue

        # Send to endpoint
        print(f"  Sending audio to {URL} ...")
        resp = send_audio(audio_path, q)

        # Clean up temp file
        os.unlink(audio_path)

        if "error" in resp:
            print(f"  ERROR: {resp.get('error')}")
            print(f"  stdout: {resp.get('stdout', '')[:200]}")
            print()
            results.append({"lang": q["lang"], "status": "request_failed", "detail": resp})
            continue

        draft = resp.get("draft", {})
        transcription = resp.get("transcript", "")

        summary = {
            "lang": q["lang"],
            "session": q["session"],
            "transcript": transcription[:150],
            "animal": draft.get("animal_name"),
            "issue": draft.get("issue"),
            "symptoms": draft.get("symptoms"),
            "date": draft.get("date"),
            "time": draft.get("time"),
            "missing": resp.get("missing_fields"),
            "response": (resp.get("response_text") or "")[:120],
            "status": draft.get("status"),
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        print()
        results.append(summary)

    # Final summary table
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"{'Lang':<8} {'Animal':<12} {'Issue':<20} {'Symptoms':<20} {'Date':<14} {'Time':<8} {'Status':<10}")
    print("-" * 95)
    for r in results:
        print(f"{r.get('lang','?'):<8} {str(r.get('animal','?')):<12} {str(r.get('issue','?')):<20} {str(r.get('symptoms','?')):<20} {str(r.get('date','?')):<14} {str(r.get('time','?')):<8} {str(r.get('status','?')):<10}")
    print()


if __name__ == "__main__":
    main()
