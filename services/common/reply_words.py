"""Whole-reply fallback words, per language, in one place.

The extraction LLM is always the primary signal. These words are only a
fallback for when the LLM returns nothing, e.g. "తెలియదు" at the breed
question was seen live coming back with no field_unknown. Matching is on
the WHOLE reply (ignoring case, spaces and a final . ! ? ।), never a
substring, so a word inside a longer answer is left to the LLM (PR #36
review: "ताप आहे, औषध नको" must not cancel a booking).

To support a new language, add its words here; no new code needed.
"""
from typing import Dict, FrozenSet, Optional

# kind -> language -> words
_WORDS: Dict[str, Dict[str, FrozenSet[str]]] = {
    # "I don't know" as a reply to the field being asked (registration: breed).
    "dont_know": {
        "en": frozenset({
            "not sure", "i'm not sure", "im not sure", "no idea",
            "don't know", "dont know", "i don't know", "i dont know", "unknown",
        }),
        "hi": frozenset({
            "पता नहीं", "मुझे पता नहीं", "पता नहीं है", "नहीं पता",
            "मालूम नहीं", "नस्ल पता नहीं",
        }),
        "mr": frozenset({
            "माहीत नाही", "माहित नाही",
            "मला माहीत नाही", "मला माहित नाही",
            "माहीत नाही मला", "माहित नाही मला",
            "नक्की माहीत नाही", "नक्की माहित नाही",
            "जात माहीत नाही", "जात माहित नाही",
        }),
        "ta": frozenset({
            "தெரியாது", "எனக்கு தெரியாது", "தெரியவில்லை", "இனவகை தெரியாது",
        }),
        "te": frozenset({
            "తెలియదు", "నాకు తెలియదు", "తెలీదు", "బ్రీడ్ తెలియదు", "జాతి తెలియదు",
        }),
        "kn": frozenset({
            "ಗೊತ್ತಿಲ್ಲ", "ನನಗೆ ಗೊತ್ತಿಲ್ಲ", "ತಳಿ ಗೊತ್ತಿಲ್ಲ",
        }),
        "ml": frozenset({
            "അറിയില്ല", "എനിക്ക് അറിയില്ല", "ഇനം അറിയില്ല", "നിശ്ചയമില്ല",
        }),
    },
    # Declining more optional details (registration: optional step).
    "skip": {
        "mr": frozenset({
            "नाही", "नको", "नाही झाला आता", "काही नाही", "नाही काही नाही", "पुढे जा",
        }),
    },
    # Confirmation replies. "cancel" is honoured in every state, so it
    # holds only explicit cancel words; "नको" alone means "no".
    "cancel": {
        "mr": frozenset({"रद्द करा", "कॅन्सल"}),
    },
    "yes": {
        "mr": frozenset({"हो", "बरोबर", "हो बरोबर", "ठीक आहे", "सबमिट", "बुक करा", "सेव्ह करा"}),
    },
    "no": {
        "mr": frozenset({"नाही", "नको", "चूक", "नाही नको", "बदल करा"}),
    },
}


def _norm(text: str) -> str:
    return " ".join((text or "").strip().lower().rstrip(".!?।").split())


def _lang(language: str) -> str:
    return (language or "en-IN").split("-")[0].lower()


# Script detection can't tell these apart (both Devanagari) -- a message
# tagged "hi" may actually be from a Marathi speaker (e.g. on WhatsApp,
# where language comes from script detection, not an app selector). Safe
# to union: the word sets are disjoint and matching stays whole-reply
# exact, so this only adds matches, never widens a substring risk.
_SCRIPT_SIBLINGS: Dict[str, "tuple[str, ...]"] = {"hi": ("mr",)}


def matches(kind: str, text: str, language: str) -> bool:
    """True only when the WHOLE reply is one of `kind`'s words for this
    language, or for a script-sibling language detection can't rule out."""
    lang = _lang(language)
    words = _WORDS.get(kind, {}).get(lang, frozenset())
    for sibling in _SCRIPT_SIBLINGS.get(lang, ()):
        words |= _WORDS.get(kind, {}).get(sibling, frozenset())
    return _norm(text) in words


def is_dont_know(text: str, language: str) -> bool:
    return matches("dont_know", text, language)


def is_skip(text: str, language: str) -> bool:
    return matches("skip", text, language)


def confirmation_signal(text: str, language: str) -> Optional[str]:
    """'cancel' / 'yes' / 'no' when the whole reply is one of those words, else None."""
    for signal in ("cancel", "yes", "no"):
        if matches(signal, text, language):
            return signal
    return None
