"""7-language message catalog for the WhatsApp channel.

Same lang-tag convention as the rest of the codebase (en/hi/ta/te/kn/mr/ml),
same {placeholder} format-string shape as animal_registration/messages
and appointment_supervisor's `_TEXT`. `_lang()` from
services.common.draft_supervisor is reused for the tag -> prefix
resolution and its "fall back to English on unknown language" behavior.

Enrollment prompt DELIBERATELY asks for "registered phone number or
username", never "farmer ID": farmers don't know their internal
f-001 UUIDs, so asking for one would be a dead end.

enroll_code_sent is deliberately the SAME reply whether or not the claim
matched an account, so it cannot be used to discover which phone numbers
or usernames are registered.
"""
from __future__ import annotations

from typing import Any

from services.common.draft_supervisor import _lang


_TEXT = {
    "en": {
        "blocked_intent": (
            "That kind of request is not available on WhatsApp right now. "
            "Please use the FarmHerd app for that. On WhatsApp you can: {allowed_summary}."
        ),
        "unknown_farmer_enroll_prompt": (
            "Hi! I don't recognize this WhatsApp number yet. Please reply with your "
            "registered phone number or your FarmHerd username so I can link this "
            "WhatsApp to your account."
        ),
        "unknown_farmer_no_enroll": (
            "This WhatsApp number is not registered with FarmHerd. Please contact "
            "support if you would like access."
        ),
        "enrollment_success": (
            "Thanks {name} -- your WhatsApp is now linked to your FarmHerd account. "
            "Send me your question and I'll help you."
        ),
        "enrollment_failed": (
            "I couldn't find a FarmHerd account matching that. Please reply with "
            "your registered phone number (like +91XXXXXXXXXX) or your username."
        ),
        "enroll_code_sent": (
            "To link this WhatsApp to your FarmHerd account, reply with your registered "
            "phone number or username. If it matches an account, we will send a 6-digit "
            "code by SMS to the registered phone -- please reply here with that code."
        ),
        "otp_wrong": "That code is not correct. Please check the SMS and try again.",
        "otp_locked": (
            "Too many wrong codes. Please send your registered phone number or username "
            "again to get a new code."
        ),
        "otp_expired": (
            "That code has expired. Please send your registered phone number or username "
            "again to get a new code."
        ),
        "rate_limited": (
            "You are sending messages a bit fast. Please wait a moment and try again."
        ),
        "reply_trimmed_suffix": "\n\n... (reply trimmed; open the app to see the full answer)",
        # Human-readable labels for allowed_intents, used in the
        # blocked_intent message body.
        "intent_labels": {
            "query": "ask about your animals or records",
            "appointment": "book a vet appointment or log a health event",
            "weather": "check weather",
            "add_animal": "register a new animal",
        },
    },
    "hi": {
        "blocked_intent": (
            "यह अनुरोध अभी WhatsApp पर उपलब्ध नहीं है। कृपया इसके लिए FarmHerd ऐप का उपयोग करें। "
            "WhatsApp पर आप कर सकते हैं: {allowed_summary}।"
        ),
        "unknown_farmer_enroll_prompt": (
            "नमस्ते! मैं इस WhatsApp नंबर को अभी पहचान नहीं पा रहा। कृपया अपना पंजीकृत फोन नंबर "
            "या FarmHerd यूज़रनेम भेजें ताकि मैं इस WhatsApp को आपके खाते से जोड़ सकूं।"
        ),
        "unknown_farmer_no_enroll": (
            "यह WhatsApp नंबर FarmHerd में पंजीकृत नहीं है। कृपया सहायता से संपर्क करें।"
        ),
        "enrollment_success": (
            "धन्यवाद {name} -- आपका WhatsApp अब आपके FarmHerd खाते से जुड़ गया है। "
            "अपना प्रश्न भेजें, मैं मदद करूंगा।"
        ),
        "enrollment_failed": (
            "मुझे कोई मिलान वाला FarmHerd खाता नहीं मिला। कृपया अपना पंजीकृत फोन नंबर "
            "(जैसे +91XXXXXXXXXX) या यूज़रनेम भेजें।"
        ),
        "enroll_code_sent": (
            "इस WhatsApp को अपने FarmHerd खाते से जोड़ने के लिए अपना पंजीकृत फोन नंबर या यूज़रनेम "
            "भेजें। अगर यह किसी खाते से मेल खाता है, तो हम पंजीकृत फोन पर SMS से 6 अंकों का कोड "
            "भेजेंगे -- कृपया वह कोड यहाँ भेजें।"
        ),
        "otp_wrong": "यह कोड सही नहीं है। कृपया SMS देखकर फिर से भेजें।",
        "otp_locked": (
            "बहुत बार गलत कोड भेजा गया। नया कोड पाने के लिए अपना पंजीकृत फोन नंबर या यूज़रनेम "
            "फिर से भेजें।"
        ),
        "otp_expired": (
            "यह कोड समाप्त हो गया है। नया कोड पाने के लिए अपना पंजीकृत फोन नंबर या यूज़रनेम "
            "फिर से भेजें।"
        ),
        "rate_limited": "आप बहुत तेज़ी से संदेश भेज रहे हैं। कृपया थोड़ी देर बाद फिर से कोशिश करें।",
        "reply_trimmed_suffix": "\n\n... (उत्तर छोटा किया गया है; पूरा उत्तर देखने के लिए ऐप खोलें)",
        "intent_labels": {
            "query": "अपने पशुओं या रिकॉर्ड के बारे में पूछना",
            "appointment": "पशु चिकित्सक अपॉइंटमेंट बुक करना या स्वास्थ्य घटना दर्ज करना",
            "weather": "मौसम देखना",
            "add_animal": "नया पशु पंजीकृत करना",
        },
    },
    "ta": {
        "blocked_intent": (
            "இந்த கோரிக்கை தற்போது WhatsApp-இல் கிடைக்கவில்லை. இதற்கு FarmHerd செயலியைப் "
            "பயன்படுத்தவும். WhatsApp-இல் நீங்கள் செய்யக்கூடியவை: {allowed_summary}."
        ),
        "unknown_farmer_enroll_prompt": (
            "வணக்கம்! இந்த WhatsApp எண்ணை என்னால் அடையாளம் காண முடியவில்லை. உங்கள் பதிவு "
            "செய்யப்பட்ட தொலைபேசி எண் அல்லது FarmHerd பயனர்பெயரை அனுப்பவும்."
        ),
        "unknown_farmer_no_enroll": (
            "இந்த WhatsApp எண் FarmHerd-இல் பதிவு செய்யப்படவில்லை. உதவிக்கு தொடர்பு கொள்ளவும்."
        ),
        "enrollment_success": (
            "நன்றி {name} -- உங்கள் WhatsApp இப்போது FarmHerd கணக்குடன் இணைக்கப்பட்டது. "
            "உங்கள் கேள்வியை அனுப்புங்கள்."
        ),
        "enrollment_failed": (
            "பொருந்தும் FarmHerd கணக்கு எதுவும் கிடைக்கவில்லை. உங்கள் பதிவு செய்யப்பட்ட "
            "தொலைபேசி எண் (+91XXXXXXXXXX போன்று) அல்லது பயனர்பெயரை அனுப்பவும்."
        ),
        "enroll_code_sent": (
            "இந்த WhatsApp-ஐ உங்கள் FarmHerd கணக்குடன் இணைக்க, உங்கள் பதிவு செய்யப்பட்ட "
            "தொலைபேசி எண் அல்லது பயனர்பெயரை அனுப்பவும். அது ஒரு கணக்குடன் பொருந்தினால், பதிவு "
            "செய்யப்பட்ட தொலைபேசிக்கு SMS மூலம் 6 இலக்க குறியீடு அனுப்பப்படும் -- அந்தக் "
            "குறியீட்டை இங்கே அனுப்பவும்."
        ),
        "otp_wrong": "இந்தக் குறியீடு சரியில்லை. SMS-ஐப் பார்த்து மீண்டும் முயற்சிக்கவும்.",
        "otp_locked": (
            "பல முறை தவறான குறியீடு. புதிய குறியீட்டைப் பெற உங்கள் பதிவு செய்யப்பட்ட "
            "தொலைபேசி எண் அல்லது பயனர்பெயரை மீண்டும் அனுப்பவும்."
        ),
        "otp_expired": (
            "இந்தக் குறியீட்டின் காலம் முடிந்துவிட்டது. புதிய குறியீட்டைப் பெற உங்கள் பதிவு "
            "செய்யப்பட்ட தொலைபேசி எண் அல்லது பயனர்பெயரை மீண்டும் அனுப்பவும்."
        ),
        "rate_limited": "நீங்கள் மிக வேகமாக செய்திகளை அனுப்புகிறீர்கள். சிறிது நேரம் காத்திருந்து மீண்டும் முயற்சிக்கவும்.",
        "reply_trimmed_suffix": "\n\n... (பதில் சுருக்கப்பட்டது; முழு பதிலைக் காண செயலியைத் திறக்கவும்)",
        "intent_labels": {
            "query": "உங்கள் விலங்குகள் அல்லது பதிவுகள் பற்றி கேட்க",
            "appointment": "கால்நடை மருத்துவர் சந்திப்பு அல்லது சுகாதார நிகழ்வு பதிவு",
            "weather": "வானிலை பார்க்க",
            "add_animal": "புதிய விலங்கு பதிவு செய்ய",
        },
    },
    "te": {
        "blocked_intent": (
            "ఈ అభ్యర్థన ప్రస్తుతం WhatsApp-లో అందుబాటులో లేదు. దీని కోసం FarmHerd యాప్ను "
            "ఉపయోగించండి. WhatsApp-లో మీరు చేయగలిగినవి: {allowed_summary}."
        ),
        "unknown_farmer_enroll_prompt": (
            "నమస్తే! ఈ WhatsApp నంబర్ను నేను గుర్తించలేదు. దయచేసి మీ నమోదిత ఫోన్ నంబర్ లేదా "
            "FarmHerd యూజర్నేమ్ పంపండి."
        ),
        "unknown_farmer_no_enroll": (
            "ఈ WhatsApp నంబర్ FarmHerd-లో నమోదు కాలేదు. దయచేసి మద్దతును సంప్రదించండి."
        ),
        "enrollment_success": (
            "ధన్యవాదాలు {name} -- మీ WhatsApp ఇప్పుడు FarmHerd ఖాతాతో లింక్ చేయబడింది. "
            "మీ ప్రశ్నను పంపండి."
        ),
        "enrollment_failed": (
            "సరిపోలే FarmHerd ఖాతా కనుగొనబడలేదు. దయచేసి మీ నమోదిత ఫోన్ నంబర్ "
            "(+91XXXXXXXXXX వంటిది) లేదా యూజర్నేమ్ పంపండి."
        ),
        "enroll_code_sent": (
            "ఈ WhatsAppను మీ FarmHerd ఖాతాతో లింక్ చేయడానికి, మీ నమోదిత ఫోన్ నంబర్ లేదా "
            "యూజర్నేమ్ పంపండి. అది ఏదైనా ఖాతాతో సరిపోలితే, నమోదిత ఫోన్కు SMS ద్వారా 6 అంకెల "
            "కోడ్ పంపుతాము -- దయచేసి ఆ కోడ్ను ఇక్కడ పంపండి."
        ),
        "otp_wrong": "ఈ కోడ్ సరైనది కాదు. దయచేసి SMS చూసి మళ్లీ ప్రయత్నించండి.",
        "otp_locked": (
            "చాలా సార్లు తప్పు కోడ్. కొత్త కోడ్ కోసం మీ నమోదిత ఫోన్ నంబర్ లేదా యూజర్నేమ్ "
            "మళ్లీ పంపండి."
        ),
        "otp_expired": (
            "ఈ కోడ్ గడువు ముగిసింది. కొత్త కోడ్ కోసం మీ నమోదిత ఫోన్ నంబర్ లేదా యూజర్నేమ్ "
            "మళ్లీ పంపండి."
        ),
        "rate_limited": "మీరు చాలా వేగంగా సందేశాలు పంపుతున్నారు. కొంచెం వేచి మళ్ళీ ప్రయత్నించండి.",
        "reply_trimmed_suffix": "\n\n... (సమాధానం కుదించబడింది; పూర్తి సమాధానం కోసం యాప్ తెరవండి)",
        "intent_labels": {
            "query": "మీ జంతువుల లేదా రికార్డుల గురించి అడగడం",
            "appointment": "పశువైద్యుని అపాయింట్మెంట్ లేదా ఆరోగ్య సంఘటన నమోదు",
            "weather": "వాతావరణం చూడడం",
            "add_animal": "కొత్త జంతువును నమోదు చేయడం",
        },
    },
    "kn": {
        "blocked_intent": (
            "ಈ ವಿನಂತಿ ಪ್ರಸ್ತುತ WhatsApp-ನಲ್ಲಿ ಲಭ್ಯವಿಲ್ಲ. ಇದಕ್ಕಾಗಿ FarmHerd ಆಪ್ ಬಳಸಿ. "
            "WhatsApp-ನಲ್ಲಿ ನೀವು ಮಾಡಬಹುದಾದವು: {allowed_summary}."
        ),
        "unknown_farmer_enroll_prompt": (
            "ನಮಸ್ಕಾರ! ಈ WhatsApp ಸಂಖ್ಯೆಯನ್ನು ನಾನು ಗುರುತಿಸಲಾಗಿಲ್ಲ. ದಯವಿಟ್ಟು ನಿಮ್ಮ ನೋಂದಾಯಿತ "
            "ಫೋನ್ ಸಂಖ್ಯೆ ಅಥವಾ FarmHerd ಬಳಕೆದಾರಹೆಸರನ್ನು ಕಳುಹಿಸಿ."
        ),
        "unknown_farmer_no_enroll": (
            "ಈ WhatsApp ಸಂಖ್ಯೆ FarmHerd-ನಲ್ಲಿ ನೋಂದಾಯಿಸಲಾಗಿಲ್ಲ. ದಯವಿಟ್ಟು ಬೆಂಬಲವನ್ನು ಸಂಪರ್ಕಿಸಿ."
        ),
        "enrollment_success": (
            "ಧನ್ಯವಾದಗಳು {name} -- ನಿಮ್ಮ WhatsApp ಈಗ FarmHerd ಖಾತೆಗೆ ಲಿಂಕ್ ಆಗಿದೆ. "
            "ನಿಮ್ಮ ಪ್ರಶ್ನೆಯನ್ನು ಕಳುಹಿಸಿ."
        ),
        "enrollment_failed": (
            "ಹೊಂದಾಣಿಕೆಯಾಗುವ FarmHerd ಖಾತೆ ಸಿಗಲಿಲ್ಲ. ದಯವಿಟ್ಟು ನಿಮ್ಮ ನೋಂದಾಯಿತ ಫೋನ್ ಸಂಖ್ಯೆ "
            "(+91XXXXXXXXXX ರೀತಿ) ಅಥವಾ ಬಳಕೆದಾರಹೆಸರನ್ನು ಕಳುಹಿಸಿ."
        ),
        "enroll_code_sent": (
            "ಈ WhatsApp ಅನ್ನು ನಿಮ್ಮ FarmHerd ಖಾತೆಗೆ ಲಿಂಕ್ ಮಾಡಲು, ನಿಮ್ಮ ನೋಂದಾಯಿತ ಫೋನ್ ಸಂಖ್ಯೆ "
            "ಅಥವಾ ಬಳಕೆದಾರಹೆಸರನ್ನು ಕಳುಹಿಸಿ. ಅದು ಯಾವುದಾದರೂ ಖಾತೆಗೆ ಹೊಂದಿಕೆಯಾದರೆ, ನೋಂದಾಯಿತ "
            "ಫೋನ್ಗೆ SMS ಮೂಲಕ 6 ಅಂಕಿಯ ಕೋಡ್ ಕಳುಹಿಸುತ್ತೇವೆ -- ದಯವಿಟ್ಟು ಆ ಕೋಡ್ ಅನ್ನು ಇಲ್ಲಿ ಕಳುಹಿಸಿ."
        ),
        "otp_wrong": "ಈ ಕೋಡ್ ಸರಿಯಿಲ್ಲ. ದಯವಿಟ್ಟು SMS ನೋಡಿ ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ.",
        "otp_locked": (
            "ಹಲವು ಬಾರಿ ತಪ್ಪು ಕೋಡ್. ಹೊಸ ಕೋಡ್ಗಾಗಿ ನಿಮ್ಮ ನೋಂದಾಯಿತ ಫೋನ್ ಸಂಖ್ಯೆ ಅಥವಾ "
            "ಬಳಕೆದಾರಹೆಸರನ್ನು ಮತ್ತೆ ಕಳುಹಿಸಿ."
        ),
        "otp_expired": (
            "ಈ ಕೋಡ್ನ ಅವಧಿ ಮುಗಿದಿದೆ. ಹೊಸ ಕೋಡ್ಗಾಗಿ ನಿಮ್ಮ ನೋಂದಾಯಿತ ಫೋನ್ ಸಂಖ್ಯೆ ಅಥವಾ "
            "ಬಳಕೆದಾರಹೆಸರನ್ನು ಮತ್ತೆ ಕಳುಹಿಸಿ."
        ),
        "rate_limited": "ನೀವು ತುಂಬಾ ವೇಗವಾಗಿ ಸಂದೇಶಗಳನ್ನು ಕಳುಹಿಸುತ್ತಿದ್ದೀರಿ. ಸ್ವಲ್ಪ ಕಾಯಿರಿ.",
        "reply_trimmed_suffix": "\n\n... (ಉತ್ತರ ಸಂಕ್ಷಿಪ್ತಗೊಳಿಸಲಾಗಿದೆ; ಪೂರ್ಣ ಉತ್ತರಕ್ಕಾಗಿ ಆಪ್ ತೆರೆಯಿರಿ)",
        "intent_labels": {
            "query": "ನಿಮ್ಮ ಪ್ರಾಣಿಗಳು ಅಥವಾ ದಾಖಲೆಗಳ ಬಗ್ಗೆ ಕೇಳಲು",
            "appointment": "ಪಶು ವೈದ್ಯರ ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ಅಥವಾ ಆರೋಗ್ಯ ಘಟನೆ ದಾಖಲಿಸಲು",
            "weather": "ಹವಾಮಾನ ನೋಡಲು",
            "add_animal": "ಹೊಸ ಪ್ರಾಣಿಯನ್ನು ನೋಂದಾಯಿಸಲು",
        },
    },
    "mr": {
        "blocked_intent": (
            "ही विनंती सध्या WhatsApp वर उपलब्ध नाही. यासाठी FarmHerd ॲप वापरा. "
            "WhatsApp वर तुम्ही काय करू शकता: {allowed_summary}."
        ),
        "unknown_farmer_enroll_prompt": (
            "नमस्कार! हा WhatsApp नंबर ओळखता आला नाही. कृपया तुमचा नोंदणीकृत "
            "फोन नंबर किंवा FarmHerd वापरकर्ता नाव पाठवा."
        ),
        "unknown_farmer_no_enroll": (
            "हा WhatsApp नंबर FarmHerd वर नोंदणीकृत नाही. कृपया सपोर्टशी संपर्क साधा."
        ),
        "enrollment_success": (
            "धन्यवाद {name} -- तुमचा WhatsApp आता FarmHerd खात्याशी लिंक झाला आहे. "
            "तुमचा प्रश्न पाठवा."
        ),
        "enrollment_failed": (
            "जुळणारे FarmHerd खाते सापडले नाही. कृपया तुमचा नोंदणीकृत फोन नंबर "
            "(+91XXXXXXXXXX स्वरूपात) किंवा वापरकर्ता नाव पाठवा."
        ),
        "enroll_code_sent": (
            "हा WhatsApp तुमच्या FarmHerd खात्याशी लिंक करण्यासाठी, तुमचा नोंदणीकृत फोन नंबर "
            "किंवा वापरकर्ता नाव पाठवा. ते एखाद्या खात्याशी जुळल्यास, आम्ही नोंदणीकृत "
            "फोनवर SMS द्वारे ६ अंकी कोड पाठवू -- कृपया तो कोड येथे पाठवा."
        ),
        "otp_wrong": "हा कोड चुकीचा आहे. कृपया SMS तपासा आणि पुन्हा प्रयत्न करा.",
        "otp_locked": (
            "अनेक वेळा चुकीचा कोड टाकला गेला. नवीन कोडसाठी तुमचा नोंदणीकृत फोन नंबर किंवा "
            "वापरकर्ता नाव पुन्हा पाठवा."
        ),
        "otp_expired": (
            "या कोडची मुदत संपली आहे. नवीन कोडसाठी तुमचा नोंदणीकृत फोन नंबर किंवा "
            "वापरकर्ता नाव पुन्हा पाठवा."
        ),
        "rate_limited": "तुम्ही खूप वेगाने संदेश पाठवत आहात. कृपया थोडा वेळ थांबा.",
        "reply_trimmed_suffix": "\n\n... (उत्तर संक्षिप्त केले आहे; पूर्ण उत्तरासाठी ॲप उघडा)",
        "intent_labels": {
            "query": "तुमच्या जनावरांबद्दल किंवा नोंदींबद्दल विचारा",
            "appointment": "पशुवैद्यकीय अपॉइंटमेंट बुक करा किंवा आरोग्याची नोंद करा",
            "weather": "हवामान पहा",
            "add_animal": "नवीन जनावर नोंदवा",
        },
    },
    "ml": {
        "blocked_intent": (
            "ഈ അഭ്യർത്ഥന ഇപ്പോൾ WhatsApp-ൽ ലഭ്യമല്ല. ഇതിനായി FarmHerd ആപ്പ് ഉപയോഗിക്കുക. "
            "WhatsApp-ൽ നിങ്ങൾക്ക് ചെയ്യാവുന്നത്: {allowed_summary}."
        ),
        "unknown_farmer_enroll_prompt": (
            "നമസ്കാരം! ഈ WhatsApp നമ്പർ തിരിച്ചറിയാനായില്ല. ദയവായി നിങ്ങളുടെ രജിസ്റ്റർ ചെയ്ത "
            "ഫോൺ നമ്പർ അല്ലെങ്കിൽ FarmHerd ഉപയോക്തൃനാമം അയയ്ക്കുക."
        ),
        "unknown_farmer_no_enroll": (
            "ഈ WhatsApp നമ്പർ FarmHerd-ൽ രജിസ്റ്റർ ചെയ്തിട്ടില്ല. ദയവായി സപ്പോർട്ടുമായി ബന്ധപ്പെടുക."
        ),
        "enrollment_success": (
            "നന്ദി {name} -- നിങ്ങളുടെ WhatsApp ഇപ്പോൾ FarmHerd അക്കൗണ്ടുമായി ലിങ്ക് ചെയ്തു. "
            "നിങ്ങളുടെ ചോദ്യം അയയ്ക്കുക."
        ),
        "enrollment_failed": (
            "പൊരുത്തപ്പെടുന്ന FarmHerd അക്കൗണ്ട് കണ്ടെത്തിയില്ല. ദയവായി നിങ്ങളുടെ രജിസ്റ്റർ ചെയ്ത ഫോൺ നമ്പർ "
            "(+91XXXXXXXXXX രൂപത്തിൽ) അല്ലെങ്കിൽ ഉപയോക്തൃനാമം അയയ്ക്കുക."
        ),
        "enroll_code_sent": (
            "ഈ WhatsApp നിങ്ങളുടെ FarmHerd അക്കൗണ്ടുമായി ലിങ്ക് ചെയ്യാൻ, നിങ്ങളുടെ രജിസ്റ്റർ ചെയ്ത ഫോൺ നമ്പർ "
            "അല്ലെങ്കിൽ ഉപയോക്തൃനാമം അയയ്ക്കുക. അത് ഒരു അക്കൗണ്ടുമായി പൊരുത്തപ്പെട്ടാൽ, രജിസ്റ്റർ ചെയ്ത "
            "ഫോണിലേക്ക് SMS വഴി 6 അക്ക കോഡ് അയയ്ക്കും -- ദയവായി ആ കോഡ് ഇവിടെ അയയ്ക്കുക."
        ),
        "otp_wrong": "ഈ കോഡ് തെറ്റാണ്. ദയവായി SMS പരിശോധിച്ച് വീണ്ടും ശ്രമിക്കുക.",
        "otp_locked": (
            "പലതവണ തെറ്റായ കോഡ് നൽകി. പുതിയ കോഡിനായി നിങ്ങളുടെ രജിസ്റ്റർ ചെയ്ത ഫോൺ നമ്പർ അല്ലെങ്കിൽ "
            "ഉപയോക്തൃനാമം വീണ്ടും അയയ്ക്കുക."
        ),
        "otp_expired": (
            "ഈ കോഡിന്റെ കാലാവധി കഴിഞ്ഞു. പുതിയ കോഡിനായി നിങ്ങളുടെ രജിസ്റ്റർ ചെയ്ത ഫോൺ നമ്പർ അല്ലെങ്കിൽ "
            "ഉപയോക്തൃനാമം വീണ്ടും അയയ്ക്കുക."
        ),
        "rate_limited": "നിങ്ങൾ വളരെ വേഗത്തിൽ സന്ദേശങ്ങൾ അയയ്ക്കുന്നു. ദയവായി അൽപ്പസമയം കാത്തിരിക്കുക.",
        "reply_trimmed_suffix": "\n\n... (മറുപടി ചുരുക്കിയിരിക്കുന്നു; പൂർണ്ണ മറുപടിക്കായി ആപ്പ് തുറക്കുക)",
        "intent_labels": {
            "query": "നിങ്ങളുടെ മൃഗങ്ങളെക്കുറിച്ചോ രേഖകളെക്കുറിച്ചോ ചോദിക്കുക",
            "appointment": "മൃഗഡോക്ടറുടെ അപ്പോയിന്റ്മെന്റ് ബുക്ക് ചെയ്യുക അല്ലെങ്കിൽ ആരോഗ്യ വിവരം രേഖപ്പെടുത്തുക",
            "weather": "കാലാവസ്ഥ നോക്കുക",
            "add_animal": "പുതിയ മൃഗത്തെ രജിസ്റ്റർ ചെയ്യുക",
        },
    },
}


def message(language: str, key: str, **values: Any) -> str:
    """Look up a catalog string. Falls back to English on unknown language;
    raises KeyError with the specific missing key if the key doesn't exist
    in either catalog (matching draft_supervisor._message's shape)."""
    lang = _lang(language)
    catalog = _TEXT.get(lang) or _TEXT.get("en", {})
    return str(catalog[key]).format(**values)


def summarize_allowed_intents(language: str, allowed: "frozenset[str] | set[str]") -> str:
    """Turn `{query, appointment}` into a localized human-readable list
    like "ask about your animals or records; book a vet appointment or
    log a health event". Order is deterministic (allowed_intents order in
    the config isn't guaranteed, so sort for stability)."""
    lang = _lang(language)
    labels_map = (_TEXT.get(lang) or _TEXT["en"]).get("intent_labels") or _TEXT["en"]["intent_labels"]
    ordered = sorted(allowed)
    return "; ".join(labels_map.get(i, i) for i in ordered)
