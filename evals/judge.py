"""Rule-based checks for one Chocolate chat turn.

Every check is plain code (no LLM), so the same reply always gives the same
result. Each check returns {"name", "ok", "detail"}; a turn passes only when
all of its checks pass.

Supported `expect` keys (all optional):
    agent               exact agent name the reply must come from
    reply_contains_any  list of strings; at least one must appear (case-insensitive)
    reply_contains_all  list of strings; every one must appear
    reply_not_contains  list of strings; none may appear
    number              int or list of ints; that number must appear in the reply
                        (Indian-script digits like १४ / ௧௪ count as 14)
    has_number          true: the reply must contain at least one number
                        (used for weather: temperature, rain mm, wind km/h)
    script              false to skip the "reply is in the right script" check.
                        Latin words that are names or IDs (ALL CAPS), or that
                        appear in the farmer's message or in the expected words
                        (e.g. breed "Murrah"), are ignored by this check.
    max_ms              latency budget for this turn in milliseconds
"""
from __future__ import annotations

import re
import unicodedata

# Unicode blocks for the reply-language check. Marathi shares Devanagari with Hindi.
SCRIPTS = {
    "en": ("Latin", [(0x0041, 0x005A), (0x0061, 0x007A), (0x00C0, 0x024F)]),
    "hi": ("Devanagari", [(0x0900, 0x097F)]),
    "mr": ("Devanagari", [(0x0900, 0x097F)]),
    "ta": ("Tamil", [(0x0B80, 0x0BFF)]),
    "te": ("Telugu", [(0x0C00, 0x0C7F)]),
    "kn": ("Kannada", [(0x0C80, 0x0CFF)]),
    "ml": ("Malayalam", [(0x0D00, 0x0D7F)]),
}
# Share of letters that must be in the expected script. Indian-language replies
# often carry Latin names/IDs (GAURI, EVAL-...), so their bar is lower.
SCRIPT_MIN_SHARE = {"en": 0.8}
SCRIPT_MIN_SHARE_DEFAULT = 0.4

KNOWN_AGENTS = {
    "router_classifier",
    "weather_alert",
    "appointment_supervisor",
    "animal_registration",
    "query_agent",
}


def normalize_digits(text: str) -> str:
    """Turn any Unicode decimal digit (१, ௪, ౨ ...) into its ASCII form."""
    out = []
    for ch in text:
        if ch.isdigit() and not ch.isascii():
            try:
                out.append(str(unicodedata.digit(ch)))
                continue
            except (TypeError, ValueError):
                pass
        out.append(ch)
    return "".join(out)


def _norm(text: str) -> str:
    return normalize_digits(unicodedata.normalize("NFC", text or "")).casefold()


_LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z\-']*")


def strip_allowed_latin(text: str, allowed: set[str]) -> str:
    """Drop Latin words that are fine inside an Indian-language reply:
    ALL-CAPS names/IDs (GAURI, EVAL-1015-EN010) and words from `allowed`."""
    def keep(m: re.Match) -> str:
        w = m.group(0)
        if (w.isupper() and len(w) > 1) or w.casefold() in allowed:
            return " "
        return w
    return _LATIN_WORD.sub(keep, text or "")


def script_share(text: str, lang: str) -> float | None:
    """Share of letters in `text` that belong to the script of `lang` (None if no letters)."""
    base = (lang or "").split("-")[0].lower()
    if base not in SCRIPTS:
        return None
    ranges = SCRIPTS[base][1]
    letters = [ch for ch in text or "" if ch.isalpha()]
    if not letters:
        return None
    hits = sum(1 for ch in letters if any(lo <= ord(ch) <= hi for lo, hi in ranges))
    return hits / len(letters)


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "ok": bool(ok), "detail": detail}


def check_turn(expect: dict, *, agent: str | None, reply: str, ms: float | None,
               language: str, error: str | None = None, user_text: str = "") -> list[dict]:
    """Run every check that `expect` asks for and return the list of results."""
    expect = expect or {}
    if error:
        return [_check("request", False, error)]

    checks: list[dict] = []
    reply = reply or ""
    norm_reply = _norm(reply)

    if not reply.strip():
        checks.append(_check("non_empty_reply", False, "reply_text is empty"))

    if "agent" in expect:
        want = expect["agent"]
        checks.append(_check("agent", agent == want, f"want {want}, got {agent}"))

    if expect.get("reply_contains_any"):
        opts = expect["reply_contains_any"]
        hit = next((o for o in opts if _norm(o) in norm_reply), None)
        checks.append(_check("reply_contains_any", hit is not None,
                             f"found {hit!r}" if hit else f"none of {opts}"))

    for s in expect.get("reply_contains_all") or []:
        checks.append(_check("reply_contains_all", _norm(s) in norm_reply, f"needs {s!r}"))

    for s in expect.get("reply_not_contains") or []:
        checks.append(_check("reply_not_contains", _norm(s) not in norm_reply, f"must not have {s!r}"))

    if "number" in expect:
        wants = expect["number"] if isinstance(expect["number"], list) else [expect["number"]]
        found = [int(n) for n in re.findall(r"\d+", normalize_digits(reply))]
        ok = any(int(w) in found for w in wants)
        checks.append(_check("number", ok, f"want {wants}, numbers in reply {found[:10]}"))

    if expect.get("has_number"):
        nums = re.findall(r"\d+", normalize_digits(reply))
        checks.append(_check("has_number", bool(nums), f"numbers in reply {nums[:5]}"))

    if expect.get("script", True):
        allowed = {w.casefold() for w in _LATIN_WORD.findall(user_text or "")}
        for key in ("reply_contains_any", "reply_contains_all"):
            for s in expect.get(key) or []:
                allowed |= {w.casefold() for w in _LATIN_WORD.findall(s)}
        base_lang = (language or "").split("-")[0].lower()
        text_for_script = reply if base_lang == "en" else strip_allowed_latin(reply, allowed)
        share = script_share(text_for_script, language)
        if share is not None:
            base = language.split("-")[0].lower()
            need = SCRIPT_MIN_SHARE.get(base, SCRIPT_MIN_SHARE_DEFAULT)
            checks.append(_check("script", share >= need,
                                 f"{SCRIPTS[base][0]} letters {share:.0%} (need {need:.0%})"))

    if expect.get("max_ms") is not None and ms is not None:
        checks.append(_check("latency", ms <= expect["max_ms"], f"{ms:.0f} ms (max {expect['max_ms']})"))

    return checks


def turn_passed(checks: list[dict]) -> bool:
    return all(c["ok"] for c in checks)
