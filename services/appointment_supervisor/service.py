from __future__ import annotations

import copy
import logging
import uuid
from base64 import b64encode
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from services.common import reply_words
from services.common.draft_supervisor import (
    DraftSupervisor,
    SUPPORTED_LANGUAGES,
    _UNSET,
    _lang,
)
from services.flokiq_sync import client as flokiq_sync
from services.llm_service.bedrock_adapter import BedrockTextAdapter, TaskTier, generate_health_recommendation
from services.voice_agent.orchestrator import APPOINTMENT_FIELD_LABELS, process_text_input
from services.voice_agent.session_store import clear_session, get_session, update_session
from services.voice_agent.tts import synthesize_speech
from storage import (
    append_ai_health_log,
    append_appointment,
    append_health_log,
    animals_for_farmer,
    merge_app_animals,
)


_log = logging.getLogger("appointment_supervisor")
if not _log.handlers:
    _log.addHandler(logging.StreamHandler())
    _log.setLevel(logging.INFO)

# SUPPORTED_LANGUAGES / _UNSET / _lang re-exported from services.common.draft_supervisor
# so existing external imports (`from services.appointment_supervisor.service
# import SUPPORTED_LANGUAGES`, etc.) keep working unchanged.
REQUIRED_FIELDS = ("animal_identifier", "issue", "date", "time")

_TEXT = {
    "en": {
        "welcome": "Hello. Please tell me the animal name or tag, the issue and symptoms, and your preferred appointment date and time.",
        "correct": "I understood: {summary}",
        "updated": "Updated: {summary}",
        "yes_missing": "Please provide {field}.",
        "ready": "All required details are complete. Would you like to submit this appointment?",
        "submit_yes": "Please say submit when you are ready to save the appointment.",
        "submitted": "The appointment and animal health record were saved successfully.",
        "submitted_sync_failed": "Your appointment is saved here, but I could not send it to the app right now. Please check the app later.",
        "animal_not_found": "I could not find an animal named or tagged '{identifier}' registered to you. Your registered animals are: {animals}. Please tell me the correct name, tag, or ID.",
        "no_animals_registered": "You do not have any animals registered yet, so I cannot match '{identifier}' to one. Please register an animal first, or ask a human vet directly.",
        "no": "What would you like to correct?",
        "cancelled": "The appointment draft was cancelled and not submitted.",
        "missing_animal_identifier": "the animal name, tag, or ID",
        "missing_issue": "the animal issue and symptoms",
        "missing_date": "the preferred appointment date",
        "missing_time": "the preferred appointment time",
    },
    "hi": {
        "welcome": "नमस्ते। कृपया पशु का नाम या टैग, समस्या और लक्षण, तथा अपॉइंटमेंट की पसंदीदा तारीख और समय बताएं।",
        "correct": "मैंने समझा: {summary}",
        "updated": "अपडेट किया गया: {summary}",
        "yes_missing": "कृपया {field} बताएं।",
        "ready": "सभी जरूरी जानकारी पूरी है। क्या आप अपॉइंटमेंट जमा करना चाहते हैं?",
        "submit_yes": "सेव करने के लिए कृपया सबमिट कहें।",
        "submitted": "अपॉइंटमेंट और पशु स्वास्थ्य रिकॉर्ड सफलतापूर्वक सेव हो गए हैं।",
        "submitted_sync_failed": "आपका अपॉइंटमेंट यहाँ सेव है, लेकिन मैं इसे अभी ऐप में नहीं भेज सका। कृपया बाद में ऐप देखें।",
        "animal_not_found": "मुझे आपके नाम पर '{identifier}' नाम या टैग वाला कोई पशु नहीं मिला। आपके पंजीकृत पशु हैं: {animals}। कृपया सही नाम, टैग या आईडी बताएं।",
        "no_animals_registered": "आपके नाम पर अभी कोई पशु पंजीकृत नहीं है, इसलिए मैं '{identifier}' का मिलान नहीं कर सकता। कृपया पहले एक पशु पंजीकृत करें।",
        "no": "आप किस जानकारी को सुधारना चाहते हैं?",
        "cancelled": "अपॉइंटमेंट ड्राफ्ट रद्द कर दिया गया है और सेव नहीं किया गया।",
        "missing_animal_identifier": "पशु का नाम, टैग या आईडी",
        "missing_issue": "पशु की समस्या और लक्षण",
        "missing_date": "अपॉइंटमेंट की तारीख",
        "missing_time": "अपॉइंटमेंट का समय",
    },
    "mr": {
        "welcome": "नमस्कार. कृपया जनावराचे नाव किंवा टॅग, समस्या आणि लक्षणे, तसेच अपॉइंटमेंटची पसंतीची तारीख आणि वेळ सांगा.",
        "correct": "मला समजले: {summary}",
        "updated": "अपडेट केले: {summary}",
        "yes_missing": "कृपया {field} सांगा.",
        "ready": "सर्व आवश्यक माहिती पूर्ण आहे. तुम्हाला अपॉइंटमेंट सबमिट करायची आहे का?",
        "submit_yes": "सेव्ह करण्यासाठी कृपया सबमिट म्हणा.",
        "submitted": "अपॉइंटमेंट आणि जनावराचा आरोग्य रेकॉर्ड यशस्वीरित्या सेव्ह झाला आहे.",
        "submitted_sync_failed": "तुमचे अपॉइंटमेंट येथे सेव्ह झाले आहे, पण मी ते आता अ‍ॅपमध्ये पाठवू शकलो नाही. कृपया नंतर अ‍ॅप तपासा.",
        "animal_not_found": "तुमच्या नावावर '{identifier}' नाव किंवा टॅग असलेले कोणतेही जनावर सापडले नाही. तुमची नोंदणीकृत जनावरे: {animals}. कृपया योग्य नाव, टॅग किंवा आयडी सांगा.",
        "no_animals_registered": "तुमच्या नावावर अजून कोणतेही जनावर नोंदणीकृत नाही, त्यामुळे मी '{identifier}' जुळवू शकत नाही. कृपया आधी एखादे जनावर नोंदणी करा.",
        "no": "तुम्हाला कोणती माहिती दुरुस्त करायची आहे?",
        "cancelled": "अपॉइंटमेंटचा मसुदा रद्द केला आहे आणि सेव्ह केलेला नाही.",
        "missing_animal_identifier": "जनावराचे नाव, टॅग किंवा आयडी",
        "missing_issue": "जनावराची समस्या आणि लक्षणे",
        "missing_date": "अपॉइंटमेंटची तारीख",
        "missing_time": "अपॉइंटमेंटची वेळ",
    },
    "ml": {
        "welcome": "നമസ്കാരം. ദയവായി മൃഗത്തിന്റെ പേര് അല്ലെങ്കിൽ ടാഗ്, പ്രശ്നവും ലക്ഷണങ്ങളും, അപ്പോയിന്റ്മെന്റിന് ഇഷ്ടമുള്ള തീയതിയും സമയവും പറയൂ.",
        "correct": "എനിക്ക് മനസ്സിലായത്: {summary}",
        "updated": "പുതുക്കി: {summary}",
        "yes_missing": "ദയവായി {field} പറയൂ.",
        "ready": "ആവശ്യമായ എല്ലാ വിവരങ്ങളും പൂർണ്ണമാണ്. ഈ അപ്പോയിന്റ്മെന്റ് സമർപ്പിക്കണോ?",
        "submit_yes": "സേവ് ചെയ്യാൻ തയ്യാറാകുമ്പോൾ 'സമർപ്പിക്കുക' എന്ന് പറയൂ.",
        "submitted": "അപ്പോയിന്റ്മെന്റും മൃഗത്തിന്റെ ആരോഗ്യ രേഖയും വിജയകരമായി സേവ് ചെയ്തു.",
        "submitted_sync_failed": "നിങ്ങളുടെ അപ്പോയിന്റ്മെന്റ് ഇവിടെ സേവ് ചെയ്തിട്ടുണ്ട്, പക്ഷേ ഇപ്പോൾ ആപ്പിലേക്ക് അയയ്ക്കാൻ കഴിഞ്ഞില്ല. ദയവായി പിന്നീട് ആപ്പ് പരിശോധിക്കൂ.",
        "animal_not_found": "നിങ്ങളുടെ പേരിൽ '{identifier}' എന്ന പേരോ ടാഗോ ഉള്ള മൃഗമില്ല. നിങ്ങൾ രജിസ്റ്റർ ചെയ്ത മൃഗങ്ങൾ: {animals}. ദയവായി ശരിയായ പേര്, ടാഗ് അല്ലെങ്കിൽ ഐഡി പറയൂ.",
        "no_animals_registered": "നിങ്ങളുടെ പേരിൽ ഇതുവരെ ഒരു മൃഗവും രജിസ്റ്റർ ചെയ്തിട്ടില്ല, അതിനാൽ '{identifier}' കണ്ടെത്താനായില്ല. ആദ്യം ഒരു മൃഗത്തെ രജിസ്റ്റർ ചെയ്യൂ.",
        "no": "ഏത് വിവരമാണ് തിരുത്തേണ്ടത്?",
        "cancelled": "അപ്പോയിന്റ്മെന്റ് ഡ്രാഫ്റ്റ് റദ്ദാക്കി, സേവ് ചെയ്തിട്ടില്ല.",
        "missing_animal_identifier": "മൃഗത്തിന്റെ പേര്, ടാഗ് അല്ലെങ്കിൽ ഐഡി",
        "missing_issue": "മൃഗത്തിന്റെ പ്രശ്നവും ലക്ഷണങ്ങളും",
        "missing_date": "അപ്പോയിന്റ്മെന്റ് തീയതി",
        "missing_time": "അപ്പോയിന്റ്മെന്റ് സമയം",
    },
    "ta": {
        "welcome": "வணக்கம். விலங்கின் பெயர் அல்லது குறிச்சொல், பிரச்சினை மற்றும் அறிகுறிகள், விருப்பமான சந்திப்பு தேதி மற்றும் நேரத்தைச் சொல்லுங்கள்.",
        "correct": "நான் புரிந்துகொண்டது: {summary}",
        "updated": "புதுப்பிக்கப்பட்டது: {summary}",
        "yes_missing": "தயவுசெய்து {field} தெரிவிக்கவும்.",
        "ready": "தேவையான தகவல்கள் அனைத்தும் உள்ளன. இந்த சந்திப்பை சமர்ப்பிக்கவா?",
        "submit_yes": "சேமிக்க தயாரானதும் சமர்ப்பிக்கவும் என்று சொல்லுங்கள்.",
        "submitted": "சந்திப்பு மற்றும் விலங்கு சுகாதார பதிவு வெற்றிகரமாக சேமிக்கப்பட்டது.",
        "submitted_sync_failed": "உங்கள் சந்திப்பு இங்கே சேமிக்கப்பட்டுள்ளது, ஆனால் இப்போது ஆப்பிற்கு அனுப்ப முடியவில்லை. தயவுசெய்து பின்னர் ஆப்பைப் பார்க்கவும்.",
        "animal_not_found": "'{identifier}' என்ற பெயர் அல்லது டேக் கொண்ட விலங்கு உங்கள் பெயரில் இல்லை. உங்கள் பதிவு செய்யப்பட்ட விலங்குகள்: {animals}. சரியான பெயர், டேக் அல்லது ஐடி தெரிவிக்கவும்.",
        "no_animals_registered": "உங்கள் பெயரில் இதுவரை எந்த விலங்கும் பதிவு செய்யப்படவில்லை, எனவே '{identifier}' ஐ பொருத்த முடியவில்லை. முதலில் ஒரு விலங்கைப் பதிவு செய்யவும்.",
        "no": "எந்த தகவலை திருத்த வேண்டும்?",
        "cancelled": "சந்திப்பு வரைவு ரத்து செய்யப்பட்டது.",
        "missing_animal_identifier": "விலங்கின் பெயர், குறிச்சொல் அல்லது ஐடி",
        "missing_issue": "விலங்கின் பிரச்சினை மற்றும் அறிகுறிகள்",
        "missing_date": "சந்திப்பு தேதி",
        "missing_time": "சந்திப்பு நேரம்",
    },
    "te": {
        "welcome": "నమస్కారం. జంతువు పేరు లేదా ట్యాగ్, సమస్య మరియు లక్షణాలు, మీకు కావలసిన అపాయింట్‌మెంట్ తేదీ మరియు సమయాన్ని చెప్పండి.",
        "correct": "నేను అర్థం చేసుకున్నది: {summary}. ఇది సరైనదేనా?",
        "updated": "వివరాలు నవీకరించబడ్డాయి. {summary} ఇది సరైనదేనా?",
        "yes_missing": "దయచేసి {field} చెప్పండి.",
        "ready": "అవసరమైన వివరాలు పూర్తయ్యాయి. ఈ అపాయింట్‌మెంట్‌ను సమర్పించాలా?",
        "submit_yes": "సేవ్ చేయడానికి సిద్ధంగా ఉన్నప్పుడు సబ్మిట్ అని చెప్పండి.",
        "submitted": "అపాయింట్‌మెంట్ మరియు జంతు ఆరోగ్య రికార్డు విజయవంతంగా సేవ్ చేయబడ్డాయి.",
        "submitted_sync_failed": "మీ అపాయింట్‌మెంట్ ఇక్కడ సేవ్ చేయబడింది, కానీ దీన్ని ఇప్పుడు యాప్‌కు పంపలేకపోయాను. దయచేసి తర్వాత యాప్‌ను చూడండి.",
        "animal_not_found": "'{identifier}' అనే పేరు లేదా ట్యాగ్ ఉన్న జంతువు మీ పేరు మీద కనిపించలేదు. మీ నమోదిత జంతువులు: {animals}. దయచేసి సరైన పేరు, ట్యాగ్ లేదా ఐడి చెప్పండి.",
        "no_animals_registered": "మీ పేరు మీద ఇంకా ఏ జంతువు నమోదు కాలేదు, కాబట్టి '{identifier}' సరిపోల్చలేను. దయచేసి ముందుగా ఒక జంతువును నమోదు చేయండి.",
        "no": "ఏ వివరాన్ని సరిచేయాలి?",
        "cancelled": "అపాయింట్‌మెంట్ డ్రాఫ్ట్ రద్దు చేయబడింది.",
        "missing_animal_identifier": "జంతువు పేరు, ట్యాగ్ లేదా ఐడి",
        "missing_issue": "జంతువు సమస్య మరియు లక్షణాలు",
        "missing_date": "అపాయింట్‌మెంట్ తేదీ",
        "missing_time": "అపాయింట్‌మెంట్ సమయం",
    },
    "kn": {
        "welcome": "ನಮಸ್ಕಾರ. ಪ್ರಾಣಿಯ ಹೆಸರು ಅಥವಾ ಟ್ಯಾಗ್, ಸಮಸ್ಯೆ ಮತ್ತು ಲಕ್ಷಣಗಳು, ನಿಮ್ಮ ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ದಿನಾಂಕ ಮತ್ತು ಸಮಯವನ್ನು ತಿಳಿಸಿ.",
        "correct": "ನಾನು ಅರ್ಥಮಾಡಿಕೊಂಡದ್ದು: {summary}. ಇದು ಸರಿಯೇ?",
        "updated": "ವಿವರಗಳನ್ನು ನವೀಕರಿಸಲಾಗಿದೆ. {summary} ಇದು ಸರಿಯೇ?",
        "yes_missing": "ದಯವಿಟ್ಟು {field} ತಿಳಿಸಿ.",
        "ready": "ಅಗತ್ಯ ವಿವರಗಳು ಪೂರ್ಣಗೊಂಡಿವೆ. ಈ ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ಸಲ್ಲಿಸಬೇಕೇ?",
        "submit_yes": "ಉಳಿಸಲು ಸಿದ್ಧವಾದಾಗ ಸಬ್ಮಿಟ್ ಎಂದು ಹೇಳಿ.",
        "submitted": "ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ಮತ್ತು ಪ್ರಾಣಿಯ ಆರೋಗ್ಯ ದಾಖಲೆ ಯಶಸ್ವಿಯಾಗಿ ಉಳಿಸಲಾಗಿದೆ.",
        "submitted_sync_failed": "ನಿಮ್ಮ ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ಇಲ್ಲಿ ಉಳಿಸಲಾಗಿದೆ, ಆದರೆ ಇದನ್ನು ಈಗ ಅಪ್ಲಿಕೇಶನ್‌ಗೆ ಕಳುಹಿಸಲು ಸಾಧ್ಯವಾಗಲಿಲ್ಲ. ದಯವಿಟ್ಟು ನಂತರ ಅಪ್ಲಿಕೇಶನ್ ಪರಿಶೀಲಿಸಿ.",
        "animal_not_found": "'{identifier}' ಎಂಬ ಹೆಸರು ಅಥವಾ ಟ್ಯಾಗ್ ಇರುವ ಪ್ರಾಣಿ ನಿಮ್ಮ ಹೆಸರಿನಲ್ಲಿ ಕಂಡುಬಂದಿಲ್ಲ. ನಿಮ್ಮ ನೋಂದಾಯಿತ ಪ್ರಾಣಿಗಳು: {animals}. ದಯವಿಟ್ಟು ಸರಿಯಾದ ಹೆಸರು, ಟ್ಯಾಗ್ ಅಥವಾ ಐಡಿ ತಿಳಿಸಿ.",
        "no_animals_registered": "ನಿಮ್ಮ ಹೆಸರಿನಲ್ಲಿ ಇನ್ನೂ ಯಾವುದೇ ಪ್ರಾಣಿ ನೋಂದಣಿಯಾಗಿಲ್ಲ, ಆದ್ದರಿಂದ '{identifier}' ಅನ್ನು ಹೊಂದಿಸಲು ಸಾಧ್ಯವಿಲ್ಲ. ದಯವಿಟ್ಟು ಮೊದಲು ಒಂದು ಪ್ರಾಣಿಯನ್ನು ನೋಂದಾಯಿಸಿ.",
        "no": "ಯಾವ ವಿವರವನ್ನು ಸರಿಪಡಿಸಬೇಕು?",
        "cancelled": "ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ಕರಡು ರದ್ದುಗೊಳಿಸಲಾಗಿದೆ.",
        "missing_animal_identifier": "ಪ್ರಾಣಿಯ ಹೆಸರು, ಟ್ಯಾಗ್ ಅಥವಾ ಐಡಿ",
        "missing_issue": "ಪ್ರಾಣಿಯ ಸಮಸ್ಯೆ ಮತ್ತು ಲಕ್ಷಣಗಳು",
        "missing_date": "ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ದಿನಾಂಕ",
        "missing_time": "ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ಸಮಯ",
    },
}

# Said after answering a side question (a weather or farm-data question
# asked while a booking is open), so the farmer knows the booking is still
# waiting and what it needs next. See _side_question_response().
_STILL_OPEN = {
    "en": "Your appointment booking is still open: {summary}",
    "hi": "आपकी अपॉइंटमेंट बुकिंग अभी खुली है: {summary}",
    "mr": "तुमची अपॉइंटमेंट बुकिंग अजून सुरू आहे: {summary}",
    "ta": "உங்கள் சந்திப்பு முன்பதிவு இன்னும் திறந்துள்ளது: {summary}",
    "te": "మీ అపాయింట్‌మెంట్ బుకింగ్ ఇంకా తెరిచి ఉంది: {summary}",
    "kn": "ನಿಮ್ಮ ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ಬುಕಿಂಗ್ ಇನ್ನೂ ತೆರೆದಿದೆ: {summary}",
    "ml": "നിങ്ങളുടെ അപ്പോയിന്റ്മെന്റ് ബുക്കിംഗ് ഇപ്പോഴും തുറന്നിരിക്കുന്നു: {summary}",
}

_LABELS = {
    "en": {"animal_identifier": "animal", "issue": "issue", "symptoms": "symptoms", "duration": "duration", "severity": "severity", "date": "date", "time": "time", "notes": "notes"},
    "hi": {"animal_identifier": "पशु", "issue": "समस्या", "symptoms": "लक्षण", "duration": "अवधि", "severity": "गंभीरता", "date": "तारीख", "time": "समय", "notes": "नोट्स"},
    "ta": {"animal_identifier": "விலங்கு", "issue": "பிரச்சினை", "symptoms": "அறிகுறிகள்", "duration": "காலம்", "severity": "தீவிரம்", "date": "தேதி", "time": "நேரம்", "notes": "குறிப்புகள்"},
    "te": {"animal_identifier": "జంతువు", "issue": "సమస్య", "symptoms": "లక్షణాలు", "duration": "వ్యవధి", "severity": "తీవ్రత", "date": "తేదీ", "time": "సమయం", "notes": "గమనికలు"},
    "kn": {"animal_identifier": "ಪ್ರಾಣಿ", "issue": "ಸಮಸ್ಯೆ", "symptoms": "ಲಕ್ಷಣಗಳು", "duration": "ಅವಧಿ", "severity": "ತೀವ್ರತೆ", "date": "ದಿನಾಂಕ", "time": "ಸಮಯ", "notes": "ಟಿಪ್ಪಣಿಗಳು"},
    "mr": {"animal_identifier": "जनावर", "issue": "समस्या", "symptoms": "लक्षणे", "duration": "कालावधी", "severity": "तीव्रता", "date": "तारीख", "time": "वेळ", "notes": "टिपा"},
    "ml": {"animal_identifier": "മൃഗം", "issue": "പ്രശ്നം", "symptoms": "ലക്ഷണങ്ങൾ", "duration": "കാലയളവ്", "severity": "തീവ്രത", "date": "തീയതി", "time": "സമയം", "notes": "കുറിപ്പുകൾ"},
}

_VALUES = {
    "hi": {"not eating": "खाना नहीं खा रहा", "lethargy": "सुस्ती", "fever": "बुखार", "swelling": "सूजन", "limping": "लंगड़ाना", "wound": "घाव", "not drinking": "पानी नहीं पी रहा"},
    "ta": {"not eating": "சாப்பிடவில்லை", "lethargy": "சோர்வு", "fever": "காய்ச்சல்", "swelling": "வீக்கம்", "limping": "நொண்டுதல்", "wound": "காயம்", "not drinking": "தண்ணீர் குடிக்கவில்லை"},
    "te": {"not eating": "తినడం లేదు", "lethargy": "నీరసం", "fever": "జ్వరం", "swelling": "వాపు", "limping": "కుంటుతూ నడవడం", "wound": "గాయం", "not drinking": "నీరు తాగడం లేదు"},
    "kn": {"not eating": "ತಿನ್ನುತ್ತಿಲ್ಲ", "lethargy": "ಸುಸ್ತು", "fever": "ಜ್ವರ", "swelling": "ಊತ", "limping": "ಕುಂಟುವುದು", "wound": "ಗಾಯ", "not drinking": "ನೀರು ಕುಡಿಯುತ್ತಿಲ್ಲ"},
    "mr": {"not eating": "खात नाही", "lethargy": "सुस्ती", "fever": "ताप", "swelling": "सूज", "limping": "लंगडणे", "wound": "जखम", "not drinking": "पाणी पीत नाही"},
    "ml": {"not eating": "തിന്നുന്നില്ല", "lethargy": "ക്ഷീണം", "fever": "പനി", "swelling": "വീക്കം", "limping": "മുടന്ത്", "wound": "മുറിവ്", "not drinking": "വെള്ളം കുടിക്കുന്നില്ല"},
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def process_query(text: str, farmer_id: str) -> dict[str, Any]:
    """Thin wrapper around query_agent.adk_agent.process_query_adk (the
    off-topic-probe call in turn(), below). A real module-level function --
    not a re-exported name -- so tests can monkeypatch service.process_query
    the same way they always have. The import is deferred to call time:
    adk_agent.py pulls in google.adk at module load (needs Python 3.10+),
    and this file must stay importable under an older interpreter for
    every other code path that never reaches this probe."""
    from services.query_agent.adk_agent import process_query_adk
    return process_query_adk(text, farmer_id)


# Furthest ahead a booking may be. A date outside today..today+365 is
# treated as "not provided" and re-asked (see _valid_appointment_date).
_MAX_APPOINTMENT_DAYS_AHEAD = 365


def _now_ist() -> datetime:
    """Current date and time in India (IST, UTC+5:30)."""
    from datetime import timedelta, timezone
    return datetime.now(timezone(timedelta(hours=5, minutes=30)))


def _today_ist():
    """Today's date in India -- the same "today" the extraction prompt's
    calendar is built from (bedrock_adapter.build_prompt)."""
    return _now_ist().date()


def _appointment_day(value: Any):
    """'today' / 'tomorrow' / 'yesterday' or a real YYYY-MM-DD -> that
    date (IST). Anything else -> None."""
    if not isinstance(value, str):
        return None
    from datetime import timedelta
    relative = {"today": 0, "tomorrow": 1, "yesterday": -1}
    if value in relative:
        return _today_ist() + timedelta(days=relative[value])
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _valid_appointment_date(value: Any) -> bool:
    """Real bug, found live: the extraction schema now instructs the model
    not to guess a date from ambiguous input, but a prompt instruction is
    not a guarantee -- this is the deterministic backstop. Rejects
    anything that isn't 'today'/'tomorrow'/'yesterday' or a real
    YYYY-MM-DD calendar date, so a bad guess gets treated as "not
    provided" (re-asked) instead of silently stored.

    Also rejects a booking date before today or more than
    _MAX_APPOINTMENT_DAYS_AHEAD days ahead (IST). A visit can't be booked
    in the past, and "fever since yesterday" must not become the booking
    date. Only bookings use this check -- health logs and birth dates
    keep accepting past dates."""
    day = _appointment_day(value)
    if day is None:
        return False
    from datetime import timedelta
    today = _today_ist()
    if day < today or day > today + timedelta(days=_MAX_APPOINTMENT_DAYS_AHEAD):
        import logging
        logging.getLogger(__name__).warning(
            "appointment date rejected (outside today..+%d days): %s",
            _MAX_APPOINTMENT_DAYS_AHEAD, value)
        return False
    return True


def _valid_appointment_time(value: Any) -> bool:
    """Same backstop for time -- rejects anything that isn't a real
    24-hour HH:MM (e.g. the literal live bug: '66' as input must never
    reach storage as a fabricated '06:00')."""
    if not isinstance(value, str):
        return False
    try:
        datetime.strptime(value, "%H:%M")
        return True
    except ValueError:
        return False


# Kill switch for the check below: APPOINTMENT_PAST_TIME_CHECK=0 turns it off.
_PAST_TIME_CHECK_ENV = "APPOINTMENT_PAST_TIME_CHECK"


def _time_already_passed(date_value: Any, time_value: Any) -> bool:
    """True when the booking is for today (IST) at a time that is already
    over, e.g. "today at 5 pm" said at 7 pm. _valid_appointment_date and
    _valid_appointment_time each check one value alone, so neither can see
    this. The current minute still counts as not passed."""
    import os
    if os.getenv(_PAST_TIME_CHECK_ENV, "1").strip().lower() in ("0", "false", "no", "off"):
        return False
    if _appointment_day(date_value) != _today_ist():
        return False
    try:
        wanted = datetime.strptime(str(time_value), "%H:%M").time()
    except ValueError:
        return False
    now = _now_ist()
    return (wanted.hour, wanted.minute) < (now.hour, now.minute)


_ANIMAL_MATCH_TOOL_SPEC = {
    "name": "match_animal",
    "description": "Pick which registered animal (if any) the farmer is referring to.",
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "matched_animal_id": {
                    "type": ["string", "null"],
                    "description": (
                        "The internal id of the single registered animal the farmer most "
                        "likely means, accounting for typos, extra words, or a natural "
                        "shortening of a real tag/name. Null if no animal is a confident, "
                        "SPECIFIC match -- e.g. if the farmer's identifier is equally "
                        "consistent with many different registered animals (ambiguous), "
                        "or matches none of them at all. Never guess when multiple animals "
                        "are equally plausible; only match when one animal is clearly the "
                        "best fit."
                    ),
                },
                "candidate_animal_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "ONLY populate when matched_animal_id is null because of ambiguity "
                        "(ignore this field entirely for a genuine no-match). List the ids "
                        "of the specific animals that are plausible matches for what the "
                        "farmer said -- e.g. if they said a shared prefix, list every "
                        "animal whose tag contains that prefix, not the farmer's whole "
                        "herd. This narrows what the farmer gets asked next; leave empty "
                        "if truly nothing plausible."
                    ),
                },
            },
            "required": ["matched_animal_id"],
        }
    },
}

_ANIMAL_MATCH_SYSTEM = (
    "You match a farmer's stated animal identifier to their real registered "
    "animals. Account for typos, extra words around a name, or a natural "
    "shortening of a real tag. Do NOT guess when the identifier could "
    "equally plausibly refer to several different animals -- e.g. if many "
    "registered tags share a common prefix or substring, a bare fragment "
    "of that shared part does not specifically identify any one of them. "
    "Only match when exactly one animal is clearly, specifically intended. "
    "When it's ambiguous rather than a total non-match, list the specific "
    "plausible candidates in candidate_animal_ids so the farmer can be "
    "asked to pick from a short, relevant list instead of their entire "
    "herd."
)


def _resolve_animal_id(wanted: str, animals: list) -> tuple[Optional[str], list]:
    """Exact match (case-insensitive) is tried first by the caller -- this
    is the fallback when that fails. Real bug this replaces: submit() used
    to give up the instant `wanted` didn't exactly equal a real id/tag
    string, even for a farmer's entirely reasonable guess ("tag 001" after
    being told real tags look like "TAG-001-1") -- a rigid rule-based
    string comparison with no actual understanding of what the farmer
    meant. This asks the model instead, given the real animal list.

    Returns (matched_id, candidate_ids). matched_id is set only for a
    confident, specific match. candidate_ids is a short, relevant shortlist
    for the ambiguous case (e.g. every tag sharing the fragment the farmer
    said) -- so the farmer gets asked to narrow among a handful of real
    possibilities instead of being shown their entire herd, which is the
    same "we're the intelligence, use it" complaint that motivated
    resolving the identifier at all instead of a flat not-found dump."""
    if not wanted or not animals:
        return None, []
    catalog = "\n".join(
        f"- id={a.id}, tag_or_name={a.tag_or_name}, species={getattr(a, 'species', '')}, breed={getattr(a, 'breed', '')}"
        for a in animals
    )
    prompt = f"""Farmer said the animal is: "{wanted}"

Registered animals for this farmer:
{catalog}

Which one (if any) does the farmer mean?"""
    try:
        adapter = BedrockTextAdapter(task=TaskTier.EXTRACTION)
        result = adapter.converse_with_tool(
            messages=[{"role": "user", "content": prompt}],
            tool_spec=_ANIMAL_MATCH_TOOL_SPEC,
            system=_ANIMAL_MATCH_SYSTEM,
            tool_choice_name="match_animal",
        )
        tool_input = result.get("tool_input") or {}
        valid_ids = {a.id for a in animals}
        matched_id = tool_input.get("matched_animal_id")
        matched_id = matched_id if matched_id in valid_ids else None
        candidates = [c for c in (tool_input.get("candidate_animal_ids") or []) if c in valid_ids]
        return matched_id, candidates
    except Exception as exc:
        # Real bug, found in code review: this swallowed every exception
        # (Bedrock throttling, expired credentials, misconfigured region)
        # with zero logging -- an outage was indistinguishable from a
        # normal "no match" case, both producing the same silent (None,
        # []) with nothing in the logs to tell them apart on-call.
        _log.warning("animal fuzzy-match failed wanted=%r: %s", wanted, exc)
        return None, []


def _verify_animal(identifier: str, animals: list) -> tuple[Optional[Any], list]:
    """Shared by the early-verification step in turn() and submit()'s
    defensive fallback. Exact match (case-insensitive) first, then the LLM
    resolver for typos/partial tags. Returns (matched_animal_or_None,
    shortlist_of_candidates_or_empty)."""
    # str() coercion matters: the extraction model doesn't strictly follow
    # its declared JSON schema (animal_tag is typed "string", but that's not
    # runtime-enforced -- _KEY_ALIASES elsewhere in this codebase exists
    # precisely because models sometimes deviate). A bare numeric ear-tag
    # coming back as a JSON number instead of a string would otherwise raise
    # AttributeError here, uncaught (main.py only catches ValueError around
    # this call path) -> a raw 500. submit()'s own inline matching already
    # did this coercion; this shared helper had been missing it.
    wanted = str(identifier).lower()
    exact = [a for a in animals if wanted in {a.id.lower(), a.tag_or_name.lower()}]
    if exact:
        return exact[0], []
    matched_id, candidate_ids = _resolve_animal_id(identifier, animals)
    by_id = {a.id: a for a in animals}
    matched = by_id.get(matched_id) if matched_id else None
    candidates = [by_id[c] for c in candidate_ids if c in by_id]
    return matched, candidates


_SYMPTOM_KEYS = ["not eating", "fever", "limping", "swelling", "not drinking"]
_OTHER_LABEL = {"en": "Other", "hi": "अन्य", "ta": "மற்றவை", "te": "ఇతర", "kn": "ಇತರ", "mr": "इतर", "ml": "മറ്റുള്ളവ"}


def _symptom_options(language: str) -> dict:
    """5 common symptom pills + Other, translated using the SAME vetted
    _VALUES vocabulary already used elsewhere in this file for rendering
    booking summaries -- not new, unverified translations."""
    lang = _lang(language)
    values_map = _VALUES.get(lang, {})
    choices = [values_map.get(k, k).capitalize() if lang == "en" else values_map.get(k, k) for k in _SYMPTOM_KEYS]
    return {"choices": choices, "other_label": _OTHER_LABEL.get(lang, "Other"), "other_allowed": True}


def _animal_options(language: str, animals: list) -> dict:
    lang = _lang(language)
    return {
        "choices": [a.tag_or_name for a in animals][:5],
        "other_label": _OTHER_LABEL.get(lang, "Other"),
        "other_allowed": True,
    }


class AppointmentSupervisor(DraftSupervisor):
    INTAKE_SUBDIR = "appointment_intakes"
    MESSAGES = _TEXT

    def _fresh(self, session_id: str, farmer_id: str, language: str) -> dict[str, Any]:
        return {
            "session_id": session_id,
            "farmer_id": farmer_id,
            "language": language if language in SUPPORTED_LANGUAGES else "en-IN",
            "state": "COLLECTING",
            "draft": {"symptoms": [], "attachments": [], "miscellaneous_notes": ""},
            "confirmed_fields": [],
            "transcript_history": [],
            "confirmation_history": [],
            "submitted": False,
            "created_at": _now(),
            "updated_at": _now(),
        }

    def _before_save(self, draft: dict[str, Any]) -> None:
        draft["updated_at"] = _now()

    def _copy_entities(self, draft: dict[str, Any], entities: dict[str, Any]) -> None:
        target = draft["draft"]
        for key, value in entities.items():
            if value in (None, "", []):
                continue
            # Deterministic backstop (see _valid_appointment_date/_time):
            # never let an objectively-invalid date/time value reach
            # storage, no matter what the extraction call returned --
            # treated as "not provided" so the missing-field flow re-asks.
            if key == "date" and not _valid_appointment_date(value):
                continue
            if key == "time" and not _valid_appointment_time(value):
                continue
            # Real bug, found in code review: this loop was writing
            # animal_id/animal_tag/animal_name here too, unconditionally,
            # BEFORE the verification-aware block below ever runs -- so an
            # already-verified animal_id could be silently overwritten by a
            # misread value (e.g. a bare "55" answering an unrelated date
            # question) regardless of expected_field or animal_verified.
            # submit() reads target["animal_id"] directly as an
            # already-trusted value, so a clobbered id here got saved
            # against the wrong animal with no verification at all. These
            # three keys are handled exclusively below, which already knows
            # how to check expected_field/animal_verified correctly --
            # never let this generic loop touch them.
            if key in ("animal_id", "animal_tag", "animal_name"):
                continue
            target[key] = value

        # Date and time are each valid on their own, but together they can
        # still point to a time today that is already over. Checked after
        # the loop, on what the draft now holds, so it works whichever turn
        # brought the date or the time. The time is dropped (re-asked), the
        # same way a past date is.
        if target.get("time") and _time_already_passed(target.get("date"), target.get("time")):
            _log.warning("appointment time rejected (already passed today): date=%s time=%s",
                         target.get("date"), target.get("time"))
            target.pop("time", None)

        # animal_tag/animal_name/animal_id are the extraction schema's
        # fields for a bare ear-tag, a name, or an internal record id --
        # REQUIRED_FIELDS only checks animal_identifier, so one of them
        # must bridge into it or a correctly-extracted value silently
        # never counts as having answered the question. animal_id is
        # bridged here too, never trusted directly -- real bug, found
        # live: extraction classified a made-up value ("FAKEANIMAL999") as
        # animal_id, which turn()'s early verification and submit() both
        # treat as already-resolved and never actually check against real
        # animals at all. Every raw extracted value, whichever field name
        # the model used, goes through the same verification; only a
        # value this class has itself confirmed sits in animal_id.
        raw_animal_ref = entities.get("animal_id") or entities.get("animal_tag") or entities.get("animal_name")
        # Real bug, found live (twice, independently): a bare/garbage number
        # given in answer to an UNRELATED pending question (date, time,
        # issue) was misread by extraction as a fresh animal reference, and
        # this branch unconditionally treated any animal-shaped value that
        # differs from the current one as a correction -- silently wiping
        # an already-verified animal mid-conversation, sometimes down to
        # nothing at all (when the misread value matched no real animal).
        # Only treat this as a genuine animal correction when the animal
        # field is actually the one being asked about (or nothing specific
        # is pending) -- never as a side effect of answering a different
        # field.
        expected_field = draft.get("expected_field")
        if (
            raw_animal_ref
            and draft.get("animal_verified")
            and raw_animal_ref != target.get("animal_identifier")
            and expected_field in (None, "animal_identifier")
        ):
            # A later turn named a different animal after one was already
            # verified (a correction) -- re-verify the new value instead
            # of silently keeping the stale one or trusting the new raw
            # value unchecked.
            draft["animal_verified"] = False
            target["animal_identifier"] = raw_animal_ref
            target.pop("animal_id", None)
        elif not draft.get("animal_verified") and not target.get("animal_identifier"):
            # raw_animal_ref (above) already reads straight from `entities`
            # -- target itself never holds animal_id/animal_tag/animal_name
            # (the generic loop above deliberately skips them), so read the
            # already-computed value rather than a target.get() that would
            # now always be None.
            if raw_animal_ref:
                target["animal_identifier"] = raw_animal_ref
        if target.get("issue") and not target.get("symptoms"):
                target["symptoms"] = [target["issue"]]

    @staticmethod
    def _names_new_animal(draft: dict[str, Any], entities: dict[str, Any]) -> bool:
        """True when this turn's extraction names an animal other than the
        one already verified. Compared case-insensitively against the
        verified name/tag, its id, and what the farmer first called it, so
        repeating the same animal in other case or script is not a change."""
        ref = entities.get("animal_id") or entities.get("animal_tag") or entities.get("animal_name")
        if not ref or not draft.get("animal_verified"):
            return False
        values = draft["draft"]
        known = {
            str(v).strip().casefold()
            for v in (values.get("animal_identifier"), values.get("animal_id"), draft.get("animal_said"))
            if v
        }
        return str(ref).strip().casefold() not in known

    @staticmethod
    def _changes_a_booking_field(draft: dict[str, Any], entities: dict[str, Any]) -> bool:
        """True when this turn's extraction carries a usable value for
        issue/symptoms/duration/severity/date/time that differs from what
        the draft already holds. Values that _copy_entities would refuse
        (a past date, an invalid time, a time already over today) do not
        count -- they would change nothing."""
        values = draft["draft"]
        for field in ("issue", "symptoms", "duration", "severity", "date", "time"):
            value = entities.get(field)
            if value in (None, "", []) or value == values.get(field):
                continue
            if field == "date" and _appointment_day(value) is None:
                continue
            if field == "date" and _appointment_day(value) < _today_ist():
                continue
            if field == "time" and (
                not _valid_appointment_time(value)
                or _time_already_passed(entities.get("date") or values.get("date"), value)
            ):
                continue
            return True
        return False

    @staticmethod
    def _turn_adds_to_booking(draft: dict[str, Any], confirmation_signal: Optional[str], entities: dict[str, Any],
                              names_new_animal: bool, answers_expected_field: bool) -> bool:
        """True when this turn plainly belongs to the booking: a yes/no/
        cancel/submit, an animal (a first one or a different one), an answer
        to the field the bot asked for, a new issue or symptom, or a date or
        time the booking is still missing. Entities repeated from the
        session cache (same value as the draft) do not count. A changed
        date or time on a booking that already has one is not counted here
        -- it may be a real correction or a word like "today" inside a
        question -- so that turn goes to the side-question check, and the
        classifier keeps it in the booking when it is a correction."""
        if confirmation_signal or names_new_animal or answers_expected_field:
            return True
        values = draft["draft"]
        if not draft.get("animal_verified") and (
            entities.get("animal_id") or entities.get("animal_tag") or entities.get("animal_name")
        ):
            return True
        for field in ("issue", "symptoms", "duration", "severity"):
            value = entities.get(field)
            if value not in (None, "", []) and value != values.get(field):
                return True
        for field in ("date", "time"):
            if entities.get(field) not in (None, "") and not values.get(field):
                return True
        return False

    def _reminder(self, draft: dict[str, Any]) -> str:
        """What the booking still needs, in the farmer's language: the
        details so far plus the next question (or the welcome text when
        nothing has been given yet)."""
        language = draft["language"]
        if not self._has_any_info(draft["draft"]):
            return self._message(language, "welcome")
        template = _STILL_OPEN.get(_lang(language)) or _STILL_OPEN["en"]
        text = template.format(summary=self._summary(draft))
        missing = self._missing(draft)
        if missing:
            field = self._message(language, f"missing_{missing[0]}")
            text = f"{text} {self._message(language, 'yes_missing', field=field)}"
        elif draft.get("state") == "READY_TO_SUBMIT":
            text = f"{text} {self._message(language, 'ready')}"
        return text

    def reminder(self, farmer_id: str, session_id: str, language: str = "en-IN") -> str:
        """Read-only: the reminder for this session's open booking. Used by
        the router when a turn goes to another agent without coming through
        turn() (a PIN answering the weather agent's question)."""
        with self._session_lock(farmer_id, session_id):
            return self._reminder(self._load(session_id, farmer_id, language))

    def _side_question_response(self, draft: dict[str, Any], cache_key: str, cache_before: Optional[dict],
                                side: str, answer: Optional[str], text: str, session_id: str) -> dict[str, Any]:
        """Leave the booking exactly as it was and hand the turn back to the
        router, which answers the question (weather) or uses `answer`
        (query) and adds the reminder. The draft is saved only to keep the
        transcript line; no field changes. No audio is made here: the router
        speaks the combined reply, so the result carries no
        response_audio_base64 key."""
        clear_session(cache_key)
        if cache_before:
            update_session(cache_key, cache_before)
        self._save(draft)
        reminder = self._reminder(draft)
        _log.info("appointment side question session=%s intent=%s state=%s", session_id, side, draft.get("state"))
        resp = self._response(draft, reminder, input_transcript=text, include_audio=False)
        resp.pop("response_audio_base64", None)
        resp.pop("audio_error", None)
        resp["side_question"] = side
        resp["side_answer"] = answer
        resp["reminder"] = reminder
        return resp

    def _missing(self, draft: dict[str, Any]) -> list[str]:
        values = draft["draft"]
        return [field for field in REQUIRED_FIELDS if not values.get(field)]

    def _has_any_info(self, values: dict[str, Any]) -> bool:
        return any(
            v not in (None, "", [])
            for k, v in values.items()
            if k not in ("attachments", "miscellaneous_notes")
        )

    def _summary(self, draft: dict[str, Any], only_fields: Optional[set[str]] = None) -> str:
        """only_fields restricts the readback to a subset (used for the
        per-turn spoken delta below, so audio says only what's new this
        turn instead of re-reading every field captured so far); None
        (the default) summarizes everything, as this always has."""
        values = draft["draft"]
        labels = _LABELS.get(_lang(draft["language"]), _LABELS["en"])
        values_map = _VALUES.get(_lang(draft["language"]), {})
        parts = []
        for field in ("animal_identifier", "issue", "symptoms", "duration", "severity", "date", "time"):
            if only_fields is not None and field not in only_fields:
                continue
            value = values.get(field)
            if value not in (None, "", []):
                if isinstance(value, list):
                    value = ", ".join(values_map.get(str(item), str(item)) for item in value)
                if isinstance(value, str):
                    value = values_map.get(value, value)
                parts.append(f"{labels.get(field, field)}: {value}")
        if values.get("miscellaneous_notes") and (only_fields is None or "miscellaneous_notes" in only_fields):
            parts.append(f"{labels['notes']}: {values['miscellaneous_notes']}")
        return "; ".join(parts) or "no appointment details yet"

    def _response(self, draft: dict[str, Any], text: str, input_transcript: str | None = None, include_audio: bool = True, options: Optional[dict] = None, prompt: Any = _UNSET, speech: Any = _UNSET) -> dict[str, Any]:
        language = draft["language"]
        # Real bug, found live: audio always spoke `text`, the fused
        # "I understood: X; Y; Z..." readback -- and because that readback
        # is built from the FULL cumulative draft every turn (_summary()
        # walks every field, not just what changed), a normal multi-turn
        # booking got a growing, increasingly redundant spoken readback
        # each turn ("animal: TAG-001-11" repeated at every step even
        # though only the date changed this time). `speech`, when given,
        # lets a caller synthesize a short delta-only phrase instead --
        # defaults to `text` (prior behavior) so every other call site
        # that doesn't pass it (animal-not-found-with-shortlist, the
        # post-correction re-summary) is unaffected; those genuinely
        # benefit from the full message being spoken.
        speech_source = text if speech is _UNSET else speech
        if include_audio:
            audio, audio_error = synthesize_speech(speech_source, target_lang=_lang(language))
        else:
            audio, audio_error = None, None
        resp = {
            "session_id": draft["session_id"],
            "state": draft["state"],
            "language": language,
            "transcript": input_transcript,
            "draft": draft["draft"],
            "missing_fields": self._missing(draft),
            "response_text": text,
            # prompt_text is the UI-safe alternative to response_text:
            # always just the bare next-step question/statement, never
            # fused with field data, so a client that already renders
            # `draft` as tags doesn't have to regex-parse prose out of
            # response_text (real, reported breakage: field labels don't
            # translate the same way across languages, and the field-dump
            # glues onto the next sentence with no separator). None when
            # this turn is a pure readback with no distinct next-step
            # sentence to isolate (state alone tells the UI to show its
            # own confirm buttons then).
            "prompt_text": text if prompt is _UNSET else prompt,
            "response_audio_base64": b64encode(audio).decode("ascii") if audio else None,
            "audio_error": audio_error,
        }
        # UI widget hint: a short list of clickable choices plus an
        # "Other" fallback (free-text works exactly as before either way --
        # this is purely additive metadata for a UI that wants to render
        # buttons instead of forcing every answer through typing).
        if options:
            resp["options"] = options
        return resp

    def turn(self, farmer_id: str, session_id: str, text: str, language: str = "en-IN", include_audio: bool = True,
             side_question: Optional[Callable[[str], Optional[str]]] = None,
             recent_animal: Optional[str] = None) -> dict[str, Any]:
        """side_question (optional): given the farmer's text, returns
        "weather" or "query" when the text is a question for another agent,
        else None. The chat router passes its intent classifier here so a
        question asked in the middle of a booking can be answered without
        touching the booking (see _side_question_response). It is only
        called on a turn that adds nothing to the booking, so ordinary
        booking turns cost no extra call. None (every other caller) keeps
        the old behaviour exactly.

        recent_animal (optional): the one stored animal the farmer was
        talking about in the turn just before ("what breed is KAALI?"), so
        "book a vet for her" knows which animal. Used only when this turn
        names no animal and the booking has none yet; the readback shows
        it, so the farmer can still correct it. The router decides it."""
        with self._session_lock(farmer_id, session_id):
            return self._turn_locked(farmer_id, session_id, text, language, include_audio, side_question, recent_animal)

    def _turn_locked(self, farmer_id: str, session_id: str, text: str, language: str = "en-IN", include_audio: bool = True,
                     side_question: Optional[Callable[[str], Optional[str]]] = None,
                     recent_animal: Optional[str] = None) -> dict[str, Any]:
        draft = self._load(session_id, farmer_id, language)
        if draft.get("submitted") or draft.get("state") == "CANCELLED":
            # Prior booking on this session_id is either already saved
            # permanently (submitted -- that record is not touched here) or
            # was explicitly cancelled. Either way a new message means the
            # farmer wants to start over, not resume a dead draft. Real bug,
            # found live: this reset only ever cleared OUR OWN draft file --
            # process_text_input keeps its own persistent per-session entity
            # cache (services/voice_agent/session_store.py), and without
            # clearing that too, a stale entity (e.g. the animal from the
            # cancelled/submitted booking) silently reappeared on the very
            # next turn even though our own draft was genuinely fresh. Same
            # fix already applied to the animal-not-found/wrong-tag reverts;
            # this reset path had the identical gap and was never caught
            # until testing the CANCELLED case exposed it.
            draft = self._fresh(session_id, farmer_id, language)
            clear_session(f"{farmer_id}:{session_id}")
            # chat_orchestrator's router keeps a SECOND, separately-keyed
            # session cache for its own intent classification
            # (f"{farmer_id}:{session_id}:route") -- found live: clearing
            # only the key above still let a cancelled booking's intent
            # (CREATE_APPOINTMENT/LOG_HEALTH) survive in the router's own
            # cache, so an unrelated next message (e.g. a weather question)
            # kept re-classifying into a booking intent and landing right
            # back in appointment_supervisor. Reaches into router.py's key
            # convention directly rather than leaving this half-fixed.
            clear_session(f"{farmer_id}:{session_id}:route")
        draft["language"] = language if language in SUPPORTED_LANGUAGES else draft["language"]
        draft["transcript_history"].append({"text": text, "language": draft["language"], "at": _now()})

        # Tell the extraction model exactly what our own last message
        # asked for, so it can resolve the reply with real context instead
        # of a Python-side keyword/regex guess. Two things ride on this
        # one hint: (1) confirmation_signal (yes/no/cancel/submit) when
        # we're mid-confirmation or ready-to-submit -- classified by
        # actual meaning ("that's wrong, try again" = no) rather than
        # literal keyword matching, which used to misfire on ordinary
        # words like "enough" containing "no"; (2) which entity field a
        # bare reply like "1122" answers (draft["expected_field"], set
        # below and in confirm()'s "yes" branch) -- this extraction call
        # already has a designed mechanism for exactly this (see
        # _TOOL_SYSTEM_PROMPT's example 5: "10 am" + pending_questions:
        # ["appointment time"] -> {time: '10:00'}), appointment_supervisor
        # just never wired into it before, so bare tag/ID replies kept
        # landing in issue/symptoms instead with no way to correct it.
        # "CONFIRMING" is overloaded: it means BOTH "just asked a literal
        # yes/no confirm question" (nothing missing) AND "still mid-collection,
        # asked a proactive missing-field question in the same breath"
        # (expected_field set). Only the first is genuinely a yes/no/cancel
        # moment -- treating the second the same way misroutes a farmer's
        # frustrated-but-informative reply ("... arnt you smart enough")
        # into "What would you like to correct?" purely because the state
        # name says CONFIRMING, when the bot's actual last message was
        # asking for a specific field, not a yes/no confirmation.
        state = draft.get("state")
        awaiting_confirmation = state == "CONFIRMING" and not draft.get("expected_field")
        if awaiting_confirmation:
            pending = ["confirm these details are correct (yes/no), or cancel"]
        elif state == "READY_TO_SUBMIT":
            pending = ["submit the appointment now (yes/submit), or cancel"]
        elif draft.get("expected_field") in APPOINTMENT_FIELD_LABELS:
            pending = [APPOINTMENT_FIELD_LABELS[draft["expected_field"]]]
        else:
            pending = None

        # The extraction call below also updates the session entity cache.
        # A side question must leave no trace in it (or a "today" read from
        # "what's the weather today" would come back as the booking date on
        # the next turn), so keep a copy to put back.
        cache_key = f"{farmer_id}:{session_id}"
        cache_before = copy.deepcopy(get_session(cache_key)) if side_question is not None else None
        result = process_text_input(text, session_id=cache_key, pending_questions_override=pending)
        confirmation_signal = result.get("confirmation_signal") or reply_words.confirmation_signal(text, draft["language"])
        turn_entities = result.get("entities") or {}

        # "What breed is KAALI?" then "she is limping, book a vet for her":
        # the extraction finds no animal in "her" (seen live in en/hi), and the
        # bot asked for the animal again. Fill in the animal from the turn
        # before, only when this turn names none and the booking has none.
        if (
            recent_animal
            and not draft.get("animal_verified")
            and not draft["draft"].get("animal_identifier")
            and not (turn_entities.get("animal_id") or turn_entities.get("animal_tag") or turn_entities.get("animal_name"))
        ):
            turn_entities = {**turn_entities, "animal_name": recent_animal}
            result = {**result, "entities": turn_entities}
            _log.info("appointment animal taken from the previous turn session=%s animal=%s", session_id, recent_animal)

        # Real gap, found via live testing: a genuine off-topic question
        # mid-booking ("any animal with ram") got forced through this state
        # machine's narrow yes/no/field lens and silently misread as a
        # correction/rejection, with no way to actually answer it.
        #
        # First attempt: rely on the extraction call's own "intent" field
        # to spot a genuinely different intent -- didn't work. Verified
        # directly (bypassing this code) that for this exact input the
        # model returns intent=null, confirmation_signal="no" -- it can't
        # confidently classify a vague phrase like "any animal with ram"
        # into any of the six defined intents, so there's no "switched
        # intent" signal to detect, and the forced yes/no-shaped pending
        # question nudges it toward "no" regardless of instruction wording.
        #
        # Working approach: when confirmation_signal="no" fires and
        # nothing new was actually extracted for this booking, ask
        # query_agent whether it can answer the text for real. A genuine
        # SQL+data result is strong empirical evidence this was an
        # answerable question, not a rejection -- far more reliable than
        # depending on a classification the model won't reliably make.
        # Bug found in a robustness audit: expected_field is set to the merged
        # key "animal_identifier" (see _copy_entities above), but the raw
        # extraction schema never emits that key directly -- it emits
        # animal_id/animal_tag/animal_name instead. So this check always
        # evaluated to False whenever waiting on the animal field, even when
        # the farmer's turn genuinely named one. Currently harmless only
        # because no call site happened to hit that exact combination; fixed
        # here rather than left to become a real bug later.
        expected_field = draft.get("expected_field")
        if expected_field == "animal_identifier":
            answers_expected_field = bool(
                turn_entities.get("animal_id") or turn_entities.get("animal_tag") or turn_entities.get("animal_name")
            )
        else:
            answers_expected_field = bool(expected_field) and bool(turn_entities.get(expected_field))

        # A "no" at the final readback can carry the fix itself ("no, not
        # that animal, the other one", "no, make it tomorrow"). Handled as a
        # bare "no", that correction was lost: either the farmer was asked
        # "What would you like to correct?" after already saying it, or the
        # text went to the off-topic probe below, which could find the named
        # animal in the database and answer with its details instead of
        # continuing the booking. So when the "no" brings a new value (a
        # different animal, or a changed issue/date/time), apply it now:
        # skip the probe and confirm("no") and take the normal merge path,
        # which re-verifies a new animal and reads the booking back again.
        # A bare "no" and an off-topic question behave as before.
        names_new_animal = self._names_new_animal(draft, turn_entities)
        corrects_in_place = (
            awaiting_confirmation
            and confirmation_signal == "no"
            and (names_new_animal or self._changes_a_booking_field(draft, turn_entities))
        )
        if corrects_in_place:
            _log.info(
                "appointment correction in place session=%s new_animal=%s",
                session_id, names_new_animal,
            )
        # A question for another agent asked in the middle of a booking
        # ("how many goats do I have?", "what's the weather in Pune today?").
        # The extraction reads every message as part of the booking (seen
        # live: intent CREATE_APPOINTMENT and no yes/no for such questions in
        # en/hi/ta, and "today" from the weather question became the booking
        # date), so it cannot spot these itself. Only a turn that adds
        # nothing to the booking is checked, with the router's classifier.
        if side_question is not None and not self._turn_adds_to_booking(
            draft, confirmation_signal, turn_entities, names_new_animal, answers_expected_field,
        ):
            side = side_question(text)
            answer = None
            if side == "query":
                probe = process_query(text, farmer_id)
                # Only a real database answer counts; anything else carries on as a booking turn.
                answer = probe.get("answer") if probe.get("sql") and probe.get("data") else None
                side = side if answer else None
            if side in ("weather", "query"):
                return self._side_question_response(draft, cache_key, cache_before, side, answer, text, session_id)

        if awaiting_confirmation and confirmation_signal == "no" and not answers_expected_field and not corrects_in_place:
            probe = process_query(text, farmer_id)
            if probe.get("sql") and probe.get("data"):
                self._save(draft)
                return self._response(draft, probe.get("answer") or "", input_transcript=text, include_audio=include_audio)

        # "cancel" must be honored regardless of state -- same bug class as
        # every other confirmation_signal check in this method: it was only
        # ever wired for two of the reachable states (awaiting_confirmation,
        # READY_TO_SUBMIT), so a farmer saying "cancel"/"never mind" mid-
        # collection (the normal state for most of a booking) had no way to
        # abandon it -- silently discarded, flow just re-prompted for the
        # next field forever.
        if confirmation_signal == "cancel":
            self._save(draft)
            return self.confirm(farmer_id, session_id, "cancel", include_audio=include_audio)

        if awaiting_confirmation and confirmation_signal in {"yes", "no"} and not corrects_in_place:
            self._save(draft)
            return self.confirm(farmer_id, session_id, confirmation_signal, include_audio=include_audio)
        if state == "READY_TO_SUBMIT" and confirmation_signal in {"yes", "submit"}:
            # "yes" is the natural way to affirmatively answer "would you
            # like to submit?" -- the model correctly reports the farmer's
            # literal word (confirmation_signal="yes"), not the enum value
            # "submit", so both must count as consent here. Missing this
            # caused a real infinite loop: "yes" fell through unmatched,
            # regressed state back to CONFIRMING, and the next turn's
            # "done??" bounced it back to READY_TO_SUBMIT via confirm()'s
            # own "yes" handling -- never once reaching submit().
            self._save(draft)
            return self.submit(farmer_id, session_id, include_audio=include_audio)
        if state == "READY_TO_SUBMIT" and confirmation_signal == "no":
            # Real bug: a bare "no" answering "would you like to submit?"
            # had no dedicated branch, so it fell through to the generic
            # animal-verified-reset check further down -- which ALWAYS
            # evaluates true at this exact state (every required field is
            # present by construction, so animal_verified is True and
            # expected_field is None), wiping the correct, already-verified
            # animal even if the farmer's actual objection was about the
            # date or issue. Route through confirm()'s "no" (CORRECTING)
            # branch instead, which preserves the whole draft.
            self._save(draft)
            return self.confirm(farmer_id, session_id, "no", include_audio=include_audio)

        # Real bug, found via live testing: once the animal auto-verifies
        # (matched immediately when given, not deferred to submit()), the
        # flow moves straight to asking for the next field and never again
        # asks "is this the right animal?" -- so a farmer who says "wrong
        # tag" right after has no way to be heard. Not a model problem:
        # verified directly that the model already returns
        # confirmation_signal="no" for "wrong tag" given the real context
        # (animal_id set, pending_questions asking for issue) -- this
        # branch was simply never checking that signal outside the
        # awaiting_confirmation/READY_TO_SUBMIT states. Fires regardless of
        # state as long as an animal was verified and the farmer hasn't
        # already moved on by answering the next field in the same turn.
        #
        # Real bug, found in code review: this fired on ANY unrelated "no"
        # once the animal was verified, not just a rejection about the
        # animal specifically -- e.g. "no, it's not fever, he's just
        # tired" (correcting the ISSUE) also wiped the correct, already-
        # verified animal, since confirmation_signal="no" alone doesn't
        # say WHAT is being rejected. Disambiguate the only way available
        # without a schema change: if this turn's raw entities also carry
        # a real value for some OTHER field (issue/symptoms/date/time/
        # etc), the farmer is clearly correcting THAT field, not the
        # animal -- let it fall through to the normal merge path below
        # instead. Only a "no" with no other new field information (the
        # bare "wrong tag"/"no" the original bug report actually tested)
        # still triggers the animal reset.
        corrects_other_field = any(
            turn_entities.get(f) not in (None, "", [])
            for f in ("issue", "symptoms", "duration", "severity", "date", "time", "miscellaneous_notes")
        )
        if (
            confirmation_signal == "no"
            and draft.get("animal_verified")
            and not answers_expected_field
            and not corrects_other_field
            and not corrects_in_place
        ):
            draft["draft"]["animal_identifier"] = None
            draft["draft"].pop("animal_id", None)
            draft["draft"].pop("animal_tag", None)
            draft["draft"].pop("animal_name", None)
            draft["animal_verified"] = False
            draft["state"] = "COLLECTING"
            draft["expected_field"] = "animal_identifier"
            clear_session(f"{farmer_id}:{session_id}")
            message = self._message(draft["language"], "yes_missing", field=self._message(draft["language"], "missing_animal_identifier"))
            self._save(draft)
            return self._response(draft, message, input_transcript=text, include_audio=include_audio)

        before = dict(draft["draft"])
        self._copy_entities(draft, result.get("entities") or {})

        # Verify the animal the moment it's given, not deferred to submit()
        # at the very end -- catching a wrong/ambiguous animal right after
        # the farmer names it is much better than discovering it only
        # after they've also given issue/date/time and confirmed
        # everything. Re-checks every turn until verified (idempotent);
        # once verified it's skipped for the rest of this booking.
        identifier = draft["draft"].get("animal_identifier")
        if identifier and not draft.get("animal_verified"):
            animals = merge_app_animals(farmer_id, animals_for_farmer(farmer_id), flokiq_sync.get_farm_animals(farmer_id))
            matched, candidates = _verify_animal(identifier, animals)
            if matched:
                # What the farmer actually called the animal (any script or
                # spelling) -- kept so a later turn repeating it is not
                # mistaken for a different animal (see _names_new_animal).
                draft["animal_said"] = identifier
                draft["draft"]["animal_id"] = matched.id
                draft["draft"]["animal_identifier"] = matched.tag_or_name
                draft["animal_verified"] = True
            else:
                draft["draft"]["animal_identifier"] = None
                draft["draft"].pop("animal_id", None)
                draft["draft"].pop("animal_tag", None)
                draft["draft"].pop("animal_name", None)
                draft["animal_verified"] = False
                draft["state"] = "COLLECTING"
                draft["expected_field"] = "animal_identifier"
                # Cap the spoken/read list at the same 5 shown as pills --
                # real bug, found live via TTS: the prose used to list ALL
                # 53 registered animals even when candidates narrowed it,
                # so voice would read the entire herd aloud while the pills
                # only offered 5. Same list feeds both now, so they can't
                # drift apart again.
                shown = (candidates or animals)[:5]
                if not animals:
                    # Real bug, found in a robustness audit: with animals
                    # == [], "".join(...) is falsy, so animal_names fell
                    # back to the literal field-label string, producing a
                    # nonsensical "...registered animals are: the animal
                    # name, tag, or ID..." for a farmer who genuinely has
                    # none yet. This is a different, honest situation --
                    # not a mismatch to correct, a farmer with zero
                    # registered animals -- and gets its own message.
                    message = self._message(draft["language"], "no_animals_registered", identifier=identifier)
                else:
                    animal_names = ", ".join(a.tag_or_name for a in shown)
                    message = self._message(draft["language"], "animal_not_found", identifier=identifier, animals=animal_names)
                # prompt_text: just the ask, reusing the same phrasing
                # already used everywhere else this field is requested --
                # the "who/what animal wasn't found" context lives in
                # options.choices structurally, not prose a UI has to
                # parse.
                prompt = self._message(draft["language"], "yes_missing", field=self._message(draft["language"], "missing_animal_identifier"))
                self._save(draft)
                return self._response(
                    draft, message, input_transcript=text, include_audio=include_audio,
                    options=_animal_options(draft["language"], shown), prompt=prompt,
                )

        missing = self._missing(draft)
        draft["expected_field"] = missing[0] if missing else None
        options = _symptom_options(draft["language"]) if draft["expected_field"] == "issue" else None

        if draft["draft"] == before and missing:
            # Extraction found nothing new and something is still missing.
            # Previously this always resent the full 4-field "Hello,
            # please tell me..." welcome, discarding whatever was already
            # collected (a real bug: looked like the bot forgot the whole
            # conversation). Now: re-ask specifically for the field still
            # missing if anything has been collected already; only show
            # the full welcome when truly nothing has been said yet.
            draft["state"] = "COLLECTING"
            if self._has_any_info(draft["draft"]):
                field = self._message(draft["language"], f"missing_{missing[0]}")
                message = self._message(draft["language"], "yes_missing", field=field)
            else:
                message = self._message(draft["language"], "welcome")
                options = None
            self._save(draft)
            return self._response(draft, message, input_transcript=text, include_audio=include_audio, options=options)

        draft["state"] = "CONFIRMING"
        self._save(draft)
        message = self._message(draft["language"], "correct", summary=self._summary(draft))
        prompt = None
        if missing:
            # Proactively ask for the next missing required field in the
            # same turn, instead of only echoing back what was understood
            # and waiting for a separate "yes" before asking anything --
            # avoids a robotic "I understood: X" -> silence -> "I understood: X, Y"
            # loop with no question in it. Reuses the existing translated
            # "yes_missing" copy (already vetted in every supported
            # language) rather than adding new phrasing.
            field = self._message(draft["language"], f"missing_{missing[0]}")
            prompt = self._message(draft["language"], "yes_missing", field=field)
            message = f"{message} {prompt}"
        # prompt is None here when nothing is missing -- this turn is a
        # pure "I understood: X" readback with no distinct next-step
        # sentence; state=="CONFIRMING" alone tells the UI to show its own
        # yes/no confirm buttons rather than a prompt sentence.
        if missing:
            # Real bug, found live: audio was speaking `message`, the FULL
            # cumulative summary (_summary(draft) walks every field ever
            # captured), every single intermediate turn -- so a farmer
            # heard the animal/issue/symptoms repeated back at every step
            # even when only the date was new this turn. Speak only what
            # changed this turn (the before/after diff already computed
            # above) plus the next question -- text (`message`) stays the
            # full detailed readback, only audio gets the short version.
            changed_fields = {k for k, v in draft["draft"].items() if before.get(k) != v}
            delta_summary = self._summary(draft, only_fields=changed_fields) if changed_fields else ""
            if delta_summary and delta_summary != "no appointment details yet":
                speech = f"{self._message(draft['language'], 'correct', summary=delta_summary)} {prompt}"
            else:
                speech = prompt
        else:
            # Terminal readback right before the farmer must say yes/no --
            # the whole booking needs to be heard here, not just a delta,
            # since this is the one moment a voice-only farmer confirms
            # everything at once.
            speech = message
        return self._response(draft, message, input_transcript=text, include_audio=include_audio, options=options, prompt=prompt, speech=speech)

    def confirm(self, farmer_id: str, session_id: str, response: str, include_audio: bool = True) -> dict[str, Any]:
        with self._session_lock(farmer_id, session_id):
            return self._confirm_locked(farmer_id, session_id, response, include_audio)

    def _confirm_locked(self, farmer_id: str, session_id: str, response: str, include_audio: bool = True) -> dict[str, Any]:
        draft = self._load(session_id, farmer_id, "en-IN")
        if draft.get("submitted"):
            raise ValueError("This appointment intake has already been submitted")
        if draft.get("state") == "CANCELLED":
            # Real bug: confirm() only ever guarded on submitted, never on
            # state, and it's a directly-callable REST endpoint
            # (POST /appointments/confirm) -- a stray or replayed "yes" on
            # an already-cancelled-but-unsubmitted draft could jump
            # straight to READY_TO_SUBMIT (since the fields were still all
            # present), and a subsequent submit() would genuinely save an
            # appointment the farmer explicitly cancelled. turn() itself
            # can never hit this (it resets a CANCELLED draft to fresh on
            # entry), so this guard specifically protects the direct-call
            # path.
            raise ValueError("This appointment intake was cancelled")
        normalized = response.strip().lower()
        language = draft["language"]
        draft["confirmation_history"].append({"response": response, "at": _now()})
        options = None
        if normalized in {"yes", "y", "haan", "ಹೌದು", "అవును", "ஆம்"}:
            draft["confirmed_fields"] = list(draft["draft"].keys())
            missing = self._missing(draft)
            draft["expected_field"] = missing[0] if missing else None
            if missing:
                draft["state"] = "COLLECTING"
                field = self._message(language, f"missing_{missing[0]}")
                message = self._message(language, "yes_missing", field=field)
                if missing[0] == "issue":
                    options = _symptom_options(language)
            else:
                draft["state"] = "READY_TO_SUBMIT"
                message = self._message(language, "ready")
        elif normalized in {"no", "n", "wrong", "गलत", "இல்லை", "ಇಲ್ಲ", "కాదు"}:
            draft["state"] = "CORRECTING"
            message = self._message(language, "no")
        elif normalized in {"cancel", "cancelled", "रद्द", "ரத்து", "ರದ್ದು", "రద్దు"}:
            draft["state"] = "CANCELLED"
            message = self._message(language, "cancelled")
            # Real bug, found live: clearing the session cache only on the
            # NEXT turn's entry (when it sees a pre-existing CANCELLED
            # state) is one turn too late. chat_orchestrator.route_turn()
            # runs its OWN classification call (session key
            # f"{farmer_id}:{session_id}:route") BEFORE it ever calls back
            # into appointment_supervisor.turn() on that next turn -- so an
            # unrelated question right after cancelling (e.g. a weather
            # question) got classified using the stale, cached
            # CREATE_APPOINTMENT intent from *before* the cancel, and never
            # even reached the entry-reset logic that would have cleared
            # it. Must clear at the moment of cancelling, not reactively.
            clear_session(f"{farmer_id}:{session_id}")
            clear_session(f"{farmer_id}:{session_id}:route")
        else:
            draft["state"] = "CONFIRMING"
            result = process_text_input(response, session_id=f"{farmer_id}:{session_id}")
            self._copy_entities(draft, result.get("entities") or {})
            message = self._message(language, "updated", summary=self._summary(draft))
            # No distinct next-step sentence here -- just the readback --
            # same as the bare "correct" case in turn().
            self._save(draft)
            return self._response(draft, message, include_audio=include_audio, options=options, prompt=None)
        self._save(draft)
        return self._response(draft, message, include_audio=include_audio, options=options)

    def submit(self, farmer_id: str, session_id: str, include_audio: bool = True) -> dict[str, Any]:
        with self._session_lock(farmer_id, session_id):
            return self._submit_locked(farmer_id, session_id, include_audio)

    def _submit_locked(self, farmer_id: str, session_id: str, include_audio: bool = True) -> dict[str, Any]:
        draft = self._load(session_id, farmer_id, "en-IN")
        if draft.get("submitted"):
            return {"status": "already_submitted", "intake": draft}
        if draft.get("state") != "READY_TO_SUBMIT":
            raise ValueError("The appointment requires final confirmation before submission")
        values = draft["draft"]
        animal_id = values.get("animal_id")
        animals = merge_app_animals(farmer_id, animals_for_farmer(farmer_id), flokiq_sync.get_farm_animals(farmer_id))
        if not animal_id:
            wanted = str(values.get("animal_identifier") or "").lower()
            matches = [a for a in animals if wanted in {a.id.lower(), a.tag_or_name.lower()}]
            candidate_ids: list = []
            if matches:
                animal_id = matches[0].id
            else:
                # Exact match failed -- ask the model instead of giving up.
                # A farmer's reasonable guess ("tag 001" after being told
                # real tags look like "TAG-001-1") or a plain typo should
                # not dead-end just because it isn't byte-identical to a
                # stored string.
                animal_id, candidate_ids = _resolve_animal_id(str(values.get("animal_identifier") or ""), animals)
        if not animal_id:
            # Loop back into the conversation instead of raising -- a raw
            # exception here used to become a dead-end HTTP 400 with no way
            # to recover, breaking the one invariant every other branch of
            # this state machine keeps: a mistake gets a chance to be
            # corrected, not a wall. Data-driven, not a generic retry
            # prompt. When _resolve_animal_id flagged specific plausible
            # candidates (ambiguous, not a total non-match), narrow the
            # list to those instead of dumping the farmer's entire herd --
            # asking them to pick between 3 real possibilities is useful,
            # asking them to scan all 53 tags is not.
            bad_identifier = str(values.get("animal_identifier") or "")
            by_id = {a.id: a for a in animals}
            # Cap at the same 5 shown as pills -- the prose used to list
            # every registered animal even when candidates narrowed it, so
            # TTS would read the entire herd aloud while pills only
            # offered 5. Same list feeds both here.
            shown = ([by_id[c] for c in candidate_ids if c in by_id] or animals)[:5]
            draft["draft"]["animal_identifier"] = None
            draft["draft"].pop("animal_id", None)
            draft["draft"].pop("animal_tag", None)
            draft["draft"].pop("animal_name", None)
            draft["state"] = "COLLECTING"
            draft["expected_field"] = "animal_identifier"
            self._save(draft)
            # process_text_input keeps its OWN persistent per-session entity
            # cache (services/voice_agent/session_store.py), independent of
            # this draft. Clearing our draft's animal fields above is not
            # enough -- that cache still holds the stale animal_tag/name,
            # and _copy_entities would silently re-merge it back in on the
            # very next turn, undoing this reset before the farmer's
            # correction ever had a chance. Real bug, found live: "GAURI"
            # typed right after this message still came back as "1122".
            clear_session(f"{farmer_id}:{session_id}")
            if not animals:
                message = self._message(draft["language"], "no_animals_registered", identifier=bad_identifier)
            else:
                animal_names = ", ".join(a.tag_or_name for a in shown)
                message = self._message(draft["language"], "animal_not_found", identifier=bad_identifier, animals=animal_names)
            prompt = self._message(draft["language"], "yes_missing", field=self._message(draft["language"], "missing_animal_identifier"))
            return self._response(draft, message, include_audio=include_audio, options=_animal_options(draft["language"], shown), prompt=prompt)
        health = append_health_log(farmer_id, animal_id, str(values.get("issue")), {
            "symptoms": values.get("symptoms", []),
            "duration": values.get("duration"),
            "severity": values.get("severity"),
            "temperature_c": values.get("temperature_c"),
            "current_medication": values.get("current_medication"),
            "attachments": values.get("attachments", []),
        }, str(values.get("miscellaneous_notes") or values.get("notes") or ""))
        appointment = append_appointment(farmer_id, str(values.get("date")), str(values.get("time")), str(values.get("doctor_id") or ""), str(values.get("miscellaneous_notes") or ""), health.id, animal_id, str(values.get("issue")), values)
        draft["draft"]["animal_id"] = animal_id
        draft["health_log_id"] = health.id
        draft["appointment_id"] = appointment.id
        draft["state"] = "SUBMITTED"
        draft["submitted"] = True
        self._save(draft)
        # Clear both session caches immediately on submit, not reactively
        # on the next turn's entry -- same reasoning as the cancel branch
        # in confirm(): router.py's own classification call runs BEFORE it
        # calls back into turn() on the next message, so a stale cached
        # intent from this just-completed booking could otherwise leak
        # into classifying whatever the farmer says next.
        clear_session(f"{farmer_id}:{session_id}")
        clear_session(f"{farmer_id}:{session_id}:route")

        # Second agent in the handoff: appointment_supervisor has finished
        # collecting details, now hand the symptoms off to a dedicated
        # generation-tier agent for preliminary, non-diagnostic guidance to
        # show the farmer while they wait for the real vet visit already
        # booked above. Never raises -- returns empty fields on any failure,
        # so a generation-agent problem never blocks the booking that
        # already succeeded.
        recommendation = generate_health_recommendation(
            species=str(values.get("species") or ""),
            symptoms=values.get("symptoms") or [],
            issue=str(values.get("issue") or ""),
            severity=str(values.get("severity") or ""),
            duration=str(values.get("duration") or ""),
            language=_lang(draft["language"]),
        )

        # Our own AI-health-log record, shaped like flokiq's real
        # health_logs table but stored locally -- always on, independent of
        # FLOKIQ_SYNC_ENABLED. Lets us accumulate real data and iterate
        # without needing flokiq's team to first confirm it's safe to write
        # AI-generated diagnosis/risk fields into their shared table.
        severity_to_risk = {"mild": "Low", "moderate": "Medium", "severe": "High"}
        risk_level = severity_to_risk.get(str(values.get("severity") or "").lower())
        append_ai_health_log(
            farmer_id=farmer_id,
            animal_id=animal_id,
            pincode=str(values.get("weather_location") or ""),
            symptoms=values.get("symptoms") or [],
            risk_level=risk_level,
            ai_diagnosis_suggestion=recommendation["diagnosis_suggestion"],
            potential_ailments=recommendation["potential_ailments"],
            first_aid_advice=recommendation["first_aid_advice"],
        )

        # Best-effort sync to flokiq's DB. Local write above is already the
        # source of truth for this booking -- a sync failure here is logged
        # and swallowed inside flokiq_sync, never raised, never loses the
        # farmer's appointment.
        flokiq_health_log = flokiq_sync.create_health_log(
            farmer_id=farmer_id,
            pincode=str(values.get("weather_location") or ""),
            symptoms=values.get("symptoms") or [],
            animal_id=animal_id,
            risk_level=risk_level,
            ai_diagnosis_suggestion=recommendation["diagnosis_suggestion"],
            potential_ailments=recommendation["potential_ailments"],
            first_aid_advice=recommendation["first_aid_advice"],
        )
        # Real bug, found in whole-branch review: build_appointment_notes
        # reads values["animal_name"], a key this draft never stores --
        # _copy_entities keeps only the resolved "animal_identifier", and
        # the raw animal_id/animal_tag/animal_name fields are deliberately
        # excluded from the draft. Every synced note was missing which
        # animal it's for. The real animal is already resolved to
        # `animal_id` above; look it up for its real tag/name and species.
        resolved_animal = next((a for a in animals if a.id == animal_id), None)
        notes_values = {
            **values,
            "animal_name": getattr(resolved_animal, "tag_or_name", None) or values.get("animal_identifier"),
            "species": getattr(resolved_animal, "species", None) or values.get("species"),
        }
        # Real bug, found in whole-stack review: the result was never
        # checked, so the farmer heard "saved successfully" even when the
        # sync to main_backend genuinely failed (network error, main_backend
        # rejected it, etc). create_appointment also returns None when sync
        # simply doesn't apply here (disabled, unconfigured, a local demo
        # farmer_id) -- will_attempt_appointment_sync distinguishes "sync
        # wasn't attempted" from "sync was attempted and failed," so the
        # caveat below only fires for a genuine failure, not every booking
        # in an environment where sync isn't even turned on.
        sync_was_attempted = flokiq_sync.will_attempt_appointment_sync(farmer_id)
        sync_result = flokiq_sync.create_appointment(
            farmer_id=farmer_id,
            date=str(values.get("date")),
            time=str(values.get("time")),
            notes=flokiq_sync.build_appointment_notes(notes_values),
            health_log_id=(flokiq_health_log or {}).get("log_id"),
        )
        sync_failed = sync_was_attempted and sync_result is None

        # Show the recommendation to the farmer -- spoken via TTS same as
        # every other response, plus returned as structured data for the
        # frontend to render (e.g. clearly labeled "AI suggestion, not a
        # diagnosis" the way the data model's source=ai_unverified marker
        # already implies).
        recommendation_audio, recommendation_audio_error = (None, None)
        if include_audio and recommendation["first_aid_advice"]:
            recommendation_audio, recommendation_audio_error = synthesize_speech(
                recommendation["first_aid_advice"], target_lang=_lang(draft["language"]),
            )

        # response_text/response_audio_base64/audio_error at the top level,
        # same keys turn()/confirm() already return -- lets any caller
        # (UI, orchestrator envelope) read one consistent field regardless
        # of which state the conversation ended in, instead of needing a
        # separate branch just for the submit shape.
        # Reviewer-found issue: appending a "may take a little longer to
        # show up in the app" caveat after "saved successfully" was still
        # dishonest -- create_appointment has no retry/queue, so a failed
        # sync NEVER reaches the app, not just later. On a genuine failure
        # this replaces the message entirely rather than appending to it,
        # so the farmer is never told the booking succeeded when the part
        # that mattered (reaching the vet's app) did not.
        submitted_text = self._message(
            draft["language"], "submitted_sync_failed" if sync_failed else "submitted"
        )
        if recommendation.get("first_aid_advice"):
            submitted_text = f"{submitted_text} {recommendation['first_aid_advice']}"
        return {
            "status": "submitted",
            "intake": draft,
            "health_log": health.model_dump(),
            "appointment": appointment.model_dump(),
            "response_text": submitted_text,
            "response_audio_base64": (
                b64encode(recommendation_audio).decode("ascii") if recommendation_audio else None
            ),
            "audio_error": recommendation_audio_error,
            "ai_recommendation": {
                **recommendation,
                "source": "ai_unverified",
                "response_audio_base64": (
                    b64encode(recommendation_audio).decode("ascii") if recommendation_audio else None
                ),
                "audio_error": recommendation_audio_error,
            },
        }

    def attach(self, farmer_id: str, session_id: str, attachment: dict[str, Any]) -> dict[str, Any]:
        with self._session_lock(farmer_id, session_id):
            return self._attach_locked(farmer_id, session_id, attachment)

    def _attach_locked(self, farmer_id: str, session_id: str, attachment: dict[str, Any]) -> dict[str, Any]:
        draft = self._load(session_id, farmer_id, "en-IN")
        if draft.get("submitted"):
            raise ValueError("This appointment intake has already been submitted")
        if draft.get("state") == "CANCELLED":
            raise ValueError("This appointment intake was cancelled")
        draft["draft"].setdefault("attachments", []).append(attachment)
        self._save(draft)
        return {"session_id": session_id, "attachments": draft["draft"]["attachments"], "draft": draft["draft"]}

