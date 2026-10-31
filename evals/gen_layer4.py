"""Generate evals/conversations/layer4_twist.json (layer 4: the farmer twists the conversation).

One theme list, written once per language, so all 7 languages always test the
same 15 cases. Run from the repo root:  python -m evals.gen_layer4
"""
from __future__ import annotations

import json
from pathlib import Path

CONV_DIR = Path(__file__).resolve().parent / "conversations"
OUT = CONV_DIR / "layer4_twist.json"
LANGS = ["en", "hi", "mr", "ta", "te", "kn", "ml"]
LOCALE = {l: f"{l}-IN" for l in LANGS}

APPT, REG, QRY = "appointment_supervisor", "animal_registration", "query_agent"


def tr(en, hi, mr, ta, te, kn, ml):
    return dict(zip(LANGS, (en, hi, mr, ta, te, kn, ml)))


# ---- shared sentences (same wording style as layers 1-3) -------------------
GAURI_FEVER_10 = tr(
    "GAURI has fever, need a vet tomorrow at 10 am",
    "GAURI को बुखार है, कल सुबह 10 बजे डॉक्टर चाहिए",
    "GAURI ला ताप आहे, उद्या सकाळी 10 वाजता डॉक्टर हवा",
    "GAURI க்கு காய்ச்சல், நாளை காலை 10 மணிக்கு டாக்டர் வேண்டும்",
    "GAURI కి జ్వరం, రేపు ఉదయం 10 గంటలకు డాక్టర్ కావాలి",
    "GAURI ಗೆ ಜ್ವರ, ನಾಳೆ ಬೆಳಿಗ್ಗೆ 10 ಗಂಟೆಗೆ ಡಾಕ್ಟರ್ ಬೇಕು",
    "GAURI ക്ക് പനി, നാളെ രാവിലെ 10 മണിക്ക് ഡോക്ടറെ വേണം")
MOTI_LIMP_10 = tr(
    "MOTI is limping, need a vet tomorrow at 10 am",
    "MOTI लंगड़ा रहा है, कल सुबह 10 बजे डॉक्टर चाहिए",
    "MOTI लंगडत आहे, उद्या सकाळी 10 वाजता डॉक्टर हवा",
    "MOTI நொண்டுகிறது, நாளை காலை 10 மணிக்கு டாக்டர் வேண்டும்",
    "MOTI కుంటుతోంది, రేపు ఉదయం 10 గంటలకు డాక్టర్ కావాలి",
    "MOTI ಕುಂಟುತ್ತಿದೆ, ನಾಳೆ ಬೆಳಿಗ್ಗೆ 10 ಗಂಟೆಗೆ ಡಾಕ್ಟರ್ ಬೇಕು",
    "MOTI മുടന്തുന്നു, നാളെ രാവിലെ 10 മണിക്ക് ഡോക്ടറെ വേണം")
CHINNI_NO_TIME = tr(
    "CHINNI has fever, need a vet tomorrow",
    "CHINNI को बुखार है, कल डॉक्टर चाहिए",
    "CHINNI ला ताप आहे, उद्या डॉक्टर हवा",
    "CHINNI க்கு காய்ச்சல், நாளை டாக்டர் வேண்டும்",
    "CHINNI కి జ్వరం, రేపు డాక్టర్ కావాలి",
    "CHINNI ಗೆ ಜ್ವರ, ನಾಳೆ ಡಾಕ್ಟರ್ ಬೇಕು",
    "CHINNI ക്ക് പനി, നാളെ ഡോക്ടറെ വേണം")
AT_10 = tr("10 am", "सुबह 10 बजे", "सकाळी 10 वाजता", "காலை 10 மணிக்கு",
           "ఉదయం 10 గంటలకు", "ಬೆಳಿಗ್ಗೆ 10 ಗಂಟೆಗೆ", "രാവിലെ 10 മണിക്ക്")
AT_5PM = tr("5 pm", "शाम 5 बजे", "संध्याकाळी 5 वाजता", "மாலை 5 மணிக்கு",
            "సాయంత్రం 5 గంటలకు", "ಸಂಜೆ 5 ಗಂಟೆಗೆ", "വൈകുന്നേരം 5 മണിക്ക്")
REGISTER_NEW = tr(
    "I want to register a new animal",
    "मुझे नया पशु पंजीकृत करना है",
    "मला नवीन जनावर नोंदवायचे आहे",
    "நான் ஒரு புதிய விலங்கை பதிவு செய்ய விரும்புகிறேன்",
    "నేను కొత్త జంతువును నమోదు చేయాలనుకుంటున్నాను",
    "ನಾನು ಹೊಸ ಪ್ರಾಣಿಯನ್ನು ನೋಂದಾಯಿಸಲು ಬಯಸುತ್ತೇನೆ",
    "എനിക്ക് പുതിയ മൃഗത്തെ രജിസ്റ്റർ ചെയ്യണം")
GOATS_Q = tr("how many goats do I have?", "मेरे पास कितनी बकरियाँ हैं?", "माझ्याकडे किती शेळ्या आहेत?",
             "என்னிடம் எத்தனை வெள்ளாடுகள் உள்ளன?", "నా దగ్గర ఎన్ని మేకలు ఉన్నాయి?",
             "ನನ್ನ ಬಳಿ ಎಷ್ಟು ಮೇಕೆಗಳು ಇವೆ?", "എന്റെ കയ്യിൽ എത്ര ആടുകൾ ഉണ്ട്?")
COWS_Q = tr("how many cows do I have?", "मेरे पास कितनी गायें हैं?", "माझ्याकडे किती गायी आहेत?",
            "என்னிடம் எத்தனை பசுக்கள் உள்ளன?", "నా దగ్గర ఎన్ని ఆవులు ఉన్నాయి?",
            "ನನ್ನ ಬಳಿ ಎಷ್ಟು ಹಸುಗಳು ಇವೆ?", "എന്റെ കയ്യിൽ എത്ര പശുക്കൾ ഉണ്ട്?")
SHEEP_Q = tr("how many sheep do I have?", "मेरे पास कितनी भेड़ें हैं?", "माझ्याकडे किती मेंढ्या आहेत?",
             "என்னிடம் எத்தனை செம்மறி ஆடுகள் உள்ளன?", "నా దగ్గర ఎన్ని గొర్రెలు ఉన్నాయి?",
             "ನನ್ನ ಬಳಿ ಎಷ್ಟು ಕುರಿಗಳು ಇವೆ?", "എന്റെ കയ്യിൽ എത്ര ചെമ്മരിയാടുകൾ ഉണ്ട്?")
SHEEP_SHORT = tr("and sheep?", "और भेड़ें?", "आणि मेंढ्या?", "செம்மறி ஆடுகள்?", "గొర్రెలు?", "ಕುರಿಗಳು?",
                 "ചെമ്മരിയാടുകൾ?")
MY_BOOKING = tr("what about my booking?", "मेरी बुकिंग का क्या हुआ?", "माझ्या बुकिंगचं काय झालं?",
                "என் புக்கிங் என்ன ஆனது?", "నా బుకింగ్ ఏమైంది?", "ನನ್ನ ಬುಕಿಂಗ್ ಏನಾಯಿತು?",
                "എന്റെ ബുക്കിംഗ് എന്തായി?")
# Latin and native spellings of Paris, so an answer to the capital question is caught.
PARIS = ["Paris", "पेरिस", "पॅरिस", "பாரிஸ்", "పారిస్", "ಪ್ಯಾರಿಸ್", "പാരിസ്"]


def e(agent=None, **kw):
    out = {}
    if agent:
        out["agent"] = agent
    out.update({k: v for k, v in kw.items() if v is not None})
    return out


def kaali_breed_words(lang: str) -> list[str]:
    """Same accepted spellings of Jamunapari that layer 3 uses for the KAALI breed question."""
    doc = json.loads((CONV_DIR / "layer3_mixed.json").read_text(encoding="utf-8"))
    c = next(c for c in doc["conversations"] if c["id"] == f"L3-{lang}-004")
    return c["turns"][0]["expect"]["reply_contains_any"]


def themes(lang: str):
    """(title, mutates, [(user, expect), ...]) for each of the 15 themes."""
    g = lambda d: d[lang]
    booking_gauri = ("{}".format(g(GAURI_FEVER_10)),
                     e(APPT, reply_contains_all=["GAURI", "{date+1}", "10:00"]))
    return [
        ("Mid-booking switch to registration: the registration starts and the booking does not come back", True, [
            booking_gauri,
            (g(tr("forget the vet, I want to register a new goat",
                  "डॉक्टर रहने दो, मुझे एक नई बकरी पंजीकृत करनी है",
                  "डॉक्टर राहू द्या, मला एक नवीन शेळी नोंदवायची आहे",
                  "டாக்டர் வேண்டாம், ஒரு புதிய வெள்ளாட்டை பதிவு செய்ய வேண்டும்",
                  "డాక్టర్ వద్దు, నేను ఒక కొత్త మేకను నమోదు చేయాలి",
                  "ಡಾಕ್ಟರ್ ಬೇಡ, ನಾನು ಒಂದು ಹೊಸ ಮೇಕೆಯನ್ನು ನೋಂದಾಯಿಸಬೇಕು",
                  "ഡോക്ടർ വേണ്ട, എനിക്ക് ഒരു പുതിയ ആടിനെ രജിസ്റ്റർ ചെയ്യണം")),
             e(REG, reply_not_contains=["10:00"])),
            (g(GOATS_Q), e(REG, number=14)),
        ]),
        ("Mid-registration switch to booking: the booking starts with the right animal", True, [
            (g(REGISTER_NEW), e(REG)),
            (g(tr("leave that, GAURI has fever, I need a vet tomorrow at 10 am",
                  "वो रहने दो, GAURI को बुखार है, कल सुबह 10 बजे डॉक्टर चाहिए",
                  "ते राहू द्या, GAURI ला ताप आहे, उद्या सकाळी 10 वाजता डॉक्टर हवा",
                  "அதை விடுங்கள், GAURI க்கு காய்ச்சல், நாளை காலை 10 மணிக்கு டாக்டர் வேண்டும்",
                  "అది వద్దు, GAURI కి జ్వరం, రేపు ఉదయం 10 గంటలకు డాక్టర్ కావాలి",
                  "ಅದು ಬೇಡ, GAURI ಗೆ ಜ್ವರ, ನಾಳೆ ಬೆಳಿಗ್ಗೆ 10 ಗಂಟೆಗೆ ಡಾಕ್ಟರ್ ಬೇಕು",
                  "അത് വേണ്ട, GAURI ക്ക് പനി, നാളെ രാവിലെ 10 മണിക്ക് ഡോക്ടറെ വേണം")),
             e(APPT, reply_contains_all=["GAURI", "{date+1}", "10:00"])),
            (g(SHEEP_Q), e(APPT, number=7, reply_contains_all=["{date+1}"])),
        ]),
        ("Animal and problem both changed in one message: GAURI is fine, MOTI is sick", True, [
            booking_gauri,
            (g(tr("GAURI is fine now, actually MOTI has a cough",
                  "GAURI अब ठीक है, असल में MOTI को खांसी है",
                  "GAURI आता बरी आहे, खरं तर MOTI ला खोकला आहे",
                  "GAURI இப்போது நலமாக இருக்கிறது, உண்மையில் MOTI க்கு இருமல்",
                  "GAURI ఇప్పుడు బాగుంది, నిజానికి MOTI కి దగ్గు ఉంది",
                  "GAURI ಈಗ ಚೆನ್ನಾಗಿದೆ, ನಿಜವಾಗಿ MOTI ಗೆ ಕೆಮ್ಮು ಇದೆ",
                  "GAURI ഇപ്പോൾ ഓക്കെയാണ്, ശരിക്കും MOTI ക്ക് ചുമയാണ്")),
             e(APPT, reply_contains_all=["MOTI", "{date+1}", "10:00"], reply_not_contains=["GAURI"])),
        ]),
        ("Booking at the readback, then two farm questions (the second one short), then 'what about my booking?'", True, [
            booking_gauri,
            (g(COWS_Q), e(APPT, number=9, reply_contains_all=["{date+1}"])),
            (g(SHEEP_SHORT), e(APPT, number=7, reply_contains_all=["{date+1}"])),
            (g(MY_BOOKING), e(APPT, reply_contains_all=["GAURI", "{date+1}"])),
        ]),
        ("General-knowledge questions in the middle of a booking: not answered, booking kept", True, [
            booking_gauri,
            (g(tr("what is the capital of France?", "फ्रांस की राजधानी क्या है?", "फ्रान्सची राजधानी कोणती?",
                  "பிரான்ஸின் தலைநகரம் எது?", "ఫ్రాన్స్ రాజధాని ఏది?", "ಫ್ರಾನ್ಸ್‌ನ ರಾಜಧಾನಿ ಯಾವುದು?",
                  "ഫ്രാൻസിന്റെ തലസ്ഥാനം ഏതാണ്?")),
             e(APPT, reply_not_contains=PARIS, reply_contains_all=["{date+1}"])),
            (g(tr("who won the cricket match yesterday?", "कल क्रिकेट मैच कौन जीता?",
                  "काल क्रिकेट सामना कोण जिंकला?", "நேற்று கிரிக்கெட் போட்டியில் யார் வென்றார்கள்?",
                  "నిన్న క్రికెట్ మ్యాచ్ ఎవరు గెలిచారు?", "ನಿನ್ನೆ ಕ್ರಿಕೆಟ್ ಪಂದ್ಯ ಯಾರು ಗೆದ್ದರು?",
                  "ഇന്നലത്തെ ക്രിക്കറ്റ് മത്സരം ആരാണ് ജയിച്ചത്?")),
             e(APPT, reply_contains_all=["{date+1}"])),
        ]),
        ("Hello, thanks and 'ok' in the middle of a booking: nothing is cancelled or confirmed", True, [
            (g(CHINNI_NO_TIME), e(APPT)),
            (g(tr("hello", "नमस्ते", "नमस्कार", "வணக்கம்", "నమస్కారం", "ನಮಸ್ಕಾರ", "നമസ്കാരം")), e(APPT)),
            (g(tr("thank you", "धन्यवाद", "धन्यवाद", "நன்றி", "ధన్యవాదాలు", "ಧನ್ಯವಾದಗಳು", "നന്ദി")), e(APPT)),
            (g(tr("ok", "ठीक है", "ठीक आहे", "சரி", "సరే", "ಸರಿ", "ശരി")), e(APPT)),
            (g(AT_10), e(APPT, reply_contains_all=["CHINNI", "{date+1}", "10:00"])),
        ]),
        ("A 'yes' right after a side answer while the time is still missing: no booking is made, the time is still asked", True, [
            (g(CHINNI_NO_TIME), e(APPT)),
            (g(GOATS_Q), e(APPT, number=14, reply_contains_all=["{date+1}"])),
            # A re-ask of the missing time need not repeat the date; the next turn proves the draft is kept.
            (g(tr("yes", "हाँ", "हो", "ஆம்", "అవును", "ಹೌದು", "അതെ")), e(APPT)),
            (g(AT_5PM), e(APPT, reply_contains_all=["CHINNI", "{date+1}", "17:00"])),
        ]),
        ("Cancel the booking and ask a count in the same message, then a count goes to the query agent", True, [
            booking_gauri,
            (g(tr("cancel the booking and tell me how many cows I have",
                  "बुकिंग रद्द करो और बताओ मेरे पास कितनी गायें हैं",
                  "बुकिंग रद्द करा आणि माझ्याकडे किती गायी आहेत ते सांगा",
                  "புக்கிங்கை ரத்து செய்யுங்கள், என்னிடம் எத்தனை பசுக்கள் உள்ளன என்று சொல்லுங்கள்",
                  "బుకింగ్ రద్దు చేయండి, నా దగ్గర ఎన్ని ఆవులు ఉన్నాయో చెప్పండి",
                  "ಬುಕಿಂಗ್ ರದ್ದು ಮಾಡಿ, ನನ್ನ ಬಳಿ ಎಷ್ಟು ಹಸುಗಳು ಇವೆ ಎಂದು ಹೇಳಿ",
                  "ബുക്കിംഗ് റദ്ദാക്കൂ, എന്റെ കയ്യിൽ എത്ര പശുക്കൾ ഉണ്ടെന്ന് പറയൂ")),
             e(number=9)),
            (g(SHEEP_Q), e(QRY, number=7)),
        ]),
        ("One long message: a booking for GAURI and a buffalo count together", True, [
            (g(tr("GAURI has fever so I want a vet tomorrow at 10 am, and also tell me how many buffaloes I have",
                  "GAURI को बुखार है तो कल सुबह 10 बजे डॉक्टर बुक करो, और हाँ बताओ मेरे पास कितनी भैंसें हैं",
                  "GAURI ला ताप आहे म्हणून उद्या सकाळी 10 वाजता डॉक्टर बुक करा, आणि माझ्याकडे किती म्हशी आहेत ते पण सांगा",
                  "GAURI க்கு காய்ச்சல், அதனால் நாளை காலை 10 மணிக்கு டாக்டர் புக் செய்யுங்கள், மேலும் என்னிடம் எத்தனை எருமைகள் உள்ளன என்றும் சொல்லுங்கள்",
                  "GAURI కి జ్వరం కాబట్టి రేపు ఉదయం 10 గంటలకు డాక్టర్ బుక్ చేయండి, అలాగే నా దగ్గర ఎన్ని గేదెలు ఉన్నాయో కూడా చెప్పండి",
                  "GAURI ಗೆ ಜ್ವರ ಇರುವುದರಿಂದ ನಾಳೆ ಬೆಳಿಗ್ಗೆ 10 ಗಂಟೆಗೆ ಡಾಕ್ಟರ್ ಬುಕ್ ಮಾಡಿ, ಜೊತೆಗೆ ನನ್ನ ಬಳಿ ಎಷ್ಟು ಎಮ್ಮೆಗಳು ಇವೆ ಎಂದೂ ಹೇಳಿ",
                  "GAURI ക്ക് പനിയാണ്, അതുകൊണ്ട് നാളെ രാവിലെ 10 മണിക്ക് ഡോക്ടറെ ബുക്ക് ചെയ്യൂ, കൂടാതെ എന്റെ കയ്യിൽ എത്ര എരുമകൾ ഉണ്ടെന്നും പറയൂ")),
             e(number=16, reply_contains_all=["GAURI", "{date+1}", "10:00"])),
            (g(MY_BOOKING), e(APPT, reply_contains_all=["GAURI", "{date+1}"])),
        ]),
        ("Language switch in the middle of a booking: details kept, the reply follows what the farmer typed", True, [
            (("CHINNI has fever, need a vet tomorrow" if lang == "en" else g(CHINNI_NO_TIME)), e(APPT)),
            (("subah 10 baje kar do" if lang == "en" else "make it 10 am please"),
             e(APPT, reply_contains_all=["CHINNI", "{date+1}", "10:00"], script=False)),
            (g(MY_BOOKING), e(APPT, reply_contains_all=["CHINNI", "{date+1}", "10:00"])),
        ]),
        ("Date changed after the readback, then the time, then back to the first date", True, [
            booking_gauri,
            (g(tr("no, make it the day after tomorrow", "नहीं, परसों रखो", "नाही, परवा ठेवा",
                  "இல்லை, நாளை மறுநாள் வையுங்கள்", "వద్దు, ఎల్లుండి పెట్టండి", "ಬೇಡ, ನಾಡಿದ್ದು ಇಡಿ",
                  "വേണ്ട, മറ്റന്നാൾ ആക്കൂ")),
             e(APPT, reply_contains_all=["{date+2}", "10:00"])),
            (g(tr("actually make it 11 am", "असल में सुबह 11 बजे कर दो", "खरं तर सकाळी 11 वाजता करा",
                  "உண்மையில் காலை 11 மணிக்கு வையுங்கள்", "నిజానికి ఉదయం 11 గంటలకు పెట్టండి",
                  "ನಿಜವಾಗಿ ಬೆಳಿಗ್ಗೆ 11 ಗಂಟೆಗೆ ಇಡಿ", "ശരിക്കും രാവിലെ 11 മണിക്ക് ആക്കൂ")),
             e(APPT, reply_contains_all=["{date+2}", "11:00"])),
            (g(tr("no wait, tomorrow was right, keep tomorrow", "नहीं रुको, कल ही ठीक था, कल ही रखो",
                  "नाही थांबा, उद्याच बरोबर होतं, उद्याच ठेवा", "இல்லை, நாளையே சரி, நாளைக்கே வையுங்கள்",
                  "వద్దు ఆగండి, రేపే సరైనది, రేపే పెట్టండి", "ಬೇಡ ಇರಿ, ನಾಳೆಯೇ ಸರಿ, ನಾಳೆಯೇ ಇಡಿ",
                  "വേണ്ട, നാളെ തന്നെയായിരുന്നു ശരി, നാളെ തന്നെ ആക്കൂ")),
             e(APPT, reply_contains_all=["GAURI", "{date+1}", "11:00"])),
        ]),
        ("Back to an open booking after three other topics", True, [
            (g(MOTI_LIMP_10), e(APPT, reply_contains_all=["MOTI", "{date+1}", "10:00"])),
            (g(GOATS_Q), e(APPT, number=14)),
            (g(tr("which breed is KAALI?", "KAALI की नस्ल क्या है?", "KAALI ची जात कोणती आहे?",
                  "KAALI என்ன இனம்?", "KAALI ఏ జాతి?", "KAALI ಯಾವ ತಳಿ?", "KAALI ഏത് ഇനമാണ്?")),
             e(APPT, reply_contains_any=kaali_breed_words(lang))),
            (g(SHEEP_SHORT), e(APPT, number=7)),
            (g(MY_BOOKING), e(APPT, reply_contains_all=["MOTI", "{date+1}", "10:00"])),
        ]),
        ("Farmer corrects the bot: 'no, I asked about buffaloes, not cows'", False, [
            (g(COWS_Q), e(QRY, number=9)),
            (g(tr("no, I asked about buffaloes, not cows",
                  "नहीं, मैंने भैंसों के बारे में पूछा था, गायों के बारे में नहीं",
                  "नाही, मी म्हशींबद्दल विचारलं, गायींबद्दल नाही",
                  "இல்லை, நான் எருமைகளைப் பற்றி கேட்டேன், பசுக்களை அல்ல",
                  "కాదు, నేను గేదెల గురించి అడిగాను, ఆవుల గురించి కాదు",
                  "ಅಲ್ಲ, ನಾನು ಎಮ್ಮೆಗಳ ಬಗ್ಗೆ ಕೇಳಿದ್ದು, ಹಸುಗಳ ಬಗ್ಗೆ ಅಲ್ಲ",
                  "അല്ല, ഞാൻ ചോദിച്ചത് എരുമകളെക്കുറിച്ചാണ്, പശുക്കളെക്കുറിച്ചല്ല")),
             e(QRY, number=16)),
            (g(SHEEP_SHORT), e(QRY, number=7)),
        ]),
        ("Registration of BHOORI dropped halfway, then a breed question about BHOORI: no such animal", True, [
            (g(tr("I want to register a new goat, named BHOORI",
                  "मुझे एक नई बकरी पंजीकृत करनी है, नाम BHOORI",
                  "मला एक नवीन शेळी नोंदवायची आहे, नाव BHOORI",
                  "ஒரு புதிய வெள்ளாட்டை பதிவு செய்ய வேண்டும், பெயர் BHOORI",
                  "ఒక కొత్త మేకను నమోదు చేయాలి, పేరు BHOORI",
                  "ಒಂದು ಹೊಸ ಮೇಕೆಯನ್ನು ನೋಂದಾಯಿಸಬೇಕು, ಹೆಸರು BHOORI",
                  "ഒരു പുതിയ ആടിനെ രജിസ്റ്റർ ചെയ്യണം, പേര് BHOORI")), e(REG)),
            (g(tr("leave it, cancel", "रहने दो, रद्द करो", "राहू द्या, रद्द करा", "வேண்டாம், ரத்து செய்யுங்கள்",
                  "వద్దు, రద్దు చేయండి", "ಬೇಡ, ರದ್ದು ಮಾಡಿ", "വേണ്ട, റദ്ദാക്കൂ")), e(REG)),
            (g(tr("what breed is BHOORI?", "BHOORI की नस्ल क्या है?", "BHOORI ची जात कोणती आहे?",
                  "BHOORI என்ன இனம்?", "BHOORI ఏ జాతి?", "BHOORI ಯಾವ ತಳಿ?", "BHOORI ഏത് ഇനമാണ്?")),
             e(QRY, reply_not_contains=["Sirohi", "Jamunapari", "Beetal", "Murrah", "Kankrej", "Mehsana"])),
        ]),
        ("Very short replies in the middle of a booking ('hmm', '?', 'wait'): the booking is kept and asked again", True, [
            (g(CHINNI_NO_TIME), e(APPT)),
            (g(tr("hmm", "हम्म", "हम्म", "ம்ம்", "హ్మ్", "ಹ್ಮ್", "ഹ്മ്")), e(APPT)),
            ("?", e(APPT)),
            (g(tr("wait", "रुको", "थांबा", "இருங்கள்", "ఆగండి", "ಇರಿ", "നിൽക്കൂ")), e(APPT)),
            (g(AT_10), e(APPT, reply_contains_all=["CHINNI", "{date+1}", "10:00"])),
        ]),
    ]


# ---- themes 16-30 ----------------------------------------------------------
MOTI_LIMP_11 = tr(
    "MOTI is limping, need a vet tomorrow at 11 am",
    "MOTI लंगड़ा रहा है, कल सुबह 11 बजे डॉक्टर चाहिए",
    "MOTI लंगडत आहे, उद्या सकाळी 11 वाजता डॉक्टर हवा",
    "MOTI நொண்டுகிறது, நாளை காலை 11 மணிக்கு டாக்டர் வேண்டும்",
    "MOTI కుంటుతోంది, రేపు ఉదయం 11 గంటలకు డాక్టర్ కావాలి",
    "MOTI ಕುಂಟುತ್ತಿದೆ, ನಾಳೆ ಬೆಳಿಗ್ಗೆ 11 ಗಂಟೆಗೆ ಡಾಕ್ಟರ್ ಬೇಕು",
    "MOTI മുടന്തുന്നു, നാളെ രാവിലെ 11 മണിക്ക് ഡോക്ടറെ വേണം")
AT_4PM = tr("4 pm", "शाम 4 बजे", "दुपारी 4 वाजता", "மாலை 4 மணிக்கு",
            "సాయంత్రం 4 గంటలకు", "ಸಂಜೆ 4 ಗಂಟೆಗೆ", "വൈകുന്നേരം 4 മണിക്ക്")
CANCEL_IT = tr("cancel it", "इसे रद्द करो", "हे रद्द करा", "இதை ரத்து செய்யுங்கள்",
               "దీన్ని రద్దు చేయండి", "ಇದನ್ನು ರದ್ದು ಮಾಡಿ", "ഇത് റദ്ദാക്കൂ")
LEAVE_CANCEL = tr("leave it, cancel", "रहने दो, रद्द करो", "राहू द्या, रद्द करा", "வேண்டாம், ரத்து செய்யுங்கள்",
                  "వద్దు, రద్దు చేయండి", "ಬೇಡ, ರದ್ದು ಮಾಡಿ", "വേണ്ട, റദ്ദാക്കൂ")
REGISTER_GOAT = tr("I want to register a new goat", "मुझे एक नई बकरी पंजीकृत करनी है",
                   "मला एक नवीन शेळी नोंदवायची आहे", "ஒரு புதிய வெள்ளாட்டை பதிவு செய்ய வேண்டும்",
                   "ఒక కొత్త మేకను నమోదు చేయాలి", "ಒಂದು ಹೊಸ ಮೇಕೆಯನ್ನು ನೋಂದಾಯಿಸಬೇಕು",
                   "ഒരു പുതിയ ആടിനെ രജിസ്റ്റർ ചെയ്യണം")


def weather_no_place(lang: str):
    """Today's-weather question with no place, and the PIN words the reply must ask for (from layer 3)."""
    doc = json.loads((CONV_DIR / "layer3_mixed.json").read_text(encoding="utf-8"))
    c = next(c for c in doc["conversations"] if c["id"] == f"L3-{lang}-012")
    return c["turns"][0]["user"], c["turns"][0]["expect"]["reply_contains_any"]


def themes_more(lang: str):
    g = lambda d: d[lang]
    booking_gauri = (g(GAURI_FEVER_10), e(APPT, reply_contains_all=["GAURI", "{date+1}", "10:00"]))
    chinni_then_10 = [(g(CHINNI_NO_TIME), e(APPT))]
    finish_10 = (g(AT_10), e(APPT, reply_contains_all=["CHINNI", "{date+1}", "10:00"]))
    w_text, w_pin = weather_no_place(lang)
    return [
        ("Weather asks for a PIN, the farmer registers an animal instead: registration takes over", True, [
            (w_text, e("weather_alert", reply_contains_any=w_pin)),
            (g(REGISTER_NEW), e(REG)),
            (g(GOATS_Q), e(REG, number=14)),
        ]),
        ("Weather question with no place in a booking: the PIN is asked, the farmer ignores it and gives the time", True, [
            *chinni_then_10,
            (w_text, e(APPT, reply_contains_any=w_pin)),
            finish_10,
        ]),
        ("Booking cancelled, then a new booking for another animal with another time", True, [
            booking_gauri,
            (g(CANCEL_IT), e(APPT)),
            (g(MOTI_LIMP_11), e(APPT, reply_contains_all=["MOTI", "{date+1}", "11:00"], reply_not_contains=["GAURI"])),
        ]),
        ("Registration cancelled, then straight into a booking", True, [
            (g(REGISTER_NEW), e(REG)),
            (g(LEAVE_CANCEL), e(REG)),
            booking_gauri,
        ]),
        ("A bare 'no' at the readback (not a cancel), then a new time", True, [
            booking_gauri,
            (g(tr("no", "नहीं", "नाही", "இல்லை", "కాదు", "ಇಲ್ಲ", "അല്ല")), e(APPT)),
            (g(AT_4PM), e(APPT, reply_contains_all=["GAURI", "{date+1}", "16:00"])),
        ]),
        ("Question about the booking itself: which animal is it for?", True, [
            booking_gauri,
            (g(tr("which animal is this booking for?", "यह बुकिंग किस पशु के लिए है?",
                  "ही बुकिंग कोणत्या जनावरासाठी आहे?", "இந்த புக்கிங் எந்த விலங்குக்கு?",
                  "ఈ బుకింగ్ ఏ జంతువు కోసం?", "ಈ ಬುಕಿಂಗ್ ಯಾವ ಪ್ರಾಣಿಗಾಗಿ?", "ഈ ബുക്കിംഗ് ഏത് മൃഗത്തിനാണ്?")),
             e(APPT, reply_contains_all=["GAURI", "{date+1}"])),
        ]),
        ("'Sorry, what did you say?' in the middle of a booking: the question is asked again", True, [
            *chinni_then_10,
            (g(tr("sorry, what did you say?", "माफ़ कीजिए, आपने क्या कहा?", "माफ करा, तुम्ही काय म्हणालात?",
                  "மன்னிக்கவும், என்ன சொன்னீர்கள்?", "క్షమించండి, మీరు ఏమన్నారు?",
                  "ಕ್ಷಮಿಸಿ, ನೀವು ಏನು ಹೇಳಿದಿರಿ?", "ക്ഷമിക്കണം, നിങ്ങൾ എന്താണ് പറഞ്ഞത്?")), e(APPT)),
            finish_10,
        ]),
        ("A farmer who is annoyed in the middle of a booking: polite reply, the booking is kept", True, [
            *chinni_then_10,
            (g(tr("this is taking too long, you are useless",
                  "इसमें बहुत देर लग रही है, तुम किसी काम के नहीं हो",
                  "यात खूप वेळ लागतोय, तुम्ही काही कामाचे नाही",
                  "இது ரொம்ப நேரம் ஆகிறது, நீங்கள் எதற்கும் உதவ மாட்டீர்கள்",
                  "ఇది చాలా ఆలస్యం అవుతోంది, మీరు ఎందుకూ పనికిరారు",
                  "ಇದು ತುಂಬಾ ತಡವಾಗುತ್ತಿದೆ, ನೀವು ಯಾವುದಕ್ಕೂ ಪ್ರಯೋಜನವಿಲ್ಲ",
                  "ഇതിന് വളരെ താമസം, നിങ്ങൾ ഒന്നിനും കൊള്ളില്ല")), e(APPT)),
            finish_10,
        ]),
        ("A thumbs-up emoji and a nonsense word in the middle of a booking: nothing is confirmed, the booking is kept", True, [
            *chinni_then_10,
            ("\U0001F44D", e(APPT)),
            ("asdfgh", e(APPT)),
            finish_10,
        ]),
        ("'Are you a real person?' in the middle of a booking: answered, booking kept", True, [
            *chinni_then_10,
            (g(tr("are you a real person?", "क्या तुम असली इंसान हो?", "तुम्ही खरे माणूस आहात का?",
                  "நீங்கள் உண்மையான மனிதரா?", "మీరు నిజమైన మనిషా?", "ನೀವು ನಿಜವಾದ ಮನುಷ್ಯರೇ?",
                  "നിങ്ങൾ യഥാർത്ഥ മനുഷ്യനാണോ?")), e(APPT)),
            finish_10,
        ]),
        ("'Forget all this, start again' with a new animal and a new time", True, [
            booking_gauri,
            (g(tr("forget all this, start again: ", "यह सब छोड़ो, फिर से शुरू करो: ",
                  "हे सगळं सोडा, पुन्हा सुरू करा: ", "இதையெல்லாம் விடுங்கள், மீண்டும் தொடங்குங்கள்: ",
                  "ఇదంతా వదిలేయండి, మళ్ళీ మొదలుపెట్టండి: ", "ಇದೆಲ್ಲ ಬಿಡಿ, ಮತ್ತೆ ಪ್ರಾರಂಭಿಸಿ: ",
                  "ഇതെല്ലാം വിടൂ, വീണ്ടും തുടങ്ങൂ: ")) + g(MOTI_LIMP_11),
             e(APPT, reply_contains_all=["MOTI", "{date+1}", "11:00"], reply_not_contains=["GAURI"])),
        ]),
        ("Registration: the farmer changes the species ('it is a sheep, not a goat'), the registration goes on", True, [
            (g(REGISTER_GOAT), e(REG)),
            (g(tr("no wait, it is a sheep, not a goat", "नहीं रुको, यह भेड़ है, बकरी नहीं",
                  "नाही थांबा, ही मेंढी आहे, शेळी नाही", "இல்லை, இது செம்மறி ஆடு, வெள்ளாடு அல்ல",
                  "కాదు ఆగండి, ఇది గొర్రె, మేక కాదు", "ಅಲ್ಲ ಇರಿ, ಇದು ಕುರಿ, ಮೇಕೆ ಅಲ್ಲ",
                  "അല്ല, ഇത് ചെമ്മരിയാടാണ്, ആടല്ല")), e(REG)),
            (g(SHEEP_Q), e(REG, number=7)),
        ]),
        ("A greeting as the very first message, then a booking", True, [
            (g(tr("hello", "नमस्ते", "नमस्कार", "வணக்கம்", "నమస్కారం", "ನಮಸ್ಕಾರ", "നമസ്കാരം")), e()),
            booking_gauri,
        ]),
        ("A long story with the booking request hidden in it", True, [
            (g(tr("Yesterday it rained a lot here and the shed got wet. Since the morning GAURI has not eaten anything and has fever, so please send a vet tomorrow at 10 am",
                  "कल यहाँ बहुत बारिश हुई और बाड़ा गीला हो गया। सुबह से GAURI ने कुछ नहीं खाया और उसे बुखार है, इसलिए कृपया कल सुबह 10 बजे डॉक्टर भेज दीजिए",
                  "काल इथे खूप पाऊस पडला आणि गोठा ओला झाला. सकाळपासून GAURI ने काहीच खाल्लेले नाही आणि तिला ताप आहे, म्हणून कृपया उद्या सकाळी 10 वाजता डॉक्टर पाठवा",
                  "நேற்று இங்கே நிறைய மழை பெய்தது, கொட்டகை நனைந்துவிட்டது. காலையிலிருந்து GAURI எதுவும் சாப்பிடவில்லை, காய்ச்சலும் இருக்கிறது, அதனால் தயவுசெய்து நாளை காலை 10 மணிக்கு டாக்டரை அனுப்புங்கள்",
                  "నిన్న ఇక్కడ చాలా వర్షం పడింది, పాక తడిసిపోయింది. ఉదయం నుంచి GAURI ఏమీ తినలేదు, జ్వరం కూడా ఉంది, కాబట్టి దయచేసి రేపు ఉదయం 10 గంటలకు డాక్టర్‌ను పంపండి",
                  "ನಿನ್ನೆ ಇಲ್ಲಿ ತುಂಬಾ ಮಳೆ ಬಂತು, ದೊಡ್ಡಿ ಒದ್ದೆಯಾಯಿತು. ಬೆಳಿಗ್ಗೆಯಿಂದ GAURI ಏನೂ ತಿಂದಿಲ್ಲ, ಜ್ವರವೂ ಇದೆ, ಆದ್ದರಿಂದ ದಯವಿಟ್ಟು ನಾಳೆ ಬೆಳಿಗ್ಗೆ 10 ಗಂಟೆಗೆ ಡಾಕ್ಟರ್ ಕಳುಹಿಸಿ",
                  "ഇന്നലെ ഇവിടെ നല്ല മഴയായിരുന്നു, തൊഴുത്ത് നനഞ്ഞു. രാവിലെ മുതൽ GAURI ഒന്നും കഴിച്ചിട്ടില്ല, പനിയുമുണ്ട്, അതുകൊണ്ട് ദയവായി നാളെ രാവിലെ 10 മണിക്ക് ഡോക്ടറെ അയയ്ക്കൂ")),
             e(APPT, reply_contains_all=["GAURI", "{date+1}", "10:00"])),
        ]),
        ("'Never mind' (not the word cancel): the booking is dropped and the next count goes to the query agent", True, [
            booking_gauri,
            (g(tr("never mind", "छोड़ो, रहने दो", "जाऊ द्या, राहू द्या", "விடுங்கள், பரவாயில்லை",
                  "వదిలేయండి, పర్వాలేదు", "ಬಿಡಿ, ಪರವಾಗಿಲ್ಲ", "വിട്ടേക്കൂ, സാരമില്ല")), e(APPT)),
            (g(SHEEP_Q), e(QRY, number=7)),
        ]),
    ]


def build() -> dict:
    convs = []
    for lang in LANGS:
        for n, (title, mutates, turns) in enumerate(themes(lang) + themes_more(lang), 1):
            convs.append({
                "id": f"L4-{lang}-{n:03d}",
                "language": LOCALE[lang],
                "title": title,
                "mutates": mutates,
                "turns": [{"user": u, "expect": ex} for u, ex in turns],
            })
    return {
        "layer": 4,
        "name": "twist",
        "description": ("The farmer twists the conversation completely: leaves a booking for a registration "
                        "or the other way round, changes animal and problem in one message, asks something "
                        "unrelated or off-topic, says only hello / thanks / ok / 'hmm', gives a bare 'yes' at a "
                        "wrong moment, cancels and asks in one message, changes language, changes his mind "
                        "about the date again and again, comes back to an old booking, corrects the bot, or "
                        "drops a registration and asks about that animal. 30 per language. Bookings and "
                        "registrations never get the final 'yes', so nothing is saved."),
        "farmer_id": "f-001",
        "facts_note": ("Same farm as layers 1-3 (f-001): goat 14, buffalo 16 (Mehsana 5, Nili-Ravi 5), sheep 7, "
                       "chicken 7, cow 9 (Kankrej 3), total 53. GAURI and MOTI = Sirohi goats, KAALI = Jamunapari "
                       "goat, LAKSHMI = Murrah buffalo, BIJLI = Nili-Ravi buffalo, RAJA = Kankrej cow, CHINNI "
                       "exists. BHOORI does NOT exist. Dates use placeholders counted from now in IST "
                       "(see evals/run.py)."),
        "conversations": convs,
    }


if __name__ == "__main__":
    OUT.write_text(json.dumps(build(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(build()['conversations'])} conversations)")
