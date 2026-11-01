"""Match a word the farmer typed, in any Indian script or in Latin letters,
to the animal names stored for that farmer.

Names are usually stored in Latin capitals ("GAURI") but farmers type them
in their own script and spelling: गौरी, गोरी, గౌరి, ಗೋರಿ, கௌரி, "gowri". A
plain string comparison never matches these, and an LLM given the list of
names does not do it reliably either. This module does it deterministically:

1. romanize(): Devanagari, Bengali, Gurmukhi, Gujarati, Odia, Tamil,
   Telugu, Kannada and Malayalam share one Unicode layout (each script is a
   0x80 block with the same letter at the same offset), so one table turns
   any of them into rough Latin letters.
2. sound_key(): folds the spelling differences that don't change how a
   name sounds -- long/short vowels, doubled letters, aspiration (kh/k),
   au/o, ai/e, w/v -- so both sides end up in the same form. For a word in
   Tamil script it also folds voiced/voiceless pairs (g/k, d/t, b/p, j/c),
   because Tamil writes each pair with one letter; elsewhere they stay
   apart, so everyday words like "gaali" don't collapse onto "KAALI".
3. find_name_mentions(): compares each word of a message with each stored
   name by that key and returns the confident matches.

Nothing here knows any particular name or language word; it only compares
the farmer's words with the farmer's own stored names.
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Iterable, List, NamedTuple

# Brahmic scripts from Devanagari (0x0900) to Malayalam (0x0D7F).
_BRAHMIC_START, _BRAHMIC_END = 0x0900, 0x0D7F

# Offset inside a script block -> Latin. Consonants carry the inherent "a".
_CONSONANTS = {
    0x15: "k", 0x16: "kh", 0x17: "g", 0x18: "gh", 0x19: "ng",
    0x1A: "c", 0x1B: "ch", 0x1C: "j", 0x1D: "jh", 0x1E: "ny",
    0x1F: "t", 0x20: "th", 0x21: "d", 0x22: "dh", 0x23: "n",
    0x24: "t", 0x25: "th", 0x26: "d", 0x27: "dh", 0x28: "n", 0x29: "n",
    0x2A: "p", 0x2B: "ph", 0x2C: "b", 0x2D: "bh", 0x2E: "m",
    0x2F: "y", 0x30: "r", 0x31: "r", 0x32: "l", 0x33: "l", 0x34: "l",
    0x35: "v", 0x36: "sh", 0x37: "sh", 0x38: "s", 0x39: "h",
    # Devanagari nukta letters (क़ ख़ ग़ ज़ ड़ ढ़ फ़ य़)
    0x58: "k", 0x59: "kh", 0x5A: "g", 0x5B: "j", 0x5C: "r", 0x5D: "rh", 0x5E: "f", 0x5F: "y",
}
_VOWELS = {
    0x05: "a", 0x06: "aa", 0x07: "i", 0x08: "ii", 0x09: "u", 0x0A: "uu",
    0x0B: "ri", 0x0C: "li", 0x0D: "e", 0x0E: "e", 0x0F: "ee", 0x10: "ai",
    0x11: "o", 0x12: "o", 0x13: "oo", 0x14: "au", 0x60: "ri", 0x61: "li",
}
_VOWEL_SIGNS = {
    0x3E: "aa", 0x3F: "i", 0x40: "ii", 0x41: "u", 0x42: "uu", 0x43: "ri",
    0x44: "ri", 0x45: "e", 0x46: "e", 0x47: "ee", 0x48: "ai", 0x49: "o",
    0x4A: "o", 0x4B: "oo", 0x4C: "au", 0x57: "au", 0x62: "li", 0x63: "li",
}
_VIRAMA = 0x4D
_SIGNS = {0x01: "n", 0x02: "n", 0x03: "h"}  # candrabindu, anusvara, visarga
# Malayalam chillu letters: a consonant with no vowel at all.
_CHILLU = {0x0D7A: "n", 0x0D7B: "n", 0x0D7C: "r", 0x0D7D: "l", 0x0D7E: "l", 0x0D7F: "k"}


def romanize(text: str) -> str:
    """Rough Latin spelling of `text`. Indian-script letters are converted;
    Latin letters are kept; everything else (digits, punctuation, other
    scripts) passes through unchanged."""
    out: List[str] = []
    after_consonant = False  # last output ended with a consonant's inherent "a"
    for ch in unicodedata.normalize("NFC", text):
        cp = ord(ch)
        if cp in _CHILLU:
            out.append(_CHILLU[cp])
            after_consonant = False
            continue
        if not (_BRAHMIC_START <= cp <= _BRAHMIC_END):
            out.append(ch)
            after_consonant = False
            continue
        off = cp & 0x7F
        if off in _CONSONANTS:
            out.append(_CONSONANTS[off] + "a")
            after_consonant = True
        elif off in _VOWEL_SIGNS and after_consonant:
            out[-1] = out[-1][:-1] + _VOWEL_SIGNS[off]
            after_consonant = False
        elif off == _VIRAMA and after_consonant:
            out[-1] = out[-1][:-1]
            after_consonant = False
        elif off in _VOWELS:
            out.append(_VOWELS[off])
            after_consonant = False
        elif off in _SIGNS:
            out.append(_SIGNS[off])
            after_consonant = False
        # nukta, accents and other marks add no sound of their own
    return "".join(out)


_ASPIRATED = re.compile(r"([bcdgjkpstr])h")
_REPEATS = re.compile(r"(.)\1+")
_FOLD = str.maketrans({"z": "j", "q": "k", "f": "p", "w": "v"})
_FOLD_VOICING = str.maketrans({"g": "k", "d": "t", "b": "p", "j": "c"})
_TAMIL = (0x0B80, 0x0BFF)


def _is_tamil(text: str) -> bool:
    return any(_TAMIL[0] <= ord(c) <= _TAMIL[1] for c in text)


def sound_key(text: str, fold_voicing: bool = False) -> str:
    """A spelling-independent key for comparing how a name sounds.
    fold_voicing also merges g/k, d/t, b/p, j/c (for Tamil-script words)."""
    s = re.sub(r"[^a-z]", "", romanize(text).lower())
    s = _ASPIRATED.sub(r"\1", s)
    s = _REPEATS.sub(r"\1", s)
    s = s.replace("au", "o").replace("ow", "o").replace("ou", "o").replace("ai", "e")
    s = s.translate(_FOLD)
    if fold_voicing:
        s = s.translate(_FOLD_VOICING)
    s = _REPEATS.sub(r"\1", s)
    if len(s) > 3 and s.endswith("a"):
        s = s[:-1]  # a final "a" is often silent (राम = "ram") -- drop it on both sides
    return s


class NameMention(NamedTuple):
    word: str    # the word as the farmer typed it
    name: str    # the stored name it most likely refers to
    score: float


# Below this a match is not trusted: one changed sound in a longer name still
# matches, while common words stay apart from names (tests/test_name_match.py).
DEFAULT_CUTOFF = 0.82
_MIN_KEY_LEN = 3
# Keys this short ("kali", "raj") are too close to everyday words for a
# similarity score: they must match exactly (or exactly plus a case ending).
_SHORT_KEY_LEN = 4
_MAX_ENDING_LEN = 4
_WORD = re.compile(r"[^\s.,!?;:\"'()\[\]{}<>/\\|-]+")


def _usable(name: str) -> bool:
    # Tags such as "TAG-001-1" are said in many ways (digits, words); leave
    # them to the model. Only letter names are matched here.
    return not any(c.isdigit() for c in name) and len(sound_key(name)) >= _MIN_KEY_LEN


def _score(key: str, name_key: str) -> float:
    if key == name_key:
        return 1.0
    # A case ending stuck to the name ("to Gauri" written as one word in
    # Telugu, Kannada, Tamil, Malayalam).
    ends_with_case = (
        len(name_key) >= _SHORT_KEY_LEN
        and key.startswith(name_key)
        and len(key) - len(name_key) <= _MAX_ENDING_LEN
    )
    if min(len(key), len(name_key)) <= _SHORT_KEY_LEN:
        return 0.9 if ends_with_case else 0.0
    score = SequenceMatcher(None, key, name_key).ratio()
    return max(score, 0.9) if ends_with_case else score


def find_name_mentions(text: str, names: Iterable[str], cutoff: float = DEFAULT_CUTOFF) -> List[NameMention]:
    """Words of `text` that most likely refer to one of `names`, best first,
    at most one per stored name. A word already equal to a stored name
    (ignoring case) is skipped -- nothing to tell the model there."""
    usable = [n for n in dict.fromkeys(names) if n and _usable(n)]
    if not usable:
        return []
    keys = {n: (sound_key(n), sound_key(n, fold_voicing=True)) for n in usable}
    best: dict = {}
    for word in _WORD.findall(text or ""):
        if any(word.casefold() == n.casefold() for n in usable):
            continue
        tamil = _is_tamil(word)
        key = sound_key(word, fold_voicing=tamil)
        if len(key) < _MIN_KEY_LEN:
            continue
        for name in usable:
            score = _score(key, keys[name][1 if tamil else 0])
            if score >= cutoff and score > best.get(name, NameMention("", "", 0.0)).score:
                best[name] = NameMention(word, name, round(score, 3))
    return sorted(best.values(), key=lambda m: -m.score)
