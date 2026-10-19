"""Matching a farmer's word, in any Indian script or Latin, to the animal
names stored for that farmer (services/common/name_match.py)."""
import pytest

from services.common.name_match import find_name_mentions, romanize, sound_key

NAMES = ["GAURI", "MOTI", "LAKSHMI", "RAJA", "BIJLI", "KAALI", "CHINNI",
         "SHERU", "BHOLA", "SUNDARI", "TAG-001-1"]


@pytest.mark.parametrize("word, name", [
    ("गोरी", "GAURI"), ("गौरी", "GAURI"),              # Hindi / Marathi
    ("గోరి", "GAURI"), ("గౌరి", "GAURI"),              # Telugu
    ("ಗೋರಿ", "GAURI"), ("ಮೋತಿ", "MOTI"),               # Kannada
    ("கௌரி", "GAURI"), ("கோரி", "GAURI"),              # Tamil (one letter for g/k)
    ("ഗോരി", "GAURI"), ("മോതി", "MOTI"),               # Malayalam
    ("gowri", "GAURI"), ("Gori", "GAURI"),             # Latin, other spellings
    ("लक्ष्मी", "LAKSHMI"), ("లక్ష్మి", "LAKSHMI"),
    ("राजा", "RAJA"), ("ಕಾಳಿ", "KAALI"), ("चिन्नी", "CHINNI"),
    ("शेरू", "SHERU"), ("भोला", "BHOLA"), ("సుందరి", "SUNDARI"),
    ("బిజిలి", "BIJLI"),                               # one extra vowel
    ("గౌరికి", "GAURI"), ("ಗೌರಿಗೆ", "GAURI"), ("கௌரிக்கு", "GAURI"),  # case endings
])
def test_names_in_any_script_and_spelling_match(word, name):
    assert [m.name for m in find_name_mentions(word, NAMES)] == [name]


@pytest.mark.parametrize("text", [
    "मेरी बकरियां कितनी हैं", "how many goats do I have", "నా గొర్రెలు ఎన్ని",
    "ಎಷ್ಟು ಕುರಿಗಳು ಇವೆ", "what is the weather today", "कल डॉक्टर चाहिए",
    "काल", "कोरी", "मोटा", "gaali", "goru", "more", "rani", "moto",
    "గొర్రె", "గోరు", "బుధవారం", "ಗುರುವಾರ", "सोमवार", "పసు", "ஆடு", "എരുമ",
    "बुखार है", "ताप आहे", "doctor", "tomorrow morning", "bijli ka bill",
])
def test_everyday_words_do_not_match_names(text):
    assert find_name_mentions(text, NAMES) == []


def test_name_inside_a_sentence_and_one_note_per_name():
    found = find_name_mentions("గోరి బ్రీడ్ ఏమిటి? గౌరి కి జ్వరం", NAMES)
    assert [m.name for m in found] == ["GAURI"]


def test_name_typed_exactly_needs_no_note():
    assert find_name_mentions("GAURI ki breed kya hai", NAMES) == []
    assert find_name_mentions("gauri ki breed", NAMES) == []


def test_tags_with_digits_are_left_to_the_model():
    assert find_name_mentions("tag 001 ka bukhar", ["TAG-001-1"]) == []


def test_empty_inputs():
    assert find_name_mentions("", NAMES) == []
    assert find_name_mentions("गोरी", []) == []
    assert find_name_mentions("गोरी", ["", None]) == []


def test_romanize_and_key():
    assert romanize("गौरी") == "gaurii"
    assert romanize("లక్ష్మి") == "lakshmi"
    assert romanize("abc 12") == "abc 12"
    assert sound_key("GAURI") == sound_key("गोरी") == sound_key("gowri")
    assert sound_key("கௌரி", fold_voicing=True) == sound_key("GAURI", fold_voicing=True)
    