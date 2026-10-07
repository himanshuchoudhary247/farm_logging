"""Single source of truth for the classifier's intent set.

Before this file, intent descriptions lived in ~4 places (classifier's
_ROUTE_INSTRUCTION, WhatsApp channel's per-language `intent_labels`
catalog, docs/conversation_patterns.md, tests) and had already drifted
between them at least once. This is the canonical definition; every
other consumer reads from here.

Adding a fifth intent later touches ONE file. Removing an intent (or
tightening its wording) is one edit, one place -- no more grepping for
matching strings across the codebase.

Fields on IntentSpec:
    name -- canonical string key used in routing (`intent == "query"` etc).
    classifier_description -- long-form English boundary text the
        classifier LlmAgent reads to decide between categories. Rendered
        into _ROUTE_INSTRUCTION as one bullet per intent.
    labels -- short per-language human-readable label (5 languages,
        en/hi/ta/te/kn/mr), used by transport-layer messages that need to
        tell a farmer what's allowed on this channel (WhatsApp's
        blocked_intent message today; SMS/Telegram similar tomorrow).

The order of INTENTS entries below IS the order they appear in the
classifier prompt (bullet list order); pick order deliberately -- more
specific categories first, general-purpose `query` fallback last,
matching the existing prompt's shape.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


LANGUAGES = ("en", "hi", "ta", "te", "kn", "mr")


@dataclass(frozen=True)
class IntentSpec:
    name: str
    classifier_description: str
    labels: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        # Fail fast at import time on a partial catalog entry -- a missing
        # language label would only show up when a WhatsApp reply in that
        # language actually gets sent, which could be days later. Better
        # to crash the process at startup than silently ship a blank label.
        missing = [lang for lang in LANGUAGES if lang not in self.labels]
        if missing:
            raise ValueError(f"IntentSpec({self.name!r}) missing labels for languages: {missing}")


# Wording of classifier_description below is copied verbatim from the
# adk_router.py _ROUTE_INSTRUCTION block that this catalog replaces; the
# refactor is meant to be behaviorally identical, so a byte-for-byte
# preserve is the safest first move. Rewordings happen in follow-up PRs
# on this file, not here.
INTENTS: Dict[str, IntentSpec] = {
    "appointment": IntentSpec(
        name="appointment",
        classifier_description=(
            "booking a vet appointment, reporting a sick/injured animal, "
            "requesting a farm visit or treatment, OR reporting/logging a "
            "health event for an animal ALREADY on the farm (a treatment "
            "given, a vaccination done, a symptom noticed, a checkup "
            "completed)."
        ),
        labels={
            "en": "book a vet appointment or log a health event",
            "hi": "पशु चिकित्सक अपॉइंटमेंट बुक करना या स्वास्थ्य घटना दर्ज करना",
            "ta": "கால்நடை மருத்துவர் சந்திப்பு அல்லது சுகாதார நிகழ்வு பதிவு",
            "te": "పశువైద్యుని అపాయింట్‌మెంట్ లేదా ఆరోగ్య సంఘటన నమోదు",
            "kn": "ಪಶು ವೈದ್ಯರ ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ಅಥವಾ ಆರೋಗ್ಯ ಘಟನೆ ದಾಖಲಿಸಲು",
            "mr": "पशुवैद्यकीय अपॉइंटमेंट बुक करा किंवा आरोग्याची नोंद करा",
        },
    ),
    "add_animal": IntentSpec(
        name="add_animal",
        classifier_description=(
            "registering a brand-new animal that isn't on the farm's records "
            "yet -- the farmer wants to ADD it as a new entry (a new "
            "goat/sheep they bought, were given, or that was born). This is "
            "about the animal's identity itself (ID, species, breed, sex), "
            "not a health event."
        ),
        labels={
            "en": "register a new animal",
            "hi": "नया पशु पंजीकृत करना",
            "ta": "புதிய விலங்கு பதிவு செய்ய",
            "te": "కొత్త జంతువును నమోదు చేయడం",
            "kn": "ಹೊಸ ಪ್ರಾಣಿಯನ್ನು ನೋಂದಾಯಿಸಲು",
            "mr": "नवीन जनावर नोंदवा",
        },
    ),
    "weather": IntentSpec(
        name="weather",
        classifier_description=(
            "weather, rain, temperature, heat/cold stress, whether to move "
            "animals indoors, or feed-price/market questions tied to "
            "weather/season."
        ),
        labels={
            "en": "check weather",
            "hi": "मौसम देखना",
            "ta": "வானிலை பார்க்க",
            "te": "వాతావరణం చూడడం",
            "kn": "ಹವಾಮಾನ ನೋಡಲು",
            "mr": "हवामान पहा",
        },
    ),
    "query": IntentSpec(
        name="query",
        classifier_description=(
            "LOOKING UP the farmer's own EXISTING animals or records -- "
            "counts, lists, history, \"how many\", \"when was\", past "
            "vaccination records, past health logs, past appointments, "
            "general greetings, or anything unclear. This category is "
            "READ-ONLY -- it can only look up data that's already saved, "
            "never record something new. If a message could be read as "
            "either reporting a new event or asking about past ones, and it "
            "describes something that just happened, prefer \"appointment\" "
            "or \"add_animal\" (whichever fits) -- a farmer telling you "
            "what happened wants it recorded, not silently discarded."
        ),
        labels={
            "en": "ask about your animals or records",
            "hi": "अपने पशुओं या रिकॉर्ड के बारे में पूछना",
            "ta": "உங்கள் விலங்குகள் அல்லது பதிவுகள் பற்றி கேட்க",
            "te": "మీ జంతువుల లేదా రికార్డుల గురించి అడగడం",
            "kn": "ನಿಮ್ಮ ಪ್ರಾಣಿಗಳು ಅಥವಾ ದಾಖಲೆಗಳ ಬಗ್ಗೆ ಕೇಳಲು",
            "mr": "तुमच्या जनावरांबद्दल किंवा नोंदींबद्दल विचारा",
        },
    ),
}


VALID_INTENTS = tuple(INTENTS.keys())


def build_route_instruction() -> str:
    """Render the classifier's full instruction string from the catalog.
    Called once at classifier-agent construction time; output is
    identical byte-for-byte to the pre-refactor hand-written
    _ROUTE_INSTRUCTION (verified by a test)."""
    bullets = "\n".join(
        f"- \"{spec.name}\": {spec.classifier_description}"
        for spec in INTENTS.values()
    )
    # The two closing paragraphs stay static -- they explain intent
    # boundaries in ways that mix multiple intents in one sentence, so
    # they don't factor cleanly per-IntentSpec. Kept here as prose;
    # rewrite when we actually need more than 4 intents.
    return (
        "Classify what area of a livestock farm-management app a farmer's "
        "message belongs to, then call record_route exactly once with your "
        "decision. Never answer the farmer directly yourself -- only "
        "classify.\n"
        "\n"
        "Categories:\n"
        f"{bullets}\n"
        "\n"
        "\"appointment\" vs \"add_animal\": both can write data, but about "
        "different things -- \"my goat has a fever\" or \"book a vet visit\" "
        "is \"appointment\" (an EXISTING animal's health). \"I got a new "
        "goat, register it\" or \"add a new sheep to my farm\" is "
        "\"add_animal\" (the animal's own identity record, brand new).\n"
        "\n"
        "When genuinely ambiguous with no hint of a new event to record, "
        "prefer \"query\" -- it is the general-purpose fallback."
    )
