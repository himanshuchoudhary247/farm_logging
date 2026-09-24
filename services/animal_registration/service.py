"""Conversational "Add Animal" registration -- mirrors flokiquser's real
Add Animal form (src/pages/farm-management/add-animal/add-animal.tsx) via
chat/voice instead of the app's own form UI.

LOCAL-ONLY BY DESIGN (user's explicit decision, see
/Users/sudhanshu/.claude/plans/elegant-roaming-river.md): unlike
appointments/health-logs (which are legitimately local-first since they're
byproducts of this chat feature), an animal registered here does NOT sync
to the real flokiq backend -- flokiq_sync has no create_animal() and the
auth question for a real write is unresolved with no timeline. The animal
exists in farmer_chat's own local demo store (visible to query_agent,
appointment_supervisor's animal-matching, etc.) but not the farmer's real
flokiq account. This is a deliberate, reviewed tradeoff, not an oversight.

Architecture: reuses appointment_supervisor's proven multi-turn
state-machine pattern (file-backed draft store, sha1-hashed farmer+session
path, per-session RLock across the whole call) rather than a dedicated
single-turn ADK Agent -- 15 fields is clearly a multi-turn task. Uses its
OWN dedicated Converse tool-use call (_ANIMAL_REGISTRATION_TOOL_SPEC)
rather than extending the shared, hot-path _EXTRACTION_TOOL_SPEC in
bedrock_adapter.py -- that schema is used on every voice turn across the
whole app and was tuned via a real eval; bloating it with 9+
registration-specific fields risks regressing everything else for a
comparatively rare feature. Same pattern as appointment_supervisor's own
_resolve_animal_id/_ANIMAL_MATCH_TOOL_SPEC, which is exactly this kind of
isolated, dedicated tool call.

No per-turn cumulative readback (explicit user direction, given after this
session found and fixed the identical bug live in appointment_supervisor,
commit d4fddb9): each turn states only what's still needed, optionally
acknowledging just what changed this turn -- never a running list of
everything already given. The full field-by-field summary appears exactly
once, at the final confirm-before-submit step.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
from base64 import b64encode
from pathlib import Path
from typing import Any, Optional

from filelock import FileLock

from services.llm_service.bedrock_adapter import BedrockTextAdapter, TaskTier
from services.voice_agent.session_store import clear_session
from services.voice_agent.tts import synthesize_speech
from storage import animals_for_farmer, append_animal, atomic_write_json, get_data_dir

_log = logging.getLogger("animal_registration")
if not _log.handlers:
    _log.addHandler(logging.StreamHandler())
    _log.setLevel(logging.INFO)

SUPPORTED_LANGUAGES = {"en-IN": "English", "hi-IN": "Hindi", "ta-IN": "Tamil", "te-IN": "Telugu", "kn-IN": "Kannada"}
_UNSET = object()

# Required, in collection order. status defaults to "active" and is
# deliberately never asked for a brand-new animal unless the farmer states
# otherwise -- see REQUIRED_FIELDS below vs _ASK_ORDER.
REQUIRED_FIELDS = ("unique_animal_id", "species", "breed", "sex")
OPTIONAL_FIELDS = (
    "birth_date", "sire_id", "dam_id", "initial_weight_kg", "current_location",
    "official_tag_type", "official_tag_number", "acquisition_date", "acquisition_source",
)

# Copied verbatim from flokiquser's add-animal.tsx breed dropdown options
# (per-species) -- source of truth is the real form, not re-derived.
_GOAT_BREEDS = [
    "Jamunapari", "Beetal", "Barbari", "Jakhrana", "Sirohi", "Marwari", "Zalawadi",
    "Gohilwadi", "Surti", "Kutchi", "Black Bengal", "Assam Hill", "Ganjam", "Ghumusari",
    "Bundelkhandi", "Kannada", "Osmanabadi", "Sangamneri", "Konkan Kanyal", "Malabari",
    "Attappady Black", "Hylo", "Kanni", "Totapari", "Changthangi", "Chegu", "Gaddi",
    "North-Western Plains Local", "Indo-Gangetic Plains Local", "Central Plateau Local",
    "Eastern Plateau and Coastal Local", "North-Eastern Hill Local",
    "Southern Peninsular Local", "Western Coastal Local", "High Altitude Temperate Local",
]
_SHEEP_BREEDS = [
    "Kashmir Merino", "Gaddi", "Rampur Bushair", "Chokla", "Magra", "Nali", "Marwari",
    "Jaisalmeri", "Sonadi", "Malpura", "Patanwadi", "Muzaffarnagari", "Chottanagpuri",
    "Garole", "Bonpala", "Deccani", "Nellore", "Bellary", "Mandya", "Mecheri",
    "Madras Red", "Ramnad White", "Kilakarsal", "Vembur", "Kenguri", "Tiruchy Black",
    "North-Western Desert Local", "Indo-Gangetic Plains Local", "Central Plateau Local",
    "Eastern Plateau and Hills Local", "Southern Peninsular Local",
    "Himalayan Temperate Local",
]
_BREEDS_BY_SPECIES = {"goat": _GOAT_BREEDS, "sheep": _SHEEP_BREEDS}
_VALID_SEX = {"male", "female"}
_VALID_SPECIES = {"goat", "sheep"}
_VALID_STATUS = {"active", "sold", "deceased", "culled", "pregnant", "sick"}
_VALID_TAG_TYPE = {"visual", "rfid", "tattoo"}
_BREED_UNSPECIFIED = "Not specified (local/mixed breed)"

_ANIMAL_REGISTRATION_TOOL_SPEC = {
    "name": "record_animal_registration",
    "description": (
        "Record whatever information about a NEW animal being registered the "
        "farmer just stated in this turn. Populate ONLY fields the farmer "
        "actually mentioned this turn -- never invent a value, never repeat "
        "a value from an earlier turn (the caller already remembers it). "
        "Call this tool exactly once EVERY turn, even if the farmer's message "
        "contains no new field value at all (e.g. 'I want to add an animal', "
        "'okay', a question, or anything else that states nothing new) -- in "
        "that case call it with every property empty/omitted. Never respond "
        "with plain text instead of calling this tool."
    ),
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "unique_animal_id": {
                    "type": "string",
                    "description": "The farmer's own chosen ID/tag/name for this animal, exactly as they said it. Never invent one.",
                },
                # Native-script words copied from the shared _EXTRACTION_TOOL_SPEC
                # in bedrock_adapter.py. All earlier testing was English-only, so a
                # Hindi/Tamil/Telugu/Kannada species word had no anchor here.
                "species": {
                    "type": "string",
                    "enum": ["goat", "sheep"],
                    "description": (
                        "Only set this when the farmer's words name the animal type. Native-"
                        "script vocabulary, so a bare single word in any of these languages "
                        "still maps correctly: "
                        "goat: बकरी (hi), మేక (te), ஆடு (ta), ಆಡು (kn), ആട് (ml). "
                        "sheep: भेड़ (hi), గొర్రె (te), செம்மறியாடு (ta), ಕುರಿ (kn), "
                        "ചെമ്മരിയാട് (ml). "
                        "Careful: the Tamil and Malayalam words for sheep END with the word "
                        "for goat (செம்மறியாடு contains ஆடு, ചെമ്മരിയാട് contains ആട്). The "
                        "full word means sheep, not goat. Do NOT guess a species when no "
                        "animal word is present at all."
                    ),
                },
                "breed": {
                    "type": "string",
                    "description": "The breed name as the farmer said it, even if it's not an exact match to a standard breed name -- never guess a breed the farmer didn't say.",
                },
                "sex": {"type": "string", "enum": ["male", "female"]},
                "status": {"type": "string", "enum": sorted(_VALID_STATUS)},
                "birth_date": {
                    "type": "string",
                    "description": "'today'/'tomorrow'/'yesterday' or ISO YYYY-MM-DD. Only set when the farmer's words clearly express a complete date -- never guess a day-of-month or default to today from a bare number.",
                },
                "sire_id": {"type": "string", "description": "The father animal's ID/tag, if stated."},
                "dam_id": {"type": "string", "description": "The mother animal's ID/tag, if stated."},
                "initial_weight_kg": {"type": "string", "description": "Weight in kilograms as a plain number string, e.g. '25'."},
                "current_location": {"type": "string"},
                "official_tag_type": {"type": "string", "enum": sorted(_VALID_TAG_TYPE)},
                "official_tag_number": {"type": "string"},
                "acquisition_date": {
                    "type": "string",
                    "description": "Same rules as birth_date -- only a clearly complete date.",
                },
                "acquisition_source": {"type": "string"},
                "wants_to_skip_optional": {
                    "type": "boolean",
                    "description": "true ONLY when the farmer is explicitly declining to add more optional details (e.g. 'no', 'that's all', 'skip', 'just submit') -- never true just because they answered one question.",
                },
                "field_unknown": {
                    "type": "boolean",
                    "description": "true ONLY when the farmer explicitly says they don't know or aren't sure about the field currently being asked (e.g. 'no idea', 'not sure', 'I don't know', 'skip it' as a direct reply to a question) -- never true just because the message doesn't obviously answer anything.",
                },
                "corrects_identity": {
                    "type": "boolean",
                    "description": "true ONLY when the farmer is explicitly correcting the animal ID, species, breed, or sex that was already captured earlier (e.g. 'actually the ID is...', 'no wait, change it to...', 'I meant a sheep, not a goat'). false for a plain new statement -- this only matters once those fields are already set.",
                },
                "confirmation_signal": {
                    "type": "string",
                    "enum": ["yes", "no", "cancel", "none"],
                    "description": (
                        "Classify the farmer's turn by actual meaning: 'yes' affirms/confirms, "
                        "'no' rejects/corrects, 'cancel' abandons the registration, 'none' if "
                        "this turn is neither (e.g. just stating a field value). "
                        "Classify by meaning, NOT by keyword matching (same rule as the shared "
                        "_EXTRACTION_TOOL_SPEC): 'there's no problem, go ahead' means 'yes' even "
                        "though it contains the word 'no'; 'enough already, just save it' is not "
                        "'no' just because a word contains those letters; 'that's wrong, change "
                        "it' means 'no' even with no literal word for it. A farmer asking an "
                        "unrelated QUESTION is not a rejection, use 'none' for that."
                    ),
                },
            },
        }
    },
}

# Worked examples (few-shot), same approach as the shared _TOOL_SYSTEM_PROMPT in
# bedrock_adapter.py. The breed-loop bugs happened because this prompt was
# prose-only and the model quietly didn't follow it; each example below maps
# to a bug found live or to a known risk (native-language words, yes/no by meaning).
_REGISTRATION_SYSTEM = """You are helping register a new animal for a farmer, one field at a time.

You will be told which field is currently being asked about (if any) and what has already been captured. Extract whatever the farmer's message actually states -- their reply may answer the pending field, correct an earlier field, or state several fields at once. Never invent a value for a field the farmer didn't mention. Never repeat back a value the farmer stated in an EARLIER turn as if it were new.

Examples (what goes into the record_animal_registration call):
1) PHASE: collecting, just asked for 'unique_animal_id' | Farmer: "12" -> {unique_animal_id: '12'} -- a bare number answers the pending field, never initial_weight_kg.
2) Nothing captured yet | Farmer: "ID 1122, goat, male" -> {unique_animal_id: '1122', species: 'goat', sex: 'male'} -- every field stated in one turn is extracted.
3) PHASE: collecting, just asked for 'species' | Farmer: "बकरी है" -> {species: 'goat'}
4) PHASE: collecting, just asked for 'species' | Farmer: "செம்மறியாடு" -> {species: 'sheep'} -- the full word is sheep, even though it ends with ஆடு (goat).
5) PHASE: collecting, just asked for 'breed' | Farmer: "पता नहीं" -> {field_unknown: true} -- an explicit don't-know; never invent a breed.
6) PHASE: optional fields, ID already captured | Farmer: "Bort" -> {} -- a stray word with no correction language is NOT a new unique_animal_id.
7) PHASE: optional fields, ID already captured | Farmer: "actually the ID is 1122" -> {unique_animal_id: '1122', corrects_identity: true}
8) PHASE: optional fields | Farmer: "no, that's all" -> {wants_to_skip_optional: true}
9) PHASE: confirming | Farmer: "there's no problem, go ahead" -> {confirmation_signal: 'yes'} -- classify by meaning, not by the word 'no'.
10) Any phase | Farmer: "rehne do, cancel karo" -> {confirmation_signal: 'cancel'}"""


_LABELS = {
    "en": {
        "unique_animal_id": "animal ID", "species": "species", "breed": "breed", "sex": "sex",
        "status": "status", "birth_date": "date of birth", "sire_id": "sire ID", "dam_id": "dam ID",
        "initial_weight_kg": "weight (kg)", "current_location": "current location",
        "official_tag_type": "tag type", "official_tag_number": "tag number",
        "acquisition_date": "acquisition date", "acquisition_source": "acquisition source",
    },
    "hi": {
        "unique_animal_id": "पशु आईडी", "species": "प्रजाति", "breed": "नस्ल", "sex": "लिंग",
        "status": "स्थिति", "birth_date": "जन्म तिथि", "sire_id": "पिता की आईडी", "dam_id": "माता की आईडी",
        "initial_weight_kg": "वजन (किग्रा)", "current_location": "वर्तमान स्थान",
        "official_tag_type": "टैग प्रकार", "official_tag_number": "टैग नंबर",
        "acquisition_date": "प्राप्ति तिथि", "acquisition_source": "प्राप्ति स्रोत",
    },
    "ta": {
        "unique_animal_id": "விலங்கு ஐடி", "species": "இனம்", "breed": "இனவகை", "sex": "பாலினம்",
        "status": "நிலை", "birth_date": "பிறந்த தேதி", "sire_id": "தந்தை ஐடி", "dam_id": "தாய் ஐடி",
        "initial_weight_kg": "எடை (கிலோ)", "current_location": "தற்போதைய இடம்",
        "official_tag_type": "டேக் வகை", "official_tag_number": "டேக் எண்",
        "acquisition_date": "பெற்ற தேதி", "acquisition_source": "பெற்ற மூலம்",
    },
    "te": {
        "unique_animal_id": "జంతువు ఐడి", "species": "జాతి", "breed": "బ్రీడ్", "sex": "లింగం",
        "status": "స్థితి", "birth_date": "పుట్టిన తేదీ", "sire_id": "తండ్రి ఐడి", "dam_id": "తల్లి ఐడి",
        "initial_weight_kg": "బరువు (కిలో)", "current_location": "ప్రస్తుత స్థానం",
        "official_tag_type": "ట్యాగ్ రకం", "official_tag_number": "ట్యాగ్ నంబర్",
        "acquisition_date": "సేకరణ తేదీ", "acquisition_source": "సేకరణ మూలం",
    },
    "kn": {
        "unique_animal_id": "ಪ್ರಾಣಿ ಐಡಿ", "species": "ಪ್ರಭೇದ", "breed": "ತಳಿ", "sex": "ಲಿಂಗ",
        "status": "ಸ್ಥಿತಿ", "birth_date": "ಜನನ ದಿನಾಂಕ", "sire_id": "ತಂದೆ ಐಡಿ", "dam_id": "ತಾಯಿ ಐಡಿ",
        "initial_weight_kg": "ತೂಕ (ಕೆಜಿ)", "current_location": "ಪ್ರಸ್ತುತ ಸ್ಥಳ",
        "official_tag_type": "ಟ್ಯಾಗ್ ಪ್ರಕಾರ", "official_tag_number": "ಟ್ಯಾಗ್ ಸಂಖ್ಯೆ",
        "acquisition_date": "ಸ್ವಾಧೀನ ದಿನಾಂಕ", "acquisition_source": "ಸ್ವಾಧೀನ ಮೂಲ",
    },
}

_TEXT = {
    "en": {
        "welcome": "Let's register a new animal. Please tell me the animal ID, species (goat or sheep), breed, and sex.",
        "ask_field": "Please provide the {field}.",
        "ask_breed": "Please provide the breed. If you're not sure, just say 'not sure'.",
        "ask_optional": "The required details are saved. Would you like to add any optional details (date of birth, weight, location, parent IDs, tag info, acquisition details)? Say what you'd like to add, or say 'no' to submit now.",
        "got_it": "Got it: {delta}.",
        "ask_more": "Anything else to add, or say 'no' to submit?",
        "breed_species_mismatch": "'{breed}' isn't a recognized {species} breed. Please give the breed again, or say 'not sure' if you don't know it.",
        "duplicate_id": "An animal with ID '{identifier}' is already registered to you. Please give a different ID.",
        "correct": "Here's everything for this new animal: {summary}. Shall I save this?",
        "no": "What would you like to correct?",
        "cancelled": "Registration cancelled, nothing was saved.",
        "submitted": "{identifier} has been registered successfully.",
    },
    "hi": {
        "welcome": "एक नया पशु दर्ज करते हैं। कृपया पशु आईडी, प्रजाति (बकरी या भेड़), नस्ल और लिंग बताएं।",
        "ask_field": "कृपया {field} बताएं।",
        "ask_breed": "कृपया नस्ल बताएं। अगर पता नहीं है, तो 'पता नहीं' कहें।",
        "ask_optional": "आवश्यक जानकारी सेव हो गई है। क्या आप कोई वैकल्पिक जानकारी जोड़ना चाहते हैं (जन्म तिथि, वजन, स्थान, माता-पिता की आईडी, टैग जानकारी)? बताएं क्या जोड़ना है, या अभी सबमिट करने के लिए 'नहीं' कहें।",
        "got_it": "समझ गया: {delta}।",
        "ask_more": "और कुछ जोड़ना है, या सबमिट करने के लिए 'नहीं' कहें?",
        "breed_species_mismatch": "'{breed}' एक मान्य {species} नस्ल नहीं है। कृपया नस्ल फिर से बताएं, या अगर पता नहीं है तो 'पता नहीं' कहें।",
        "duplicate_id": "आईडी '{identifier}' वाला पशु पहले से पंजीकृत है। कृपया अलग आईडी बताएं।",
        "correct": "इस नए पशु का पूरा विवरण: {summary}। क्या मैं इसे सेव करूं?",
        "no": "आप क्या सुधारना चाहते हैं?",
        "cancelled": "पंजीकरण रद्द कर दिया गया, कुछ भी सेव नहीं हुआ।",
        "submitted": "{identifier} सफलतापूर्वक पंजीकृत हो गया है।",
    },
    "ta": {
        "welcome": "ஒரு புதிய விலங்கை பதிவு செய்வோம். விலங்கு ஐடி, இனம் (ஆடு அல்லது செம்மறியாடு), இனவகை மற்றும் பாலினம் தெரிவிக்கவும்.",
        "ask_field": "தயவுசெய்து {field} தெரிவிக்கவும்.",
        "ask_breed": "தயவுசெய்து இனவகை தெரிவிக்கவும். தெரியாவிட்டால் 'தெரியாது' என்று சொல்லுங்கள்.",
        "ask_optional": "தேவையான விவரங்கள் சேமிக்கப்பட்டன. விருப்ப விவரங்கள் (பிறந்த தேதி, எடை, இடம், பெற்றோர் ஐடி, டேக் தகவல்) சேர்க்க விரும்புகிறீர்களா? சேர்க்க வேண்டியதைச் சொல்லுங்கள், அல்லது இப்போது சமர்ப்பிக்க 'இல்லை' என்று சொல்லுங்கள்.",
        "got_it": "சரி: {delta}.",
        "ask_more": "இன்னும் ஏதாவது சேர்க்க வேண்டுமா, அல்லது சமர்ப்பிக்க 'இல்லை' என்று சொல்லுங்கள்?",
        "breed_species_mismatch": "'{breed}' என்பது சரியான {species} இனவகை அல்ல. தயவுசெய்து மீண்டும் தெரிவிக்கவும், அல்லது தெரியாவிட்டால் 'தெரியாது' என்று சொல்லுங்கள்.",
        "duplicate_id": "'{identifier}' ஐடி கொண்ட விலங்கு ஏற்கனவே பதிவு செய்யப்பட்டுள்ளது. வேறு ஐடி தெரிவிக்கவும்.",
        "correct": "இந்த புதிய விலங்கின் முழு விவரம்: {summary}. இதை சேமிக்கவா?",
        "no": "எதை திருத்த வேண்டும்?",
        "cancelled": "பதிவு ரத்து செய்யப்பட்டது, எதுவும் சேமிக்கப்படவில்லை.",
        "submitted": "{identifier} வெற்றிகரமாக பதிவு செய்யப்பட்டது.",
    },
    "te": {
        "welcome": "కొత్త జంతువును నమోదు చేద్దాం. దయచేసి జంతువు ఐడి, జాతి (మేక లేదా గొర్రె), బ్రీడ్ మరియు లింగం చెప్పండి.",
        "ask_field": "దయచేసి {field} చెప్పండి.",
        "ask_breed": "దయచేసి బ్రీడ్ చెప్పండి. తెలియకపోతే 'తెలియదు' అని చెప్పండి.",
        "ask_optional": "అవసరమైన వివరాలు సేవ్ అయ్యాయి. ఐచ్ఛిక వివరాలు (పుట్టిన తేదీ, బరువు, స్థానం, తల్లిదండ్రుల ఐడి, ట్యాగ్ సమాచారం) జోడించాలనుకుంటున్నారా? ఏమి జోడించాలో చెప్పండి, లేదా ఇప్పుడే సమర్పించడానికి 'లేదు' అని చెప్పండి.",
        "got_it": "అర్థమైంది: {delta}.",
        "ask_more": "ఇంకేమైనా జోడించాలా, లేదా సమర్పించడానికి 'లేదు' అని చెప్పండి?",
        "breed_species_mismatch": "'{breed}' చెల్లుబాటు అయ్యే {species} బ్రీడ్ కాదు. దయచేసి మళ్ళీ చెప్పండి, లేదా తెలియకపోతే 'తెలియదు' అని చెప్పండి.",
        "duplicate_id": "'{identifier}' ఐడితో జంతువు ఇప్పటికే నమోదు చేయబడింది. దయచేసి వేరే ఐడి చెప్పండి.",
        "correct": "ఈ కొత్త జంతువు యొక్క పూర్తి వివరాలు: {summary}. దీన్ని సేవ్ చేయనా?",
        "no": "మీరు దేన్ని సరిచేయాలనుకుంటున్నారు?",
        "cancelled": "నమోదు రద్దు చేయబడింది, ఏమీ సేవ్ కాలేదు.",
        "submitted": "{identifier} విజయవంతంగా నమోదు చేయబడింది.",
    },
    "kn": {
        "welcome": "ಹೊಸ ಪ್ರಾಣಿಯನ್ನು ನೋಂದಾಯಿಸೋಣ. ದಯವಿಟ್ಟು ಪ್ರಾಣಿ ಐಡಿ, ಪ್ರಭೇದ (ಮೇಕೆ ಅಥವಾ ಕುರಿ), ತಳಿ ಮತ್ತು ಲಿಂಗವನ್ನು ತಿಳಿಸಿ.",
        "ask_field": "ದಯವಿಟ್ಟು {field} ತಿಳಿಸಿ.",
        "ask_breed": "ದಯವಿಟ್ಟು ತಳಿ ತಿಳಿಸಿ. ಗೊತ್ತಿಲ್ಲದಿದ್ದರೆ 'ಗೊತ್ತಿಲ್ಲ' ಎಂದು ಹೇಳಿ.",
        "ask_optional": "ಅಗತ್ಯ ವಿವರಗಳು ಉಳಿಸಲಾಗಿದೆ. ಐಚ್ಛಿಕ ವಿವರಗಳನ್ನು (ಜನನ ದಿನಾಂಕ, ತೂಕ, ಸ್ಥಳ, ಪೋಷಕರ ಐಡಿ, ಟ್ಯಾಗ್ ಮಾಹಿತಿ) ಸೇರಿಸಲು ಬಯಸುವಿರಾ? ಏನು ಸೇರಿಸಬೇಕೆಂದು ಹೇಳಿ, ಅಥವಾ ಈಗಲೇ ಸಲ್ಲಿಸಲು 'ಇಲ್ಲ' ಎಂದು ಹೇಳಿ.",
        "got_it": "ಅರ್ಥವಾಯಿತು: {delta}.",
        "ask_more": "ಇನ್ನೇನಾದರೂ ಸೇರಿಸಬೇಕೇ, ಅಥವಾ ಸಲ್ಲಿಸಲು 'ಇಲ್ಲ' ಎಂದು ಹೇಳಿ?",
        "breed_species_mismatch": "'{breed}' ಮಾನ್ಯವಾದ {species} ತಳಿಯಲ್ಲ. ದಯವಿಟ್ಟು ಮತ್ತೆ ತಿಳಿಸಿ, ಅಥವಾ ಗೊತ್ತಿಲ್ಲದಿದ್ದರೆ 'ಗೊತ್ತಿಲ್ಲ' ಎಂದು ಹೇಳಿ.",
        "duplicate_id": "'{identifier}' ಐಡಿ ಹೊಂದಿರುವ ಪ್ರಾಣಿ ಈಗಾಗಲೇ ನೋಂದಾಯಿಸಲಾಗಿದೆ. ದಯವಿಟ್ಟು ಬೇರೆ ಐಡಿ ತಿಳಿಸಿ.",
        "correct": "ಈ ಹೊಸ ಪ್ರಾಣಿಯ ಸಂಪೂರ್ಣ ವಿವರ: {summary}. ಇದನ್ನು ಉಳಿಸಲೇ?",
        "no": "ನೀವು ಏನನ್ನು ಸರಿಪಡಿಸಲು ಬಯಸುವಿರಿ?",
        "cancelled": "ನೋಂದಣಿ ರದ್ದುಗೊಳಿಸಲಾಗಿದೆ, ಏನೂ ಉಳಿಸಲಾಗಿಲ್ಲ.",
        "submitted": "{identifier} ಯಶಸ್ವಿಯಾಗಿ ನೋಂದಾಯಿಸಲಾಗಿದೆ.",
    },
}


def _lang(language: str) -> str:
    return (language or "en-IN").split("-")[0].lower()


def _match_breed(breed_text: str, species: str) -> Optional[str]:
    """Deterministic validation, not an LLM call -- the model already
    extracted the farmer's free-text breed guess (_ANIMAL_REGISTRATION_TOOL_SPEC's
    breed field); this just checks it against the real per-species list
    (case-insensitive, substring-tolerant for common shortenings) rather
    than trusting an unvalidated string. Returns the canonical name or
    None if nothing in the list plausibly matches."""
    if not breed_text or species not in _BREEDS_BY_SPECIES:
        return None
    wanted = breed_text.strip().lower()
    for candidate in _BREEDS_BY_SPECIES[species]:
        c = candidate.lower()
        if wanted == c or wanted in c or c in wanted:
            return candidate
    return None


class AnimalRegistrationSupervisor:
    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or get_data_dir()
        self.intake_dir = self.data_dir / "animal_registration_intakes"
        # Same concurrency-safety design as appointment_supervisor's own
        # RLock fix this session (a real lost-update race found in code
        # review) -- applied here from day one, not as a follow-up fix.
        self._session_locks: dict[str, threading.RLock] = {}
        self._session_locks_guard = threading.Lock()

    def _session_lock(self, farmer_id: str, session_id: str) -> threading.RLock:
        digest = hashlib.sha1(f"{farmer_id}:{session_id}".encode("utf-8")).hexdigest()
        with self._session_locks_guard:
            return self._session_locks.setdefault(digest, threading.RLock())

    def _path(self, farmer_id: str, session_id: str) -> Path:
        digest = hashlib.sha1(f"{farmer_id}:{session_id}".encode("utf-8")).hexdigest()
        return self.intake_dir / f"{digest}.json"

    def _fresh(self, session_id: str, farmer_id: str, language: str) -> dict[str, Any]:
        return {
            "session_id": session_id,
            "farmer_id": farmer_id,
            "language": language if language in SUPPORTED_LANGUAGES else "en-IN",
            "state": "COLLECTING",
            "draft": {},
            "transcript_history": [],
            "submitted": False,
        }

    def _load(self, session_id: str, farmer_id: str, language: str) -> dict[str, Any]:
        path = self._path(farmer_id, session_id)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return self._fresh(session_id, farmer_id, language)

    def _save(self, draft: dict[str, Any]) -> None:
        path = self._path(draft["farmer_id"], draft["session_id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(path) + ".lock"):
            atomic_write_json(path, draft)

    def _message(self, language: str, key: str, **values: str) -> str:
        catalog = _TEXT.get(_lang(language), _TEXT["en"])
        return catalog[key].format(**values)

    def _missing_required(self, draft: dict[str, Any]) -> list[str]:
        values = draft["draft"]
        return [f for f in REQUIRED_FIELDS if not values.get(f)]

    def _summary(self, draft: dict[str, Any], only_fields: Optional[set[str]] = None) -> str:
        """only_fields restricts the readback to a subset -- used nowhere
        in this module today (unlike appointment_supervisor, there is no
        per-turn delta readback here at all; see the module docstring) but
        kept for parity/reuse if a future caller needs it. None (default)
        summarizes everything -- the ONLY place this is actually called
        with None is the final confirm-before-submit message."""
        values = draft["draft"]
        labels = _LABELS.get(_lang(draft["language"]), _LABELS["en"])
        parts = []
        for field in REQUIRED_FIELDS + OPTIONAL_FIELDS:
            if only_fields is not None and field not in only_fields:
                continue
            value = values.get(field)
            if value not in (None, "", []):
                parts.append(f"{labels.get(field, field)}: {value}")
        return "; ".join(parts) or "no details yet"

    def _response(self, draft: dict[str, Any], text: str, input_transcript: Optional[str] = None,
                  include_audio: bool = True, speech: Any = _UNSET) -> dict[str, Any]:
        language = draft["language"]
        speech_source = text if speech is _UNSET else speech
        if include_audio:
            audio, audio_error = synthesize_speech(speech_source, target_lang=_lang(language))
        else:
            audio, audio_error = None, None
        return {
            "session_id": draft["session_id"],
            "state": draft["state"],
            "language": language,
            "transcript": input_transcript,
            "draft": draft["draft"],
            "missing_fields": self._missing_required(draft),
            "response_text": text,
            "response_audio_base64": b64encode(audio).decode("ascii") if audio else None,
            "audio_error": audio_error,
        }

    def _extract(self, draft: dict[str, Any], text: str) -> dict[str, Any]:
        """Dedicated Converse tool-use call, own tool spec -- deliberately
        NOT the shared _EXTRACTION_TOOL_SPEC (see module docstring).

        Live testing (a peer session running the real UI against this
        branch, 2026-09-22) found a real bug here: the system prompt
        claims "you will be told which field is currently being asked
        about" but this method never actually said so -- so a bare reply
        like "Bort" or "12" got guessed at freely by the model instead of
        being anchored to the pending field, producing wrong-field
        extraction (a short numeric ID guessed as initial_weight_kg, then
        a breed guess silently overwriting the already-captured
        unique_animal_id on the next turn). The pending-field hint below
        is the actual fix -- not a rewrite, the missing piece."""
        pending_hint = ""
        if draft["state"] == "COLLECTING":
            missing = self._missing_required(draft)
            if missing:
                pending_hint = (
                    f"\nPHASE: collecting REQUIRED fields only. Still missing: {', '.join(missing)}. "
                    f"The farmer was just asked specifically for '{missing[0]}'. If their message is a "
                    f"plausible direct answer to that -- even a bare word, number, or short phrase with "
                    f"no field name attached -- treat it as '{missing[0]}', not as any other field. Do "
                    f"NOT populate an optional field (birth_date, sire_id, dam_id, initial_weight_kg, "
                    f"current_location, official_tag_type, official_tag_number, acquisition_date, "
                    f"acquisition_source) during this phase unless the farmer's words unmistakably name "
                    f"that field or its unit (e.g. actually says 'weight' or 'kg', or a place name for "
                    f"location) -- a bare number alone almost always answers '{missing[0]}', never weight."
                )
        elif draft["state"] == "COLLECTING_OPTIONAL":
            locked = {f: draft["draft"].get(f) for f in REQUIRED_FIELDS if draft["draft"].get(f)}
            if locked:
                locked_desc = "; ".join(f"{k}={v}" for k, v in locked.items())
                pending_hint = (
                    f"\nPHASE: optional fields. Required fields are already captured and correct "
                    f"({locked_desc}) -- do NOT change unique_animal_id, species, breed, or sex "
                    f"unless the farmer's words unmistakably say they want to correct one of those "
                    f"specific fields (e.g. 'actually the ID is...', 'wrong breed, it's...'). If so, "
                    f"also set corrects_identity to true. A bare word or number with no such "
                    f"correction language most likely answers one of the OPTIONAL fields (birth_date, "
                    f"sire_id, dam_id, initial_weight_kg, current_location, official_tag_type, "
                    f"official_tag_number, acquisition_date, acquisition_source), or nothing at all if "
                    f"it doesn't clearly fit any of those -- never re-guess it as a new ID."
                )
        elif draft["state"] == "CONFIRMING":
            # The confirmation_signal guidance only works if the model knows a
            # yes/no question was actually asked. The shared path gets this from
            # pending_questions; this module never said it, so a reply like
            # "no problem, go ahead" had nothing to anchor it to the confirm step.
            pending_hint = (
                "\nPHASE: confirming. The farmer was just shown the full summary of this "
                "new animal and asked whether to save it. Set confirmation_signal by the "
                "actual meaning of their reply (see that field's description)."
            )
        context = (
            f"Currently captured so far (do not repeat these back as new): "
            f"{self._summary(draft) if draft['draft'] else 'nothing yet'}."
            f"{pending_hint}\n"
            f"Farmer just said: \"{text}\""
        )
        try:
            adapter = BedrockTextAdapter(task=TaskTier.EXTRACTION)
            result = adapter.converse_with_tool(
                messages=[{"role": "user", "content": context}],
                tool_spec=_ANIMAL_REGISTRATION_TOOL_SPEC,
                system=_REGISTRATION_SYSTEM,
                tool_choice_name="record_animal_registration",
            )
            return result.get("tool_input") or {}
        except Exception as exc:
            _log.warning("animal registration extraction failed: %s", exc)
            return {}

    def _copy_entities(self, draft: dict[str, Any], entities: dict[str, Any]) -> tuple[dict[str, Any], Optional[str]]:
        """Applies validated entities to the draft. Returns (changed_fields,
        error_message_or_None) -- an error (e.g. breed/species mismatch)
        means nothing was written for that field and the farmer should be
        re-asked, matching this session's established pattern of turning a
        ValueError-shaped problem into a conversational re-ask rather than
        a crash."""
        target = draft["draft"]
        changed: dict[str, Any] = {}
        # A breed mismatch previously short-circuited this whole method via
        # an early `return` -- found live: on a turn stating several fields
        # at once (e.g. "12 goat aa male"), a failed breed guess silently
        # dropped every field that would otherwise have been applied after
        # it (sex, unique_animal_id, everything in the loop below). Now the
        # breed error is deferred and every other field still applies.
        breed_error: Optional[str] = None

        species = entities.get("species")
        if species and species in _VALID_SPECIES:
            if target.get("species") != species:
                changed["species"] = species
            target["species"] = species

        breed_raw = entities.get("breed")
        if breed_raw:
            effective_species = target.get("species")
            if effective_species in _BREEDS_BY_SPECIES:
                matched = _match_breed(breed_raw, effective_species)
                if matched:
                    changed["breed"] = matched
                    target["breed"] = matched
                else:
                    breed_error = self._message(
                        draft["language"], "breed_species_mismatch",
                        breed=breed_raw, species=effective_species,
                    )
            else:
                # Species not yet known -- store the raw guess, re-validate
                # once species is captured (turn() re-runs this per turn).
                changed["breed"] = breed_raw
                target["breed"] = breed_raw

        sex = entities.get("sex")
        if sex and sex in _VALID_SEX:
            if target.get("sex") != sex:
                changed["sex"] = sex
            target["sex"] = sex

        status = entities.get("status")
        if status and status in _VALID_STATUS:
            if target.get("status") != status:
                changed["status"] = status
            target["status"] = status

        tag_type = entities.get("official_tag_type")
        if tag_type and tag_type in _VALID_TAG_TYPE:
            if target.get("official_tag_type") != tag_type:
                changed["official_tag_type"] = tag_type
            target["official_tag_type"] = tag_type

        for key in ("unique_animal_id", "sire_id", "dam_id", "initial_weight_kg",
                    "current_location", "official_tag_number", "acquisition_source",
                    "birth_date", "acquisition_date"):
            value = entities.get(key)
            if value not in (None, ""):
                # Found live: once required-field collection is done, a
                # stray ambiguous word (e.g. "Bort") could get guessed as
                # a *new* unique_animal_id and silently overwrite the
                # already-correct one -- species/breed/sex are naturally
                # guarded by enum/breed-list validation, but the ID is
                # free text with none. Require an explicit correction
                # signal to touch it once it's already set and required
                # collection has moved on -- same principle as
                # appointment_supervisor's fix for its own verified
                # animal_id not being clobbered by an unrelated reply.
                if (
                    key == "unique_animal_id"
                    and target.get("unique_animal_id")
                    and draft["state"] != "COLLECTING"
                    and not entities.get("corrects_identity")
                ):
                    continue
                if target.get(key) != value:
                    changed[key] = value
                target[key] = value

        return changed, breed_error

    def turn(self, farmer_id: str, session_id: str, text: str, language: str = "en-IN",
              include_audio: bool = True) -> dict[str, Any]:
        with self._session_lock(farmer_id, session_id):
            return self._turn_locked(farmer_id, session_id, text, language, include_audio)

    def _turn_locked(self, farmer_id: str, session_id: str, text: str, language: str,
                      include_audio: bool) -> dict[str, Any]:
        draft = self._load(session_id, farmer_id, language)
        if draft.get("submitted"):
            draft = self._fresh(session_id, farmer_id, language)

        draft["transcript_history"].append(text)
        entities = self._extract(draft, text)

        if entities.get("confirmation_signal") == "cancel":
            self._save(draft)
            return self.confirm(farmer_id, session_id, "cancel", include_audio=include_audio)

        if draft["state"] == "CONFIRMING" and entities.get("confirmation_signal") in {"yes", "no"}:
            self._save(draft)
            return self.confirm(farmer_id, session_id, entities["confirmation_signal"], include_audio=include_audio)

        changed, error = self._copy_entities(draft, entities)

        # Duplicate-tag check as soon as the ID is given, not deferred to
        # submit() -- same "catch it right after they say it" principle
        # appointment_supervisor uses for animal verification. Runs even
        # when `error` (a breed mismatch) is also set this turn -- a
        # duplicate ID and a bad breed guess can land in the same turn
        # since _copy_entities no longer drops sibling fields on a breed
        # error, and the duplicate must still surface, not silently pass
        # while the farmer's attention is on the breed re-ask instead.
        if "unique_animal_id" in changed:
            wanted = str(draft["draft"]["unique_animal_id"]).strip().lower()
            existing = [a for a in animals_for_farmer(farmer_id) if a.tag_or_name.strip().lower() == wanted]
            if existing:
                draft["draft"]["unique_animal_id"] = None
                message = self._message(draft["language"], "duplicate_id", identifier=str(entities.get("unique_animal_id")))
                self._save(draft)
                return self._response(draft, message, input_transcript=text, include_audio=include_audio)

        if error:
            self._save(draft)
            return self._response(draft, error, input_transcript=text, include_audio=include_audio)

        # Breed is the one required field a farmer can legitimately not
        # know (crossbreeds/local names are common) -- an explicit "don't
        # know" while breed is the pending field accepts a fallback value
        # instead of looping forever. Found missing live: without this, a
        # farmer who genuinely doesn't know had no path forward at all.
        if (
            entities.get("field_unknown")
            and draft["state"] == "COLLECTING"
            and not draft["draft"].get("breed")
            and self._missing_required(draft)
            and self._missing_required(draft)[0] == "breed"
        ):
            draft["draft"]["breed"] = _BREED_UNSPECIFIED
            changed["breed"] = _BREED_UNSPECIFIED

        missing = self._missing_required(draft)
        if missing:
            draft["state"] = "COLLECTING"
            self._save(draft)
            field_label = _LABELS.get(_lang(draft["language"]), _LABELS["en"]).get(missing[0], missing[0])
            if missing[0] == "breed":
                message = self._message(draft["language"], "ask_breed")
            elif draft["draft"]:
                message = self._message(draft["language"], "ask_field", field=field_label)
            else:
                message = self._message(draft["language"], "welcome")
            return self._response(draft, message, input_transcript=text, include_audio=include_audio)

        if entities.get("wants_to_skip_optional") or entities.get("confirmation_signal") == "no":
            draft["state"] = "CONFIRMING"
            self._save(draft)
            message = self._message(draft["language"], "correct", summary=self._summary(draft))
            return self._response(draft, message, input_transcript=text, include_audio=include_audio, speech=message)

        # Real bug found in review: a farmer who said "no" at the confirm
        # step (state -> CORRECTING) and then gave a plain correction with
        # no explicit "no"/skip signal fell through into the branch below,
        # which unconditionally re-enters COLLECTING_OPTIONAL and asks
        # "want to add optional details?" instead of re-showing a fresh
        # confirm summary -- the farmer would have to say "no" again
        # (now meaning something else) just to get back to confirming.
        # Any correction turn from CORRECTING goes straight back to a
        # fresh CONFIRMING summary instead.
        if draft["state"] == "CORRECTING":
            draft["state"] = "CONFIRMING"
            self._save(draft)
            message = self._message(draft["language"], "correct", summary=self._summary(draft))
            return self._response(draft, message, input_transcript=text, include_audio=include_audio, speech=message)

        # Past required fields, not explicitly skipping -- either just
        # arrived here (first time) or adding more optional detail on a
        # later turn. First arrival gets the full explanation of what's
        # available; later turns get a short delta-only acknowledgment
        # instead ("Got it: weight: 25. Anything else?") -- never a
        # cumulative re-list of everything captured so far, same
        # no-repetition rule as appointment_supervisor's fix this session.
        was_already_optional = draft["state"] == "COLLECTING_OPTIONAL"
        draft["state"] = "COLLECTING_OPTIONAL"
        self._save(draft)
        if was_already_optional and changed:
            delta_summary = self._summary(draft, only_fields=set(changed.keys()))
            message = f"{self._message(draft['language'], 'got_it', delta=delta_summary)} {self._message(draft['language'], 'ask_more')}"
        else:
            message = self._message(draft["language"], "ask_optional")
        return self._response(draft, message, input_transcript=text, include_audio=include_audio)

    def confirm(self, farmer_id: str, session_id: str, response: str, include_audio: bool = True) -> dict[str, Any]:
        with self._session_lock(farmer_id, session_id):
            return self._confirm_locked(farmer_id, session_id, response, include_audio)

    def _confirm_locked(self, farmer_id: str, session_id: str, response: str, include_audio: bool) -> dict[str, Any]:
        draft = self._load(session_id, farmer_id, "en-IN")
        if draft.get("submitted"):
            raise ValueError("This animal registration has already been submitted")
        language = draft["language"]
        resp = (response or "").strip().lower()

        if resp == "cancel":
            draft["state"] = "CANCELLED"
            draft["submitted"] = True  # terminal, same guard shape as appointment_supervisor
            self._save(draft)
            clear_session(f"{farmer_id}:{session_id}")
            message = self._message(language, "cancelled")
            return self._response(draft, message, include_audio=include_audio)

        if resp in {"yes", "y", "confirm", "submit"}:
            self._save(draft)
            return self.submit(farmer_id, session_id, include_audio=include_audio)

        draft["state"] = "CORRECTING"
        self._save(draft)
        message = self._message(language, "no")
        return self._response(draft, message, include_audio=include_audio)

    def submit(self, farmer_id: str, session_id: str, include_audio: bool = True) -> dict[str, Any]:
        with self._session_lock(farmer_id, session_id):
            return self._submit_locked(farmer_id, session_id, include_audio)

    def _submit_locked(self, farmer_id: str, session_id: str, include_audio: bool) -> dict[str, Any]:
        draft = self._load(session_id, farmer_id, "en-IN")
        if draft.get("submitted"):
            return {"status": "already_submitted", "intake": draft}
        values = draft["draft"]
        missing = self._missing_required(draft)
        if missing:
            raise ValueError("Registration requires the required fields before submission")

        try:
            animal = append_animal(
                farmer_id=farmer_id,
                tag_or_name=str(values["unique_animal_id"]),
                species=values["species"],
                sex=values.get("sex", ""),
                breed=values.get("breed", ""),
                status=values.get("status", "active"),
                birth_date=values.get("birth_date"),
                sire_id=values.get("sire_id", ""),
                dam_id=values.get("dam_id", ""),
                initial_weight_kg=values.get("initial_weight_kg", ""),
                current_location=values.get("current_location", ""),
                official_tag_type=values.get("official_tag_type", ""),
                official_tag_number=values.get("official_tag_number", ""),
                acquisition_date=values.get("acquisition_date"),
                acquisition_source=values.get("acquisition_source", ""),
            )
        except ValueError as exc:
            # Duplicate slipped through (e.g. a race with another
            # registration for the same tag) -- loop back rather than crash.
            draft["draft"]["unique_animal_id"] = None
            draft["state"] = "COLLECTING"
            self._save(draft)
            message = str(exc)
            return self._response(draft, message, include_audio=include_audio)

        draft["state"] = "SUBMITTED"
        draft["submitted"] = True
        draft["animal_id"] = animal.id
        self._save(draft)
        clear_session(f"{farmer_id}:{session_id}")
        message = self._message(draft["language"], "submitted", identifier=animal.tag_or_name)
        return {
            "status": "submitted",
            "animal": animal.model_dump(),
            **self._response(draft, message, include_audio=include_audio),
        }
