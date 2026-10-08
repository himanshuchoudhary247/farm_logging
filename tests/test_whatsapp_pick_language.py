"""_pick_language must never raise on a script detect_language returns --
a bare dict index here (missing "mr"/"ml") previously raised KeyError on
any Marathi/Malayalam-script WhatsApp message, silently dropping the
reply (found in deep-review of PR #39)."""
from types import SimpleNamespace

from services.whatsapp_channel.router import _pick_language

_CFG = SimpleNamespace(default_language="en-IN")


def test_marathi_script_detects_as_hindi_not_a_crash():
    """detect_language can't distinguish Marathi from Hindi (both
    Devanagari) -- this stays "hi-IN", a separate known limitation
    (mitigated in services/common/reply_words.py's word matching, not
    here). The fix in this file is specifically that it degrades to a
    tag instead of raising, for any script detect_language does return."""
    assert _pick_language("माहीत नाही", _CFG) == "hi-IN"


def test_malayalam_script_gets_malayalam_tag():
    assert _pick_language("അറിയില്ല", _CFG) == "ml-IN"


def test_known_scripts_still_resolve_correctly():
    assert _pick_language("ಗೊತ್ತಿಲ್ಲ", _CFG) == "kn-IN"
    assert _pick_language("தெரியாது", _CFG) == "ta-IN"
    assert _pick_language("తెలియదు", _CFG) == "te-IN"


def test_english_and_script_neutral_text_unaffected():
    assert _pick_language("hello", _CFG) == "en-IN"
    assert _pick_language("411001", _CFG) == _CFG.default_language
