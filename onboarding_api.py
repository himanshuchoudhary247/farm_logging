"""Simplified Farmer Onboarding API for standalone EC2 deployment."""
import json
import io
import os
import time
import logging
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from typing import Any, Optional
import boto3

log = logging.getLogger("onboarding_api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")

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

FIELD_QUESTIONS_HI = {
    "name": "आपका नाम क्या है?",
    "aadharNo": "आपका आधार नंबर क्या है?",
    "gender": "आपका लिंग क्या है?",
    "fatherOrSpouseName": "आपके पिता या पति का नाम क्या है?",
    "phone": "आपका फोन नंबर क्या है?",
    "city": "आप किस शहर में रहते हैं?",
    "state": "आप किस राज्य से हैं?",
    "pincode": "आपका पिनकोड क्या है?",
    "farmName": "आपके फार्म का नाम क्या है?",
    "sheepCount": "आपके पास कितनी भेड़ें हैं?",
    "goatCount": "आपके पास कितनी बकरियां हैं?",
    "totalAnimalCapacity": "आपकी कुल पशु क्षमता क्या है?",
    "farmCity": "आपका फार्म किस शहर में है?",
    "farmState": "आपका फार्म किस राज्य में है?",
    "education": "आपकी शिक्षा क्या है?",
    "occupation": "आपका पेशा क्या है?",
}

FIELD_QUESTIONS_KN = {
    "name": "ನಿಮ್ಮ ಹೆಸರು ಯಾವುದು?",
    "aadharNo": "ನಿಮ್ಮ ಆಧಾರ್ ನಂಬರ್ ಯಾವುದು?",
    "gender": "ನಿಮ್ಮ ಲಿಂಗ ಯಾವುದು?",
    "fatherOrSpouseName": "ನಿಮ್ಮ ತಂದೆ ಅಥವಾ ಪತ್ನಿಯ ಹೆಸರು ಯಾವುದು?",
    "phone": "ನಿಮ್ಮ ಫೋನ್ ನಂಬರ್ ಯಾವುದು?",
    "city": "ನೀವು ಯಾವ ನಗರದಲ್ಲಿ ವಾಸಿಸುತ್ತೀರಿ?",
    "state": "ನೀವು ಯಾವ ರಾಜ್ಯದಿಂದ ಬಂದಿದ್ದೀರಿ?",
    "pincode": "ನಿಮ್ಮ ಪಿನ್‌ಕೋಡ್ ಯಾವುದು?",
    "farmName": "ನಿಮ್ಮ ಫಾರ್ಮ್ ಹೆಸರು ಯಾವುದು?",
    "sheepCount": "ನಿಮ್ಮ ಹತ್ತಿರ ಎಷ್ಟು ಕುರಿಗಳಿವೆ?",
    "goatCount": "ನಿಮ್ಮ ಹತ್ತಿರ ಎಷ್ಟು ಮೇಕೆಗಳಿವೆ?",
    "totalAnimalCapacity": "ನಿಮ್ಮ ಒಟ್ಟು ಪ್ರಾಣಿ ಸಾಮರ್ಥ್ಯ ಯಾವುದು?",
    "farmCity": "ನಿಮ್ಮ ಫಾರ್ಮ್ ಯಾವ ನಗರದಲ್ಲಿದೆ?",
    "farmState": "ನಿಮ್ಮ ಫಾರ್ಮ್ ಯಾವ ರಾಜ್ಯದಲ್ಲಿದೆ?",
    "education": "ನಿಮ್ಮ ಶಿಕ್ಷಣ ಯಾವುದು?",
    "occupation": "ನಿಮ್ಮ ವೃತ್ತಿ ಯಾವುದು?",
}

FIELD_QUESTIONS_TE = {
    "name": "మీ పేరు ఏమిటి?",
    "aadharNo": "మీ ఆధార్ నంబర్ ఏమిటి?",
    "gender": "మీ లింగం ఏమిటి?",
    "fatherOrSpouseName": "మీ తండ్రి లేదా భార్య పేరు ఏమిటి?",
    "phone": "మీ ఫోన్ నంబర్ ఏమిటి?",
    "city": "మీరు ఏ నగరంలో నివసిస్తున్నారు?",
    "state": "మీరు ఏ రాష్ట్రం నుండి వచ్చారు?",
    "pincode": "మీ పిన్‌కోడ్ ఏమిటి?",
    "farmName": "మీ ఫారం పేరు ఏమిటి?",
    "sheepCount": "మీ దగ్గర ఎన్ని గొర్రెలు ఉన్నాయి?",
    "goatCount": "మీ దగ్గర ఎన్ని మేకలు ఉన్నాయి?",
    "totalAnimalCapacity": "మీ మొత్తం జంతు సామర్థ్యం ఏమిటి?",
    "farmCity": "మీ ఫారం ఏ నగరంలో ఉంది?",
    "farmState": "మీ ఫారం ఏ రాష్ట్రంలో ఉంది?",
    "education": "మీ విద్య ఏమిటి?",
    "occupation": "మీ వృత్తి ఏమిటి?",
}

FIELD_QUESTIONS_TA = {
    "name": "உங்கள் பெயர் என்ன?",
    "aadharNo": "உங்கள் ஆதார் எண் என்ன?",
    "gender": "உங்கள் பாலினம் என்ன?",
    "fatherOrSpouseName": "உங்கள் தந்தை அல்லது மனைவியின் பெயர் என்ன?",
    "phone": "உங்கள் போன் நம்பர் என்ன?",
    "city": "நீங்கள் எந்த நகரத்தில் வசிக்கிறீர்கள்?",
    "state": "நீங்கள் எந்த மாநிலத்தைச் சேர்ந்தவர்?",
    "pincode": "உங்கள் பின் கோட் என்ன?",
    "farmName": "உங்கள் பண்ணையின் பெயர் என்ன?",
    "sheepCount": "உங்களிடம் எத்தனை ஆடுகள் உள்ளன?",
    "goatCount": "உங்களிடம் எத்தனை வெள்ளாடுகள் உள்ளன?",
    "totalAnimalCapacity": "உங்கள் மொத்த விலங்கு திறன் என்ன?",
    "farmCity": "உங்கள் பண்ணை எந்த நகரத்தில் உள்ளது?",
    "farmState": "உங்கள் பண்ணை எந்த மாநிலத்தில் உள்ளது?",
    "education": "உங்கள் கல்வி என்ன?",
    "occupation": "உங்கள் தொழில் என்ன?",
}

FIELD_QUESTIONS_MR = {
    "name": "तुमचे नाव काय आहे?",
    "aadharNo": "तुमचा आधार नंबर काय आहे?",
    "gender": "तुमचे लिंग काय आहे?",
    "fatherOrSpouseName": "तुमच्या वडिलांचे किंवा पत्नीचे नाव काय आहे?",
    "phone": "तुमचा फोन नंबर काय आहे?",
    "city": "तुम्ही कोणत्या शहरात राहता?",
    "state": "तुम्ही कोणत्या राज्यातून आला आहात?",
    "pincode": "तुमचा पिनकोड काय आहे?",
    "farmName": "तुमच्या शेताचे नाव काय आहे?",
    "sheepCount": "तुमच्याकडे किती मेंढ्या आहेत?",
    "goatCount": "तुमच्याकडे किती शेळ्या आहेत?",
    "totalAnimalCapacity": "तुमची एकूण प्राणी क्षमता काय आहे?",
    "farmCity": "तुमचे शेत कोणत्या शहरात आहे?",
    "farmState": "तुमचे शेत कोणत्या राज्यात आहे?",
    "education": "तुमचे शिक्षण काय आहे?",
    "occupation": "तुमचा व्यवसाय काय आहे?",
}

FIELD_QUESTIONS_PA = {
    "name": "ਤੁਹਾਡਾ ਨਾਮ ਕੀ ਹੈ?",
    "aadharNo": "ਤੁਹਾਡਾ ਆਧਾਰ ਨੰਬਰ ਕੀ ਹੈ?",
    "gender": "ਤੁਹਾਡਾ ਲਿੰਗ ਕੀ ਹੈ?",
    "fatherOrSpouseName": "ਤੁਹਾਡੇ ਪਿਤਾ ਜਾਂ ਪਤਨੀ ਦਾ ਨਾਮ ਕੀ ਹੈ?",
    "phone": "ਤੁਹਾਡਾ ਫੋਨ ਨੰਬਰ ਕੀ ਹੈ?",
    "city": "ਤੁਸੀਂ ਕਿਸ ਸ਼ਹਿਰ ਵਿੱਚ ਰਹਿੰਦੇ ਹੋ?",
    "state": "ਤੁਸੀਂ ਕਿਸ ਰਾਜ ਤੋਂ ਹੋ?",
    "pincode": "ਤੁਹਾਡਾ ਪਿੰਕੋਡ ਕੀ ਹੈ?",
    "farmName": "ਤੁਹਾਡੇ ਫਾਰਮ ਦਾ ਨਾਮ ਕੀ ਹੈ?",
    "sheepCount": "ਤੁਹਾਡੇ ਕੋਲ ਕਿੰਨੀਆਂ ਭੇਡਾਂ ਹਨ?",
    "goatCount": "ਤੁਹਾਡੇ ਕੋਲ ਕਿੰਨੀਆਂ ਬਕਰੀਆਂ ਹਨ?",
    "totalAnimalCapacity": "ਤੁਹਾਡੀ ਕੁੱਲ ਪਸ਼ੂ ਸਮਰੱਥਾ ਕੀ ਹੈ?",
    "farmCity": "ਤੁਹਾਡਾ ਫਾਰਮ ਕਿਸ ਸ਼ਹਿਰ ਵਿੱਚ ਹੈ?",
    "farmState": "ਤੁਹਾਡਾ ਫਾਰਮ ਕਿਸ ਰਾਜ ਵਿੱਚ ਹੈ?",
    "education": "ਤੁਹਾਡੀ ਸਿੱਖਿਆ ਕੀ ਹੈ?",
    "occupation": "ਤੁਹਾਡਾ ਪੇਸ਼ਾ ਕੀ ਹੈ?",
}

LANG_QUESTION_MAP = {
    "en": FIELD_QUESTIONS,
    "hi": FIELD_QUESTIONS_HI,
    "kn": FIELD_QUESTIONS_KN,
    "te": FIELD_QUESTIONS_TE,
    "ta": FIELD_QUESTIONS_TA,
    "mr": FIELD_QUESTIONS_MR,
    "pa": FIELD_QUESTIONS_PA,
}

FIELD_LABELS = {
    "en": {"name": "name", "phone": "phone number", "city": "city", "state": "state",
           "pincode": "pincode", "gender": "gender", "aadharNo": "Aadhar number",
           "fatherOrSpouseName": "father's/spouse's name", "sheepCount": "sheep count",
           "goatCount": "goat count", "farmName": "farm name", "education": "education",
           "occupation": "occupation", "totalAnimalCapacity": "animal capacity",
           "farmCity": "farm city", "farmState": "farm state"},
    "hi": {"name": "नाम", "phone": "फोन नंबर", "city": "शहर", "state": "राज्य",
           "pincode": "पिनकोड", "gender": "लिंग", "aadharNo": "आधार नंबर",
           "fatherOrSpouseName": "पिता/पति का नाम", "sheepCount": "भेड़ों की संख्या",
           "goatCount": "बकरियों की संख्या", "farmName": "फार्म का नाम",
           "education": "शिक्षा", "occupation": "पेशा",
           "totalAnimalCapacity": "पशु क्षमता", "farmCity": "फार्म का शहर",
           "farmState": "फार्म का राज्य"},
    "kn": {"name": "ಹೆಸರು", "phone": "ಫೋನ್ ನಂಬರ್", "city": "ನಗರ", "state": "ರಾಜ್ಯ",
           "pincode": "ಪಿನ್‌ಕೋಡ್", "gender": "ಲಿಂಗ", "aadharNo": "ಆಧಾರ್ ನಂಬರ್",
           "fatherOrSpouseName": "ತಂದೆ/ಪತ್ನಿ ಹೆಸರು", "sheepCount": "ಕುರಿಗಳ ಸಂಖ್ಯೆ",
           "goatCount": "ಮೇಕೆಗಳ ಸಂಖ್ಯೆ", "farmName": "ಫಾರ್ಮ್ ಹೆಸರು",
           "education": "ಶಿಕ್ಷಣ", "occupation": "ವೃತ್ತಿ",
           "totalAnimalCapacity": "ಪ್ರಾಣಿ ಸಾಮರ್ಥ್ಯ", "farmCity": "ಫಾರ್ಮ್ ನಗರ",
           "farmState": "ಫಾರ್ಮ್ ರಾಜ್ಯ"},
    "te": {"name": "పేరు", "phone": "ఫోన్ నంబర్", "city": "నగరం", "state": "రాష్ట్రం",
           "pincode": "పిన్‌కోడ్", "gender": "లింగం", "aadharNo": "ఆధార్ నంబర్",
           "fatherOrSpouseName": "తండ్రి/భార్య పేరు", "sheepCount": "గొర్రెల సంఖ్య",
           "goatCount": "మేకల సంఖ్య", "farmName": "ఫారం పేరు",
           "education": "విద్య", "occupation": "వృత్తి",
           "totalAnimalCapacity": "జంతు సామర్థ్యం", "farmCity": "ఫారం నగరం",
           "farmState": "ఫారం రాష్ట్రం"},
    "ta": {"name": "பெயர்", "phone": "போன் நம்பர்", "city": "நகரம்", "state": "மாநிலம்",
           "pincode": "பின் கோட்", "gender": "பாலினம்", "aadharNo": "ஆதார் எண்",
           "fatherOrSpouseName": "தந்தை/மனைவி பெயர்", "sheepCount": "ஆடுகளின் எண்ணிக்கை",
           "goatCount": "வெள்ளாடு எண்ணிக்கை", "farmName": "பண்ணை பெயர்",
           "education": "கல்வி", "occupation": "தொழில்",
           "totalAnimalCapacity": "விலங்கு திறன்", "farmCity": "பண்ணை நகரம்",
           "farmState": "பண்ணை மாநிலம்"},
    "mr": {"name": "नाव", "phone": "फोन नंबर", "city": "शहर", "state": "राज्य",
           "pincode": "पिनकोड", "gender": "लिंग", "aadharNo": "आधार नंबर",
           "fatherOrSpouseName": "वडील/पत्नी नाव", "sheepCount": "मेंढ्यांची संख्या",
           "goatCount": "शेळ्यांची संख्या", "farmName": "शेताचे नाव",
           "education": "शिक्षण", "occupation": "व्यवसाय",
           "totalAnimalCapacity": "प्राणी क्षमता", "farmCity": "शेताचे शहर",
           "farmState": "शेताचे राज्य"},
    "pa": {"name": "ਨਾਮ", "phone": "ਫੋਨ ਨੰਬਰ", "city": "ਸ਼ਹਿਰ", "state": "ਰਾਜ",
           "pincode": "ਪਿੰਕੋਡ", "gender": "ਲਿੰਗ", "aadharNo": "ਆਧਾਰ ਨੰਬਰ",
           "fatherOrSpouseName": "ਪਿਤਾ/ਪਤਨੀ ਨਾਮ", "sheepCount": "ਭੇਡਾਂ ਦੀ ਗਿਣਤੀ",
           "goatCount": "ਬਕਰੀਆਂ ਦੀ ਗਿਣਤੀ", "farmName": "ਫਾਰਮ ਦਾ ਨਾਮ",
           "education": "ਸਿੱਖਿਆ", "occupation": "ਪੇਸ਼ਾ",
           "totalAnimalCapacity": "ਪਸ਼ੂ ਸਮਰੱਥਾ", "farmCity": "ਫਾਰਮ ਦਾ ਸ਼ਹਿਰ",
           "farmState": "ਫਾਰਮ ਦਾ ਰਾਜ"},
}

CONFIRM_PREFIX = {
    "en": "Got it, thank you! ",
    "hi": "ठीक है, धन्यवाद! ",
    "kn": "ಸರಿ, ಧನ್ಯವಾದ! ",
    "te": "సరే, ధన్యవాదాలు! ",
    "ta": "சரி, நன்றி! ",
    "mr": "ठीक आहे, धन्यवाद! ",
    "pa": "ਠੀਕ ਹੈ, ਧੰਨਵਾਦ! ",
}

POLITE_OPENER = {
    "en": "Please tell me, ",
    "hi": "कृपया बताइए, ",
    "kn": "ದಯವಿಟ್ಟು ತಿಳಿಸಿ, ",
    "te": "దయచేసి చెప్పండి, ",
    "ta": "தயவுசெய்து சொல்லுங்கள், ",
    "mr": "कृपया सांगा, ",
    "pa": "ਕਿਰਪਾ ਕਰਕੇ ਦੱਸੋ, ",
}

GREETING_ACK = {
    "en": "Hello! Nice to meet you.",
    "hi": "नमस्ते! आपका स्वागत है।",
    "kn": "ನಮಸ್ಕಾರ! ನಿಮಗೆ ಸ್ವಾಗತ.",
    "te": "నమస్కారం! మీకు స్వాగతం.",
    "ta": "வணக்கம்! உங்களை வரவேற்கிறோம்.",
    "mr": "नमस्कार! आपले स्वागत आहे.",
    "pa": "ਸਤ ਸ੍ਰੀ ਅਕਾਲ! ਤੁਹਾਡਾ ਸਵਾਗਤ ਹੈ।",
}

GREETING_PHRASES = {
    "en": {"hello", "hi", "hey", "hii", "hiii", "yo", "sup", "whats up", "what's up", "how are you", "how are u", "how r u", "good morning", "good evening", "good afternoon", "hi there", "hey there", "hello there", "namaste"},
    "hi": {"हेलो", "हैलो", "नमस्ते", "नमस्कार", "हाय", "सुप्रभात", "शुभ प्रभात", "हेलो व्हाट एस अप", "हेलो व्हाट'एस अप", "हैलो व्हाट एस अप", "हेलो हेलो व्हाट एस अप", "हेलो हेलो व्हाट'एस अप", "क्या चल रहा है", "क्या चल रहा", "क्या हाल है", "कैसे हो", "कैसे हैं", "हाय व्हाट एस अप"},
    "kn": {"ನಮಸ್ಕಾರ", "ಹಲೋ", "ಹಾಯ್", "ಹೇ", "ಏನು ಸಮಾಚಾರ", "ಹಲೋ ಹೇಗಿದ್ದೀರಾ"},
    "te": {"నమస్కారం", "హలో", "హాయ్", "ఏమి సంగతులు", "హలో ఎలా ఉన్నారు"},
    "ta": {"வணக்கம்", "ஹலோ", "ஹாய்", "என்ன சமாச்சாரம்", "எப்படி இருக்கிறீர்கள்"},
    "mr": {"नमस्कार", "हॅलो", "हाय", "काय चाललं", "कसं आहात"},
    "pa": {"ਸਤ ਸ੍ਰੀ ਅਕਾਲ", "ਹੈਲੋ", "ਹਾਇ", "ਕੀ ਹਾਲ ਹੈ", "ਕੀ ਹਾਲ ਏ"},
}

GREETING_TOKENS = {
    "en": {"hello", "hi", "hey", "hii", "hiii", "yo", "sup", "what", "whats", "what's", "up", "how", "are", "you", "r", "u", "there", "morning", "good", "namaste"},
    "hi": {"हेलो", "हैलो", "हाय", "नमस्ते", "नमस्कार", "व्हाट", "व्हाट'एस", "व्हाट्स", "अप", "सुप्रभात", "हैलो"},
    "kn": {"ನಮಸ್ಕಾರ", "ಹಲೋ", "ಹಾಯ್", "ಹೇ", "ಏನು", "ಸಮಾಚಾರ", "ಹೇಗಿದ್ದೀರಾ"},
    "te": {"నమస్కారం", "హలో", "హాయ్", "ఏమి", "సంగతులు", "ఎలా", "ఉన్నారు"},
    "ta": {"வணக்கம்", "ஹலோ", "ஹாய்", "என்ன", "சமாச்சாரம்", "எப்படி"},
    "mr": {"नमस्कार", "हॅलो", "हाय", "काय", "चाललं", "कसं", "आहात"},
    "pa": {"ਸਤ", "ਸ੍ਰੀ", "ਅਕਾਲ", "ਹੈਲੋ", "ਹਾਇ", "ਕੀ", "ਹਾਲ", "ਏ"},
}

FIELD_FORMAT_HINTS = {
    "aadharNo": {
        "en": "Aadhaar number is 12 digits — please give the full 12-digit number.",
        "hi": "आधार नंबर 12 अंकों का होता है — कृपया पूरा 12 अंकों का नंबर बताएं।",
        "kn": "ಆಧಾರ್ ಸಂಖ್ಯೆ 12 ಅಂಕೆಗಳಾಗಿದೆ — ದಯವಿಟ್ಟು ಪೂರ್ಣ 12 ಅಂಕೆಯ ಸಂಖ್ಯೆಯನ್ನು ನೀಡಿ.",
        "te": "ఆధార్ నంబర్ 12 అంకెలు — దయచేసి పూర్తి 12 అంకెల నంబర్ ఇవ్వండి.",
        "ta": "ஆதார் எண் 12 இலக்கங்கள் — தயவுசெய்து முழு 12 இலக்க எண்ணைக் கொடுங்கள்.",
        "mr": "आधार क्रमांक 12 अंकी असतो — कृपया पूर्ण 12 अंकी क्रमांक द्या.",
        "pa": "ਆਧਾਰ ਨੰਬਰ 12 ਅੰਕਾਂ ਦਾ ਹੁੰਦਾ ਹੈ — ਕਿਰਪਾ ਕਰਕੇ ਪੂਰਾ 12 ਅੰਕਾਂ ਦਾ ਨੰਬਰ ਦਿਓ।",
    },
    "phone": {
        "en": "Phone number is 10 digits — please give the full 10-digit mobile number.",
        "hi": "फोन नंबर 10 अंकों का होता है — कृपया पूरा 10 अंकों का मोबाइल नंबर बताएं।",
        "kn": "ಫೋನ್ ಸಂಖ್ಯೆ 10 ಅಂಕೆಗಳು — ದಯವಿಟ್ಟು ಪೂರ್ಣ 10 ಅಂಕೆಯ ಮೊಬೈಲ್ ಸಂಖ್ಯೆ ನೀಡಿ.",
        "te": "ఫోన్ నంబర్ 10 అంకెలు — దయచేసి పూర్తి 10 అంకెల మొబైల్ నంబర్ ఇవ్వండి.",
        "ta": "தொலைபேசி எண் 10 இலக்கங்கள் — தயவுசெய்து முழு 10 இலக்க மொபைல் எண்ணைக் கொடுங்கள்.",
        "mr": "फोन क्रमांक 10 अंकी असतो — कृपया पूर्ण 10 अंकी मोबाईल क्रमांक द्या.",
        "pa": "ਫੋਨ ਨੰਬਰ 10 ਅੰਕਾਂ ਦਾ ਹੁੰਦਾ ਹੈ — ਕਿਰਪਾ ਕਰਕੇ ਪੂਰਾ 10 ਅੰਕਾਂ ਦਾ ਮੋਬਾਈਲ ਨੰਬਰ ਦਿਓ।",
    },
    "pincode": {
        "en": "PIN code is 6 digits — please give the full 6-digit PIN code.",
        "hi": "पिन कोड 6 अंकों का होता है — कृपया पूरा 6 अंकों का पिन कोड बताएं।",
        "kn": "ಪಿನ್ ಕೋಡ್ 6 ಅಂಕೆಗಳು — ದಯವಿಟ್ಟು ಪೂರ್ಣ 6 ಅಂಕೆಯ ಪಿನ್ ಕೋಡ್ ನೀಡಿ.",
        "te": "పిన్ కోడ్ 6 అంకెలు — దయచేసి పూర్తి 6 అంకెల పిన్ కోడ్ ఇవ్వండి.",
        "ta": "பின் குறியீடு 6 இலக்கங்கள் — தயவுசெய்து முழு 6 இலக்க பின் குறியீட்டைக் கொடுங்கள்.",
        "mr": "पिन कोड 6 अंकी असतो — कृपया पूर्ण 6 अंकी पिन कोड द्या.",
        "pa": "ਪਿੰਨ ਕੋਡ 6 ਅੰਕਾਂ ਦਾ ਹੁੰਦਾ ਹੈ — ਕਿਰਪਾ ਕਰਕੇ ਪੂਰਾ 6 ਅੰਕਾਂ ਦਾ ਪਿੰਨ ਕੋਡ ਦਿਓ।",
    },
    "gender": {
        "en": "Please tell me: male, female, or other.",
        "hi": "कृपया बताएं: पुरुष, महिला या अन्य।",
        "kn": "ದಯವಿಟ್ಟು ಹೇಳಿ: ಪುರುಷ, ಮಹಿಳೆ, ಅಥವಾ ಇತರೆ.",
        "te": "దయచేసి చెప్పండి: పురుషుడు, స్త్రీ, లేదా ఇతర.",
        "ta": "தயவுசெய்து கூறுங்கள்: ஆண், பெண், அல்லது மற்றவை.",
        "mr": "कृपया सांगा: पुरुष, स्त्री किंवा इतर.",
        "pa": "ਕਿਰਪਾ ਕਰਕੇ ਦੱਸੋ: ਪੁਰਸ਼, ਔਰਤ, ਜਾਂ ਹੋਰ।",
    },
}

GENDER_MAP = {
    "male": ["male", "man", "m", "पुरुष", "पुलिंग", "पुरूष", "नर", "मर्द", "लड़का", "पुरुष हूं", "मैं पुरुष हूं",
             "ಪುರುಷ", "ಗಂಡು", "పురుషుడు", "మగ", "ஆண்", "पुरुष आहे", "मी पुरुष", "ਪੁਰਸ਼", "ਮਰਦ", "ਆਦਮੀ"],
    "female": ["female", "woman", "f", "w", "महिला", "स्त्री", "स्री", "लड़की", "महिला हूं", "मैं महिला हूं",
               "ಮಹಿಳೆ", "ಹೆಣ್ಣು", "స్త్రీ", "మహిళ", "ఆడ", "பெண்", "स्त्री आहे", "मी महिला", "ਔਰਤ", "ਇਸਤਰੀ"],
    "other": ["other", "others", "अन्य", "transgender", "trans", "थर्ड जेंडर", "ತೃತೀಯ", "ఇతర", "மற்றவை", "इतर", "होर"],
}

FIELD_FORMAT = {
    "aadharNo": {"type": "digits", "length": 12},
    "phone": {"type": "digits", "length": 10},
    "alternateMobile": {"type": "digits", "length": 10},
    "farmPhone": {"type": "digits", "length": 10},
    "alternatePhone": {"type": "digits", "length": 10},
    "pincode": {"type": "digits", "length": 6},
    "farmPincode": {"type": "digits", "length": 6},
    "gender": {"type": "enum"},
    "sheepCount": {"type": "int"},
    "goatCount": {"type": "int"},
    "totalAnimalCapacity": {"type": "int"},
}

def _is_greeting(text: str, lang_code: str) -> bool:
    import re
    import string
    if not text or not text.strip():
        return False
    clean = " ".join(text.lower().split())
    _punct = string.punctuation.replace("'", "")
    clean = re.sub("[" + re.escape(_punct) + "]", "", clean).strip()
    if clean in GREETING_PHRASES.get(lang_code, set()):
        return True
    tokens = [t for t in re.split(r"\s+", clean) if t]
    toks = GREETING_TOKENS.get(lang_code, set())
    return bool(tokens) and all(t in toks for t in tokens)

def _validate_value(field: str, value, lang_code: str):
    import re
    fmt = FIELD_FORMAT.get(field)
    if not fmt:
        return value, None
    hint = FIELD_FORMAT_HINTS.get(field, {}).get(lang_code, FIELD_FORMAT_HINTS.get(field, {}).get("en"))
    if fmt["type"] == "digits":
        digits = re.sub(r"\D", "", str(value))
        if len(digits) != fmt["length"]:
            return None, hint
        return digits, None
    if fmt["type"] == "int":
        try:
            return int(str(value).replace(",", "").strip()), None
        except Exception:
            return None, hint
    if fmt["type"] == "enum":
        norm = str(value).strip().lower()
        for canonical, synonyms in GENDER_MAP.items():
            if norm in synonyms or any(s in norm for s in synonyms if len(s) > 2):
                return canonical, None
        return None, hint
    return value, None

def extract_fields_llm(text: str, existing: dict, language: str,
                       current_field: str = None, conversation_history: list = None) -> dict:
    t_total_start = time.time()
    prev_farmer = existing.get("farmer", {})
    prev_farm = existing.get("farm", {})
    filled_farmer = {k: v for k, v in prev_farmer.items() if v}
    filled_farm = {k: v for k, v in prev_farm.items() if v}
    all_missing = [f for f in FARMER_FIELDS if not filled_farmer.get(f)] + \
                  [f for f in FARM_FIELDS if not filled_farm.get(f)]

    lang_code = language.split("-")[0] if language else "en"
    lang_questions = LANG_QUESTION_MAP.get(lang_code, FIELD_QUESTIONS)

    # Greeting / small-talk guard: never extract a greeting into a data field
    if _is_greeting(text, lang_code):
        ask_field = current_field or (all_missing[0] if all_missing else None)
        question = lang_questions.get(ask_field, FIELD_QUESTIONS.get(ask_field, "What can I help you with?"))
        elapsed_total = (time.time() - t_total_start) * 1000
        log.info("LATENCY greeting_check total=%.0fms", elapsed_total)
        return {
            "farmer": filled_farmer,
            "farm": filled_farm,
            "missing_fields": all_missing,
            "follow_up_question": f"{GREETING_ACK.get(lang_code, 'Hello!')} {POLITE_OPENER.get(lang_code, '')}{question.lower() if lang_code == 'en' else question}",
            "current_field": ask_field,
            "complete": False,
            "timing": {"total_ms": round(elapsed_total, 1), "model_ms": 0, "pre_model_ms": round(elapsed_total, 1), "post_model_ms": 0},
        }

    # Build conversation context string
    history_str = "None - this is the first message."
    if conversation_history and len(conversation_history) > 0:
        lines = []
        for turn in conversation_history[-5:]:  # last 5 turns
            role = "Farmer" if turn.get("role") == "user" else "Assistant"
            lines.append(f"  {role}: {turn.get('content', '')}")
        history_str = "\n".join(lines)

    # Determine what was last asked (in selected language)
    lang_code = language.split("-")[0] if language else "en"
    lang_questions = LANG_QUESTION_MAP.get(lang_code, FIELD_QUESTIONS)
    last_question = lang_questions.get(current_field, FIELD_QUESTIONS.get(current_field, current_field or "unknown"))
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

10. NAMES ARE ALWAYS NAMES: A person's name (English, Hindi, Kannada, any script — e.g. "Himanshu", "हिमांशु", "रामु", "ಸುರೇಶ್") is ALWAYS extracted as `name`, EVEN IF the last question was about another field (like phone or Aadhar). If a real name appears in the message, overwrite any existing `name` value — the farmer may be correcting an earlier wrong/test answer (e.g. they typed "ABCD" before but now give their real name "हिमांशु").

11. FORMAT MISMATCH = ROUTE TO CORRECT FIELD: If the farmer's answer does NOT match the format expected by the current question, figure out what field it actually belongs to:
   - Current question was about Aadhar (12 digits) but answer is a person's name → put it in `name`, not aadharNo
   - Current question was about phone (10 digits) but answer is a name → put it in `name`
   - Current question was about sheepCount but answer is "50 goats" → put in goatCount
   - Current question was about city but answer is a number → put in the right numeric field

12. FIELD FORMAT EXPECTATIONS:
   - phone: 10 digits (Indian mobile)
   - aadharNo: 12 digits (a partial number like "123456" is INVALID — do NOT extract it; leave aadharNo empty)
   - pincode: 6 digits
   - sheepCount/goatCount/totalAnimalCapacity: integers
   - name/city/state/education/occupation: text
   - gender: ALWAYS return one of exactly: "male", "female", or "other" (English, lowercase). Map "पुलिंग"/"पुरुष"/"पुरुष हूं" → "male", "महिला"/"स्त्री" → "female", "अन्य" → "other".
   A value that violates the expected format for the current field should be redirected to the field it DOES match.

13. GREETINGS / SMALL TALK ARE NEVER DATA: If the farmer only says a greeting, pleasantry, or filler ("hello", "hi", "हेलो", "नमस्ते", "क्या हाल है", "बढ़िया है", "all good", "ठीक है", "चंगा", etc.), do NOT extract anything into any field — return empty farmer/farm. The assistant will re-ask the current question.

14. NON-ANSWER / REPEATED NONSENSE: If the farmer repeats a word that is clearly not an answer to any question (e.g. repeating "पुलिंग पुलिंग" when asked for a name), do NOT extract it — return empty farmer/farm.

15. TONE: The assistant is a warm, respectful helper speaking to a rural farmer. Never be rude, impatient, or judgmental. If the farmer's input is unclear, still reply gently — the system's follow_up_question will be polite. Do not emit scolding or frustration into confidence_notes.

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
    t_model_start = time.time()
    resp = client.invoke_model(modelId="mistral.mistral-large-3-675b-instruct", body=body)
    model_elapsed = (time.time() - t_model_start) * 1000
    result = json.loads(resp["body"].read())
    raw_text = result.get("choices", [{}])[0].get("message", {}).get("content", "{}")
    t_parse_start = time.time()
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
    parse_elapsed = (time.time() - t_parse_start) * 1000
    log.info("LATENCY model_invoke=%.0fms json_parse=%.1fms", model_elapsed, parse_elapsed)

    merged_farmer = dict(filled_farmer)
    merged_farm = dict(filled_farm)
    for k, v in parsed.get("farmer", {}).items():
        if v and k in FARMER_FIELDS:
            merged_farmer[k] = v
    for k, v in parsed.get("farm", {}).items():
        if v and k in FARM_FIELDS:
            merged_farm[k] = v

    # Deterministic format validation: reject invalid values so the field gets re-asked
    rejected = {}
    for k, v in list(merged_farmer.items()):
        if k in FIELD_FORMAT and v:
            new_val, err = _validate_value(k, v, lang_code)
            if err:
                rejected[k] = err
                del merged_farmer[k]
            else:
                merged_farmer[k] = new_val
    for k, v in list(merged_farm.items()):
        if k in FIELD_FORMAT and v:
            new_val, err = _validate_value(k, v, lang_code)
            if err:
                rejected[k] = err
                del merged_farm[k]
            else:
                merged_farm[k] = new_val

    # Rejected fields are asked first (re-validate existing stored values only if they were in this turn)
    rejected_fields = list(rejected.keys())
    still_missing = rejected_fields + \
                    [f for f in FARMER_FIELDS if not merged_farmer.get(f) and f not in rejected_fields] + \
                    [f for f in FARM_FIELDS if not merged_farm.get(f) and f not in rejected_fields]

    # Determine next field to ask (in selected language)
    next_field = still_missing[0] if still_missing else None
    if next_field:
        raw_q = lang_questions.get(next_field, FIELD_QUESTIONS.get(next_field, f"Please tell me your {next_field}"))
        if lang_code == "en":
            raw_q = raw_q[0].lower() + raw_q[1:] if raw_q else raw_q
        follow_up = POLITE_OPENER.get(lang_code, "") + raw_q
    else:
        follow_up = None

    # Rejected/invalid values: show format hint and re-ask that field (no confirmation prefix)
    if rejected_fields:
        first_rejected = rejected_fields[0]
        hint = rejected.get(first_rejected, "")
        follow_up = f"{hint} {lang_questions.get(first_rejected, FIELD_QUESTIONS.get(first_rejected, 'Please provide a valid value.'))}"

    # Build confirmation prefix for newly extracted / updated fields
    labels = FIELD_LABELS.get(lang_code, FIELD_LABELS["en"])
    confirm_parts = []
    for k, v in merged_farmer.items():
        if not v:
            continue
        if not filled_farmer.get(k):
            confirm_parts.append(labels.get(k, k))
        elif filled_farmer.get(k) != v:
            confirm_parts.append(labels.get(k, k))
    for k, v in merged_farm.items():
        if not v:
            continue
        if not filled_farm.get(k):
            confirm_parts.append(labels.get(k, k))
        elif filled_farm.get(k) != v:
            confirm_parts.append(labels.get(k, k))

    if confirm_parts and follow_up and not rejected_fields:
        unique_parts = list(dict.fromkeys(confirm_parts))
        follow_up = CONFIRM_PREFIX.get(lang_code, "Got it! ") + "(" + ", ".join(unique_parts) + ") " + follow_up
    elif confirm_parts and not follow_up and not rejected_fields:
        unique_parts = list(dict.fromkeys(confirm_parts))
        done_msgs = {"en": "All details collected!", "hi": "सारी जानकारी दर्ज हो गई!",
                     "kn": "ಎಲ್ಲಾ ವಿವರಗಳು ದಾಖಲಾಗಿವೆ!", "te": "అన్ని వివరాలు నమోదయ్యాయి!",
                     "ta": "அனைத்து விவரங்களும் பதிவாகின!", "mr": "सर्व माहिती दर्ज झाली!",
                     "pa": "ਸਾਰੀ ਜਾਣਕਾਰੀ ਦਰਜ ਹੋ ਗਈ!"}
        follow_up = CONFIRM_PREFIX.get(lang_code, "Got it! ") + "(" + ", ".join(unique_parts) + ") " + done_msgs.get(lang_code, "All details collected!")

    total_elapsed = (time.time() - t_total_start) * 1000
    pre_model_elapsed = (t_model_start - t_total_start) * 1000
    post_model_elapsed = (time.time() - t_model_start - model_elapsed / 1000) * 1000
    timing_info = {
        "total_ms": round(total_elapsed, 1),
        "model_ms": round(model_elapsed, 1),
        "pre_model_ms": round(pre_model_elapsed, 1),
        "post_model_ms": round(post_model_elapsed, 1),
        "json_parse_ms": round(parse_elapsed, 1),
    }
    log.info("LATENCY total=%.0fms model=%.0fms pre_model=%.0fms post_model=%.0fms",
             total_elapsed, model_elapsed, pre_model_elapsed, post_model_elapsed)

    return {
        "farmer": merged_farmer,
        "farm": merged_farm,
        "missing_fields": still_missing,
        "follow_up_question": follow_up,
        "current_field": field_hint,
        "complete": len(still_missing) == 0,
        "timing": timing_info,
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

@app.get("/tts")
def text_to_speech(text: str = "Hello", language: str = "en"):
    try:
        from gtts import gTTS
        lang_code = language.split("-")[0] if language else "en"
        tts = gTTS(text=text, lang=lang_code)
        buf = io.BytesIO()
        tts.write_to_fp(buf)
        buf.seek(0)
        return Response(content=buf.read(), media_type="audio/mpeg")
    except Exception as e:
        raise HTTPException(500, f"TTS failed: {e}")

@app.get("/")
def root():
    return {
        "service": "Farmer Onboarding API",
        "status": "ok",
        "endpoints": ["/health", "/tts", "/onboarding", "/onboarding/health", "/voice", "/voice_done"],
        "ui": os.environ.get("STREAMLIT_URL", "https://65.0.181.84:8503"),
    }

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
