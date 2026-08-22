#!/usr/bin/env python3
"""Run 15 multilingual voice appointment text queries and report results."""
import json
import subprocess

QUERIES = [
    {"lang": "en-IN", "text": "My sheep Lakshmi has foot swelling for three days. It is moderate. Book appointment tomorrow at 11:30 AM.", "session": "t2-en-01"},
    {"lang": "en-IN", "text": "The goat is not eating since two days and has fever. Need vet visit on Friday at 3pm.", "session": "t2-en-02"},
    {"lang": "en-IN", "text": "Buffalo has wound on leg and limping. Severe pain. Want appointment on 25 August at 9 morning.", "session": "t2-en-03"},
    {"lang": "hi-IN", "text": "इसका नाम है सीमा, खाना नहीं खा रही है और कल अपॉइंटमेंट चाहिए", "session": "t2-hi-01"},
    {"lang": "hi-IN", "text": "भेड़ के पैर में सूजन है, पांच दिन से समस्या है। 29 अगस्त को सुबह 10 बजे अपॉइंटमेंट चाहिए", "session": "t2-hi-02"},
    {"lang": "hi-IN", "text": "बुखार है और सुस्त है। कल शाम को अपॉइंटमेंट दिलाएं", "session": "t2-hi-03"},
    {"lang": "ta-IN", "text": "இதன் பெயர் செல்வி, சாப்பிடவில்லை காய்ச்சல் உள்ளது, நாளை காலை 10 மணி சந்திப்பு வேண்டும்", "session": "t2-ta-01"},
    {"lang": "ta-IN", "text": "ஆட்டிற்கு கால் வீக்கம் உள்ளது, மூன்று நாட்களாக நொண்டுதல் உள்ளது", "session": "t2-ta-02"},
    {"lang": "ta-IN", "text": "மாடு சோர்வாக உள்ளது, தண்ணீர் குடிக்கவில்லை", "session": "t2-ta-03"},
    {"lang": "te-IN", "text": "దీని పేరు లక్ష్మి, తినడం లేదు, నీరసంగా ఉంది, రేపు ఉదయం 10 గంటలకు అపాయింట్ కావాలి", "session": "t2-te-01"},
    {"lang": "te-IN", "text": "గొర్రెకు కాలు వాపు ఉంది, జ్వరం వస్తోంది, రేపు సాయంత్రం 4 గంటలకు", "session": "t2-te-02"},
    {"lang": "te-IN", "text": "మేక బలహీనంగా ఉంది, తినడం లేదు", "session": "t2-te-03"},
    {"lang": "kn-IN", "text": "ಇದರ ಹೆಸರು ಗೌರಿ, ತಿನ್ನುತ್ತಿಲ್ಲ, ಜ್ವರ ಬಂದಿದೆ, ನಾಳೆ ಬೆಳಗ್ಗೆ 10 ಗಂಟೆ ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ಬೇಕು", "session": "t2-kn-01"},
    {"lang": "kn-IN", "text": "ಕುರಿಗೆ ಕಾಲು ಊತ ಇದೆ, ಐದು ದಿನಗಳಿಂದ ಕುಂಟುವುದು", "session": "t2-kn-02"},
    {"lang": "kn-IN", "text": "ಎಮ್ಮೆ ಸುಸ್ತಾಗಿದೆ, ನೀರು ಕುಡಿಯುತ್ತಿಲ್ಲ", "session": "t2-kn-03"},
]

URL = "https://65.0.181.84/api/farmers/demo-farmer/appointments/voice/text"

for q in QUERIES:
    payload = json.dumps({"session_id": q["session"], "language": q["lang"], "text": q["text"]})
    try:
        result = subprocess.run(
            ["curl", "-k", "-sS", "--max-time", "90", "-X", "POST", URL,
             "-H", "Content-Type: application/json", "-d", payload],
            capture_output=True, text=True, timeout=100
        )
        d = json.loads(result.stdout)
        draft = d.get("draft", {})
        print(f"=== {q['lang']} / {q['session']} ===")
        print(json.dumps({
            "animal": draft.get("animal_name"),
            "issue": draft.get("issue"),
            "symptoms": draft.get("symptoms"),
            "date": draft.get("date"),
            "time": draft.get("time"),
            "missing": d.get("missing_fields"),
            "response": (d.get("response_text") or "")[:100],
        }, ensure_ascii=False))
    except Exception as e:
        print(f"=== {q['lang']} / {q['session']} ===")
        print(f"ERROR: {e}")
    print()
