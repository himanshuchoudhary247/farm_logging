"""A plain "no" must never trap a farmer inside a booking, an animal
registration or an order.

Before this, a reply like "no" or "nahi chahiye" at a question that is not a
yes/no question (the date, the tag, "what would you like to change?") changed
nothing in the draft, so the same question came back -- again and again. The
only way out was the exact word "cancel", which farmers do not know.

The rule, for every draft flow (see CancelCheckMixin.turn_with_cancel_check):

1. The flow runs the farmer's message exactly as before.
2. Only when the WHOLE reply is a "no"-type word AND that turn changed nothing
   in the draft (no field, no state, no step) does this step in. A "no" that
   means something (the confirm readback's "no" -> "what to correct?", an
   optional field skipped, a wrong animal) always changes the draft, so those
   are left exactly as they were.
   - A clear "I don't want it" ("nahi chahiye", "don't want", "rehne do",
     "वேண்டாம்", ...) cancels straight away.
   - A bare "no" ("no", "nahi", "नहीं", ...) asks once: "Do you want to
     cancel?" with two chips. "Yes" cancels; "No" shows the same question
     again; anything else goes through the flow as a normal answer.
   - A bare "no" again right after the farmer chose to carry on cancels,
     so the farmer is never asked the same thing twice in a row.
3. A plain "no" at a Yes/No question (the readback "is this correct?",
   "submit?", the order quote) also asks "Do you want to cancel?" first.
   "No, continue" then does what that "no" always did (asks what to
   correct / change), with no model call; "Yes" cancels. A "no" that
   carries a change ("no, make it tomorrow") still goes to the flow.

No model call is added: the answer to "Do you want to cancel?" is matched
here against fixed words, and that turn skips the flow's own extraction
call. Words are matched on the whole reply only (ignoring case, spaces and
a final . ! ? ।), never inside a longer sentence.
"""
from __future__ import annotations

import copy
import logging
from typing import Any, Callable, Optional

from services.common.draft_supervisor import SUPPORTED_LANGUAGES

_log = logging.getLogger("api.cancel_check")

# Marks a reply that asks "Do you want to cancel?" (see CancelCheckMixin._cancel_ask).
CANCEL_QUESTION_KEY = "cancel_question"

# Draft keys that change on every turn whatever the farmer said; left out
# when checking whether a turn changed anything.
_EVERY_TURN_KEYS = frozenset({
    "transcript_history", "confirmation_history", "updated_at", "created_at", "language", "cancel_check",
    "last_reply",
})

# States where the app shows its own Yes/No buttons; never ask on top of them.
_YES_NO_STATES = frozenset({"CONFIRMING", "READY_TO_SUBMIT"})
_DONE_STATES = frozenset({"CANCELLED", "SUBMITTED", "ORDERED"})


def _norm(text: str) -> str:
    return " ".join((text or "").strip().lower().rstrip(".!?।,").split())


def _words(*groups: tuple[str, ...]) -> frozenset[str]:
    return frozenset(_norm(w) for group in groups for w in group)


# A clear "I don't want this" -- cancels at once when the turn changed nothing.
_STOP = _words(
    ("i don't want", "i dont want", "don't want", "dont want", "i don't want it", "i dont want it",
     "not needed", "no need", "i don't need it", "i dont need it", "leave it", "forget it",
     "never mind", "nevermind", "no thanks", "no thank you", "stop", "stop it"),
    ("nahi chahiye", "nahin chahiye", "nhi chahiye", "nahi chaiye", "nhi chaiye", "nahi karna",
     "nahi karni", "nahi karna hai", "nahi karni hai", "rehne do", "rahne do", "band karo",
     "mat karo", "chhodo", "chodo", "chhod do", "chod do", "jaane do", "jane do",
     "zarurat nahi", "jarurat nahi", "zaroorat nahi"),
    ("नहीं चाहिए", "नही चाहिए", "नहीं चाहिये", "नहीं करना", "नहीं करनी", "नहीं करना है",
     "रहने दो", "बंद करो", "मत करो", "छोड़ो", "छोड़ दो", "जाने दो", "ज़रूरत नहीं", "जरूरत नहीं",
     "ज़रूरत नहीं है", "जरूरत नहीं है"),
    ("नको आहे", "मला नको", "नको मला", "राहू दे", "राहू द्या", "बंद करा", "गरज नाही", "सोडा",
     "सोडून द्या", "नको करू"),
    ("வேண்டாம்", "எனக்கு வேண்டாம்", "தேவையில்லை", "தேவை இல்லை", "விடுங்கள்", "விடு",
     "நிறுத்து", "நிறுத்துங்கள்"),
    ("వద్దు", "నాకు వద్దు", "అవసరం లేదు", "వదిలేయండి", "వదిలేయి", "ఆపండి", "ఆపు"),
    ("ಬೇಡ", "ನನಗೆ ಬೇಡ", "ಅಗತ್ಯವಿಲ್ಲ", "ಬೇಕಾಗಿಲ್ಲ", "ಬಿಡಿ", "ಬಿಟ್ಟುಬಿಡಿ", "ನಿಲ್ಲಿಸಿ"),
    ("വേണ്ട", "എനിക്ക് വേണ്ട", "ആവശ്യമില്ല", "വിട്ടേക്ക്", "വിട്ടേക്കൂ", "നിർത്തൂ", "നിർത്തുക"),
)

# A bare "no" -- could mean "stop" or "that's wrong", so the farmer is asked once.
_BARE_NO = _words(
    ("no", "nope", "nah", "no no", "not now", "n"),
    ("nahi", "nahin", "nhi", "nai", "na", "naa", "nahi nahi"),
    ("नहीं", "नही", "ना", "नहीं नहीं"),
    ("नाही", "नको", "नाही नाही", "नको नको"),
    ("இல்லை", "இல்ல", "இல்லை இல்லை"),
    ("లేదు", "కాదు", "లేదు లేదు"),
    ("ಇಲ್ಲ", "ಇಲ್ಲಾ", "ಇಲ್ಲ ಇಲ್ಲ"),
    ("ഇല്ല", "അല്ല", "ഇല്ല ഇല്ല"),
)

# Answers to "Do you want to cancel?".
_ANSWER_CANCEL = _STOP | _words(
    ("yes", "y", "yeah", "yep", "ok", "okay", "cancel", "cancel it", "yes cancel", "yes, cancel"),
    ("haan", "han", "haa", "ha", "haan ji", "ji haan", "cancel karo", "cancel kar do", "haan cancel karo"),
    ("हाँ", "हां", "हा", "जी हाँ", "जी हां", "रद्द करो", "रद्द करें", "रद्द कर दो", "कैंसल", "कैंसल करो"),
    ("हो", "होय", "हो रद्द करा", "रद्द करा", "कॅन्सल", "कॅन्सल करा"),
    ("ஆம்", "ஆமா", "ஆமாம்", "ரத்து", "ரத்து செய்", "ரத்து செய்யுங்கள்"),
    ("అవును", "ఔను", "రద్దు", "రద్దు చేయండి", "రద్దు చేయి"),
    ("ಹೌದು", "ರದ್ದು", "ರದ್ದುಗೊಳಿಸಿ", "ರದ್ದು ಮಾಡಿ"),
    ("അതെ", "ശരി", "റദ്ദാക്കുക", "റദ്ദാക്കൂ"),
)
_ANSWER_CONTINUE = _BARE_NO | _words(
    ("continue", "go on", "carry on", "no, continue", "no continue", "keep going"),
    ("jaari rakho", "jari rakho", "aage badho", "chalu rakho"),
    ("जारी रखें", "जारी रखो", "आगे बढ़ो", "चालू रखो"),
    ("पुढे चालू ठेवा", "चालू ठेवा", "पुढे", "पुढे चला"),
    ("தொடரவும்", "தொடர்", "தொடருங்கள்"),
    ("కొనసాగించండి", "కొనసాగించు"),
    ("ಮುಂದುವರಿಸಿ", "ಮುಂದುವರೆಸಿ"),
    ("തുടരുക", "തുടരൂ"),
)

# "Do you want to cancel?" per flow, and the two chips.
_ASK = {
    "booking": {
        "en": "Do you want to cancel this booking?",
        "hi": "क्या आप यह बुकिंग रद्द करना चाहते हैं?",
        "mr": "तुम्हाला हे बुकिंग रद्द करायचे आहे का?",
        "ta": "இந்த முன்பதிவை ரத்து செய்ய விரும்புகிறீர்களா?",
        "te": "ఈ బుకింగ్‌ను రద్దు చేయాలనుకుంటున్నారా?",
        "kn": "ಈ ಬುಕಿಂಗ್ ಅನ್ನು ರದ್ದುಗೊಳಿಸಬೇಕೇ?",
        "ml": "ഈ ബുക്കിംഗ് റദ്ദാക്കണോ?",
    },
    "animal": {
        "en": "Do you want to stop adding this animal?",
        "hi": "क्या आप इस पशु को जोड़ना बंद करना चाहते हैं?",
        "mr": "तुम्हाला हे जनावर जोडणे थांबवायचे आहे का?",
        "ta": "இந்த விலங்கைச் சேர்ப்பதை நிறுத்த விரும்புகிறீர்களா?",
        "te": "ఈ జంతువును జోడించడం ఆపాలనుకుంటున్నారా?",
        "kn": "ಈ ಪ್ರಾಣಿಯನ್ನು ಸೇರಿಸುವುದನ್ನು ನಿಲ್ಲಿಸಬೇಕೇ?",
        "ml": "ഈ മൃഗത്തെ ചേർക്കുന്നത് നിർത്തണോ?",
    },
    "order": {
        "en": "Do you want to cancel this order?",
        "hi": "क्या आप यह ऑर्डर रद्द करना चाहते हैं?",
        "mr": "तुम्हाला ही ऑर्डर रद्द करायची आहे का?",
        "ta": "இந்த ஆர்டரை ரத்து செய்ய விரும்புகிறீர்களா?",
        "te": "ఈ ఆర్డర్‌ను రద్దు చేయాలనుకుంటున్నారా?",
        "kn": "ಈ ಆರ್ಡರ್ ಅನ್ನು ರದ್ದುಗೊಳಿಸಬೇಕೇ?",
        "ml": "ഈ ഓർഡർ റദ്ദാക്കണോ?",
    },
}
_CHIP_CANCEL = {
    "en": "Yes, cancel", "hi": "हाँ, रद्द करें", "mr": "हो, रद्द करा", "ta": "ஆம், ரத்து செய்",
    "te": "అవును, రద్దు చేయండి", "kn": "ಹೌದು, ರದ್ದುಗೊಳಿಸಿ", "ml": "അതെ, റദ്ദാക്കുക",
}
_CHIP_CONTINUE = {
    "en": "No, continue", "hi": "नहीं, जारी रखें", "mr": "नाही, पुढे चालू ठेवा", "ta": "இல்லை, தொடரவும்",
    "te": "లేదు, కొనసాగించండి", "kn": "ಇಲ್ಲ, ಮುಂದುವರಿಸಿ", "ml": "ഇല്ല, തുടരുക",
}
_ANSWER_CANCEL = _ANSWER_CANCEL | _words(tuple(_CHIP_CANCEL.values()))
_ANSWER_CONTINUE = _ANSWER_CONTINUE | _words(tuple(_CHIP_CONTINUE.values()))


def _lang(language: str) -> str:
    lang = (language or "en-IN").split("-")[0].lower()
    return lang if lang in _CHIP_CANCEL else "en"


def is_stop(text: str) -> bool:
    return _norm(text) in _STOP


def is_bare_no(text: str) -> bool:
    return _norm(text) in _BARE_NO


def answer(text: str) -> Optional[str]:
    """'cancel' / 'continue' for a reply to "Do you want to cancel?", else None."""
    norm = _norm(text)
    if norm in _ANSWER_CANCEL:
        return "cancel"
    if norm in _ANSWER_CONTINUE:
        return "continue"
    return None


def ask_text(kind: str, language: str) -> str:
    return _ASK[kind][_lang(language)]


def chips(language: str) -> dict[str, Any]:
    lang = _lang(language)
    return {"choices": [_CHIP_CANCEL[lang], _CHIP_CONTINUE[lang]], "other_label": "", "other_allowed": False}


def _snapshot(draft: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy({k: v for k, v in draft.items() if k not in _EVERY_TURN_KEYS})


class CancelCheckMixin:
    """For a DraftSupervisor subclass. It sets _CANCEL_KIND and implements
    _cancel_now() (the flow's own cancel), _cancel_reply() (a reply in the
    flow's own response shape) and _cancel_correcting_text() (its "what would
    you like to correct?" question), then wraps its turn body with
    turn_with_cancel_check() inside its session lock."""

    _CANCEL_KIND = "booking"

    def _cancel_progress(self, draft: dict[str, Any]) -> dict[str, Any]:
        """What counts as progress in this flow: the draft without the keys
        that change on every turn. CORRECTING and CONFIRMING are one step
        here: going from "what would you like to correct?" back to the same
        readback with nothing changed is not progress. A flow overrides this
        when more of its states mean the same step (see appointment_supervisor)."""
        view = _snapshot(draft)
        if view.get("state") == "CORRECTING":
            view["state"] = "CONFIRMING"
        return view

    def _cancel_yes_no_question(self, draft: dict[str, Any]) -> bool:
        """True when the flow's last question was a real yes/no question;
        the app shows its own Yes/No buttons then and the flow handles "no"."""
        return draft.get("state") in _YES_NO_STATES

    def _cancel_now(self, farmer_id: str, session_id: str, text: str, include_audio: bool) -> dict[str, Any]:
        raise NotImplementedError

    def _cancel_reply(self, draft: dict[str, Any], text: str, input_transcript: str, include_audio: bool,
                      options: Optional[dict] = None, prompt: Optional[str] = None) -> dict[str, Any]:
        raise NotImplementedError

    def _cancel_correcting_text(self, draft: dict[str, Any]) -> str:
        raise NotImplementedError

    def _cancel_continue_after_no(self, farmer_id: str, session_id: str, text: str,
                                  include_audio: bool) -> dict[str, Any]:
        """What the flow's own "no" at its Yes/No question does (ask what to
        correct / change) -- run when the farmer chose to carry on."""
        raise NotImplementedError

    def _cancel_flow_reads_no(self, draft: dict[str, Any]) -> bool:
        """True at a step where this flow itself gives a plain "no" a meaning
        (e.g. add-animal's optional details: "no" = skip); see _cancel_flow_no."""
        return False

    def _cancel_flow_no(self, farmer_id: str, session_id: str, draft: dict[str, Any], text: str,
                        include_audio: bool) -> dict[str, Any]:
        """What a plain "no" means at a _cancel_flow_reads_no step, done
        without the model (the question itself offers "say 'no' to ...")."""
        raise NotImplementedError

    def _remember_reply(self, session_id: str, farmer_id: str, language: str, result: dict[str, Any],
                        clear_continued: bool) -> None:
        """Keep the flow's last question, to show it again when the farmer
        says "No, continue" to "Do you want to cancel?"."""
        after = self._load(session_id, farmer_id, language)
        if after.get("submitted") or after.get("state") in _DONE_STATES or result.get("released"):
            return
        after["last_reply"] = {"reply": result.get("response_text") or "", "prompt": result.get("prompt_text"),
                               "options": result.get("options")}
        if clear_continued:
            after.pop("cancel_check", None)
        self._save(after)

    def _cancel_hold_state(self, draft: dict[str, Any]) -> str:
        """The state the draft waits in while "Do you want to cancel?" is
        open. Same state by default; a flow whose state makes the app draw
        its own Yes/No buttons overrides it (see appointment_supervisor)."""
        return draft.get("state") or ""

    def _cancel_ask(self, draft: dict[str, Any], session_id: str, text: str, include_audio: bool,
                    show_again: dict[str, Any]) -> dict[str, Any]:
        """Ask "Do you want to cancel?" and remember what to show again if
        the farmer carries on (`show_again`: reply, prompt, options, state)."""
        draft["cancel_check"] = {"asked": True, **show_again}
        self._save(draft)
        _log.info("cancel_check ask flow=%s session=%s state=%s", self._CANCEL_KIND, session_id, draft.get("state"))
        question = ask_text(self._CANCEL_KIND, draft["language"])
        resp = self._cancel_reply(draft, question, text, include_audio, options=chips(draft["language"]), prompt=question)
        # Tells the chat router to send no form with this reply: the app
        # hides choice buttons when a form is shown, and these two buttons
        # are the whole point of the question (services/a2ui/widgets.py).
        resp[CANCEL_QUESTION_KEY] = True
        return resp

    def _cancel_end(self, draft: dict[str, Any], farmer_id: str, session_id: str, text: str, include_audio: bool,
                    reason: str) -> dict[str, Any]:
        _log.info("cancel_check cancel flow=%s session=%s state=%s reason=%s", self._CANCEL_KIND, session_id,
                  draft.get("state"), reason)
        draft.pop("cancel_check", None)
        self._save(draft)
        return self._cancel_now(farmer_id, session_id, text, include_audio)

    def turn_with_cancel_check(self, farmer_id: str, session_id: str, text: str, language: str,
                               include_audio: bool, run: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        draft = self._load(session_id, farmer_id, language)
        if language in SUPPORTED_LANGUAGES:
            # The farmer's current language, as the flow itself does on every turn.
            draft["language"] = language
        pending = draft.get("cancel_check") or {}
        active = not draft.get("submitted") and draft.get("state") not in _DONE_STATES
        stop, bare_no = is_stop(text), is_bare_no(text)

        # 1) The farmer is answering "Do you want to cancel?".
        if active and pending.get("asked"):
            choice = answer(text)
            draft.pop("cancel_check", None)
            if choice == "cancel":
                return self._cancel_end(draft, farmer_id, session_id, text, include_audio, "answer_yes")
            if choice == "continue":
                _log.info("cancel_check answer=continue flow=%s session=%s", self._CANCEL_KIND, session_id)
                if pending.get("state"):
                    draft["state"] = pending["state"]
                if pending.get("after_no"):
                    # Carry on after a "no" at a Yes/No question: what that
                    # "no" always did -- ask what to correct / change.
                    self._save(draft)
                    result = self._cancel_continue_after_no(farmer_id, session_id, text, include_audio)
                    after = self._load(session_id, farmer_id, language)
                    after["cancel_check"] = {"continued": True}
                    self._save(after)
                    return result
                draft["cancel_check"] = {"continued": True}
                self._save(draft)
                return self._cancel_reply(draft, pending.get("reply") or "", text, include_audio,
                                          options=pending.get("options"), prompt=pending.get("prompt"))
            # Anything else is a normal answer to the flow's question.
            if pending.get("state"):
                draft["state"] = pending["state"]
            self._save(draft)
            pending = {}

        # 2a) A plain "no" at a Yes/No question: ask before treating it as
        # "something is wrong". Decided here, before the flow and its model call.
        if active and self._cancel_yes_no_question(draft) and (stop or bare_no):
            if stop:
                return self._cancel_end(draft, farmer_id, session_id, text, include_audio, "stop_words")
            back_to = draft.get("state")
            draft["state"] = self._cancel_hold_state(draft)
            return self._cancel_ask(draft, session_id, text, include_audio, {"after_no": True, "state": back_to})

        # 2) At "what would you like to correct?" a plain "no" corrects
        # nothing; the flow would only show the same readback again (or
        # treat it as "wrong animal" and drop the animal). Handled here,
        # before the flow and its model call.
        if active and draft.get("state") == "CORRECTING" and (stop or bare_no):
            if stop or pending.get("continued"):
                return self._cancel_end(draft, farmer_id, session_id, text, include_audio,
                                        "stop_words" if stop else "no_again")
            return self._cancel_ask(draft, session_id, text, include_audio, {
                "reply": self._cancel_correcting_text(draft), "prompt": self._cancel_correcting_text(draft),
                "options": None, "state": "CORRECTING",
            })

        # 2b) A plain "no" at any other question (the date, the tag, the
        # quantity ...): it gives no value for that question. Before, the
        # flow asked the same thing again -- or, right after the animal was
        # matched, took it as "wrong animal" and dropped the animal. Asked
        # here instead, before the flow and its model call. ("wrong tag",
        # "not that animal", "no fever" are not a plain "no" and still go
        # to the flow.)
        last = draft.get("last_reply")
        if active and (stop or bare_no) and last and not self._cancel_flow_reads_no(draft):
            if stop or pending.get("continued"):
                return self._cancel_end(draft, farmer_id, session_id, text, include_audio,
                                        "stop_words" if stop else "no_again")
            return self._cancel_ask(draft, session_id, text, include_audio, {**last, "state": draft.get("state")})

        # 2c) A step that itself offers "no" as an answer ("say 'no' to
        # submit now"): a plain "no" there is that answer, never "cancel?".
        # Done without the model -- seen live, the model did not read
        # "no" as "skip" and the question came back.
        if active and (stop or bare_no) and self._cancel_flow_reads_no(draft):
            _log.info("cancel_check flow_no flow=%s session=%s state=%s", self._CANCEL_KIND, session_id,
                      draft.get("state"))
            draft.pop("cancel_check", None)
            return self._cancel_flow_no(farmer_id, session_id, draft, text, include_audio)

        # 3) Everything else runs through the flow as before.
        asked_yes_no = active and self._cancel_yes_no_question(draft)
        before = self._cancel_progress(draft) if active else None
        before_state = draft.get("state")
        result = run()

        if before is None or not (stop or bare_no) or result.get("released") or asked_yes_no:
            # Not a plain "no", or a "no" to a real yes/no question: the
            # flow's own handling stands. ("Carry on" only counts for the
            # very next reply.)
            if before is not None:
                self._remember_reply(session_id, farmer_id, language, result, bool(pending.get("continued")))
            return result
        after = self._load(session_id, farmer_id, language)
        if after.get("submitted") or after.get("state") in _DONE_STATES:
            return result
        if self._cancel_progress(after) != before:
            # The "no" meant something to the flow (a correction, a skip).
            self._remember_reply(session_id, farmer_id, language, result, True)
            return result

        if stop or pending.get("continued"):
            return self._cancel_end(after, farmer_id, session_id, text, include_audio,
                                    "stop_words" if stop else "no_again")

        # Nothing moved: ask. The booking stays at the step the farmer was
        # on (so the app shows no Yes/No buttons of its own over the
        # question); carrying on shows the flow's reply exactly as it was.
        show_again = {"reply": result.get("response_text") or "", "prompt": result.get("prompt_text"),
                      "options": result.get("options"), "state": after.get("state")}
        after["state"] = before_state
        return self._cancel_ask(after, session_id, text, include_audio, show_again)
