"""Records card for farm questions as an A2UI widget (https://a2ui.org, spec v0.9).

When Chocolate answers a question about the farmer's own records (animals,
health logs, AI health checks, vaccinations, appointments -- the query
agent, which also answers the Health Report pill), its reply also carries a
read-only card built from the rows the query really returned. The layout
follows the shape of the data, never the question or the model's text:

  * one record with several fields -> a details card ("Label: value" lines)
  * a breakdown (one text column + one number column, several rows, e.g.
    animals per species) -> one line per group with its count and share,
    and the total
  * several records -> a header saying what they are and how many
    ("Vaccinations (5)", read from the columns), a summary of risk
    or status when those columns are present (e.g. "🔴 High risk: 1 ·
    🟢 Low risk: 3"), then one small card per record: its name on top, its
    risk, one line of what kind of animal it is ("Goat · Sirohi · Female"),
    then its other fields; a due date that has passed is marked
    "⚠️ Overdue". At most MAX_ITEMS cards; the card says how many are
    shown, and the app keeps the full table one tap away.

When the agent needed several lookups for one answer (a health report: AI
health checks, health problems, pending vaccines), the card shows each one
as its own section, in the order they were looked up (result["data_sets"]).

No card for a single value ("You have 53 animals." already says it), for no
rows, or when the query failed. The card has no buttons and sends nothing.

Built from the query agent's own result ({"answer", "data": {"columns",
"rows", "row_count", "truncated", "display": {"columns", "rows"}}}). Column
headings are the query agent's own localized headings (data.display), so
the card and the table use the same words. Values are cleaned for a farmer:
internal IDs, login fields and JSON objects are never shown, stored English
words (goat, female, pending, High) are shown in the app's language, dates
as DD-MM-YYYY in Indian time, JSON lists as "fever, cough", and long text is
cut short. Numbers keep 0-9, like the table, so tags and dates read the same.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date as _date, datetime, timedelta, timezone
from typing import Any, Mapping, Optional

from services.a2ui.common import clean, lang_code, surface_messages, widgets_enabled
from services.a2ui.weather_widget import _RISK_ICON, _TEXT as _WEATHER_TEXT

_log = logging.getLogger("a2ui_query_widget")
if not _log.handlers:
    _log.addHandler(logging.StreamHandler())
    _log.setLevel(logging.INFO)

# Cards in the list, lines per card, groups in a breakdown, lines in a
# details card: enough to read on a phone without scrolling past the chat.
MAX_ITEMS = 8
MAX_FIELDS = 4
MAX_GROUPS = 12
MAX_DETAILS = 12
# Long text (AI first-aid advice runs to 600+ characters) is cut here.
MAX_TEXT = 160

# Columns a farmer must never see: record IDs, login fields, file names. Any
# column named "id" or ending in "_id" is an internal ID too (animal_id,
# log_id, doctor_id, ...). Hidden by name, so an alias the query picks for its
# own column ("source", "type") is never hidden by mistake.
_HIDDEN = {"id", "password_hash", "login_username", "image"}
# Stored markers that mean nothing to a farmer (ai_health_logs.source is
# always "ai_unverified"): a column holding only these is not shown.
_INTERNAL_VALUES = {"ai_unverified"}
# A table's name as a value (a query that counts per table: "health_logs | 4")
# is shown as what those records are, in the farmer's language.
_TABLE_TOPICS = {"ai_health_logs": "health_checks", "vaccination_records": "vaccinations",
                 "appointments": "appointments", "health_logs": "health_logs", "animals": "animals"}
# What a record is about, for each card's title: the animal first (tag_or_name,
# or an alias the query gave it -- "animal_name", "animal", "name"), then what
# happened to it, then its species.
_EVENT_TITLE_COLUMNS = {"vaccine_name", "issue_summary", "issue"}
_ANIMAL_TITLE_RE = re.compile(r"(^|_)animal($|_)|(^|_)name$")
# Which kind of records a lookup returned, from the columns it returned (the
# query agent's tables, models.py): first match wins.
_TOPIC_COLUMNS = (
    ("health_checks", {"risk_level", "symptoms_reported", "potential_ailments", "ai_diagnosis_suggestion",
                       "first_aid_advice"}),
    ("vaccinations", {"vaccine_name", "administered_date", "due_date"}),
    ("appointments", {"issue_summary", "doctor_id"}),
    ("health_logs", {"recorded_at", "issue"}),
    ("animals", {"tag_or_name", "species", "breed", "sex"}),
)
# A due date that has passed matters unless the record is already done.
_DUE_COLUMN = "due_date"
_DONE_STATUSES = {"administered", "completed", "cancelled"}
# Lookups shown for one answer, at most (the last ones the agent made).
MAX_SECTIONS = 3
_RISK_COLUMNS = {"risk_level", "risk"}
_STATUS_COLUMN = "status"
# Columns whose stored English words registration also shows in the
# farmer's language (goat -> बकरी); other text is shown as stored.
_WORD_COLUMNS = {"species", "sex", "breed"}
# The kind-of-animal line always reads in this order, whatever order the query used.
_KIND_ORDER = ("species", "breed", "sex")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")
_AGGREGATE_RE = re.compile(r"^\s*(count|sum|total|avg|average|min|max)\b", re.IGNORECASE)
_AGGREGATE_WORD = {"count": "count", "sum": "total", "total": "total", "avg": "average", "average": "average"}
# A number column that counts things ("COUNT(*)", "animal_count", "total",
# "num_goats"): its groups add up, so the breakdown shows each share and the
# total. Any other number (an age, a weight) is shown as it is.
_COUNT_COLUMN_RE = re.compile(r"count|cnt|total|sum|num", re.IGNORECASE)
# Same Indian time the weather card uses (no daylight saving, no tz database needed).
_FARM_TZ = timezone(timedelta(hours=5, minutes=30))

_STATUS_ICON = {"pending": "⏳", "administered": "✅", "completed": "✅", "confirmed": "✅",
                "cancelled": "❌", "missed": "⚠️"}

# Words in the farmer's language. "statuses" covers the stored values of
# animals.status, appointments.status and vaccination_records.status; any
# other value is shown as stored.
_TEXT: dict[str, dict[str, Any]] = {
    "en": {"records": "{n} records", "showing": "Showing {shown} of {total}", "total": "Total",
           "details": "Details", "count": "Count", "average": "Average",
           "overdue": "Overdue", "topics": {"health_checks": "AI health checks", "vaccinations": "Vaccinations", "appointments": "Appointments", "health_logs": "Health problems", "animals": "Animals"},
           "statuses": {"active": "Active", "sold": "Sold", "deceased": "Died", "culled": "Culled",
                        "pregnant": "Pregnant", "sick": "Sick", "pending": "Pending", "administered": "Given",
                        "completed": "Completed", "cancelled": "Cancelled", "confirmed": "Confirmed",
                        "missed": "Missed"}},
    "hi": {"records": "{n} रिकॉर्ड", "showing": "{total} में से {shown} दिखाए गए", "total": "कुल",
           "details": "विवरण", "count": "संख्या", "average": "औसत",
           "overdue": "समय निकल गया", "topics": {"health_checks": "AI स्वास्थ्य जाँच", "vaccinations": "टीके", "appointments": "अपॉइंटमेंट", "health_logs": "स्वास्थ्य समस्याएँ", "animals": "पशु"},
           "statuses": {"active": "सक्रिय", "sold": "बेचा गया", "deceased": "मृत", "culled": "हटाया गया",
                        "pregnant": "गर्भवती", "sick": "बीमार", "pending": "बाकी", "administered": "लगाया गया",
                        "completed": "पूरा हुआ", "cancelled": "रद्द", "confirmed": "पक्का", "missed": "छूट गया"}},
    "mr": {"records": "{n} नोंदी", "showing": "{total} पैकी {shown} दाखवल्या", "total": "एकूण",
           "details": "तपशील", "count": "संख्या", "average": "सरासरी",
           "overdue": "मुदत संपली", "topics": {"health_checks": "AI आरोग्य तपासणी", "vaccinations": "लसीकरण", "appointments": "भेटी", "health_logs": "आरोग्य समस्या", "animals": "जनावरे"},
           "statuses": {"active": "सक्रिय", "sold": "विकले", "deceased": "मृत", "culled": "काढून टाकले",
                        "pregnant": "गाभण", "sick": "आजारी", "pending": "बाकी", "administered": "दिली",
                        "completed": "पूर्ण", "cancelled": "रद्द", "confirmed": "निश्चित", "missed": "चुकली"}},
    "ta": {"records": "{n} பதிவுகள்", "showing": "{total} இல் {shown} காட்டப்படுகிறது", "total": "மொத்தம்",
           "details": "விவரங்கள்", "count": "எண்ணிக்கை", "average": "சராசரி",
           "overdue": "தேதி கடந்தது", "topics": {"health_checks": "AI சுகாதார சோதனைகள்", "vaccinations": "தடுப்பூசிகள்", "appointments": "சந்திப்புகள்", "health_logs": "சுகாதார பிரச்சினைகள்", "animals": "விலங்குகள்"},
           "statuses": {"active": "செயலில்", "sold": "விற்கப்பட்டது", "deceased": "இறந்தது",
                        "culled": "நீக்கப்பட்டது", "pregnant": "சினை", "sick": "நோய்வாய்ப்பட்டது",
                        "pending": "நிலுவையில்", "administered": "போடப்பட்டது", "completed": "முடிந்தது",
                        "cancelled": "ரத்து", "confirmed": "உறுதி", "missed": "தவறியது"}},
    "te": {"records": "{n} రికార్డులు", "showing": "{total} లో {shown} చూపిస్తున్నాం", "total": "మొత్తం",
           "details": "వివరాలు", "count": "సంఖ్య", "average": "సగటు",
           "overdue": "గడువు దాటింది", "topics": {"health_checks": "AI ఆరోగ్య తనిఖీలు", "vaccinations": "టీకాలు", "appointments": "అపాయింట్‌మెంట్లు", "health_logs": "ఆరోగ్య సమస్యలు", "animals": "జంతువులు"},
           "statuses": {"active": "యాక్టివ్", "sold": "అమ్మేశారు", "deceased": "చనిపోయింది",
                        "culled": "తొలగించారు", "pregnant": "చూడి", "sick": "అనారోగ్యం", "pending": "పెండింగ్",
                        "administered": "వేశారు", "completed": "పూర్తయింది", "cancelled": "రద్దు",
                        "confirmed": "నిర్ధారించారు", "missed": "తప్పిపోయింది"}},
    "kn": {"records": "{n} ದಾಖಲೆಗಳು", "showing": "{total} ರಲ್ಲಿ {shown} ತೋರಿಸಲಾಗಿದೆ", "total": "ಒಟ್ಟು",
           "details": "ವಿವರಗಳು", "count": "ಸಂಖ್ಯೆ", "average": "ಸರಾಸರಿ",
           "overdue": "ಅವಧಿ ಮೀರಿದೆ", "topics": {"health_checks": "AI ಆರೋಗ್ಯ ತಪಾಸಣೆಗಳು", "vaccinations": "ಲಸಿಕೆಗಳು", "appointments": "ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್‌ಗಳು", "health_logs": "ಆರೋಗ್ಯ ಸಮಸ್ಯೆಗಳು", "animals": "ಪ್ರಾಣಿಗಳು"},
           "statuses": {"active": "ಸಕ್ರಿಯ", "sold": "ಮಾರಾಟವಾಗಿದೆ", "deceased": "ಸತ್ತಿದೆ",
                        "culled": "ತೆಗೆದುಹಾಕಲಾಗಿದೆ", "pregnant": "ಗಬ್ಬ", "sick": "ಅನಾರೋಗ್ಯ", "pending": "ಬಾಕಿ",
                        "administered": "ನೀಡಲಾಗಿದೆ", "completed": "ಪೂರ್ಣಗೊಂಡಿದೆ", "cancelled": "ರದ್ದು",
                        "confirmed": "ದೃಢಪಡಿಸಲಾಗಿದೆ", "missed": "ತಪ್ಪಿದೆ"}},
    "ml": {"records": "{n} രേഖകൾ", "showing": "{total} ൽ {shown} കാണിക്കുന്നു", "total": "ആകെ",
           "details": "വിശദാംശങ്ങൾ", "count": "എണ്ണം", "average": "ശരാശരി",
           "overdue": "സമയം കഴിഞ്ഞു", "topics": {"health_checks": "AI ആരോഗ്യ പരിശോധനകൾ", "vaccinations": "വാക്സിനുകൾ", "appointments": "അപ്പോയിന്റ്മെന്റുകൾ", "health_logs": "ആരോഗ്യ പ്രശ്നങ്ങൾ", "animals": "മൃഗങ്ങൾ"},
           "statuses": {"active": "സജീവം", "sold": "വിറ്റു", "deceased": "ചത്തു", "culled": "ഒഴിവാക്കി",
                        "pregnant": "ഗർഭിണി", "sick": "രോഗം", "pending": "ബാക്കി", "administered": "നൽകി",
                        "completed": "പൂർത്തിയായി", "cancelled": "റദ്ദാക്കി", "confirmed": "സ്ഥിരീകരിച്ചു",
                        "missed": "നഷ്ടമായി"}},
}


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value == value  # NaN != NaN


def _number_text(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.1f}".rstrip("0").rstrip(".")


def _json_value(value: Any) -> Any:
    """A JSON list or object stored as text (symptoms_reported, params), parsed; else None."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not (text.startswith("[") and text.endswith("]")) and not (text.startswith("{") and text.endswith("}")):
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


def _date_text(value: str) -> Optional[str]:
    """"2026-10-30" or an ISO timestamp -> "30-10-2026" (the day in Indian time); None if not a date."""
    if _DATE_RE.match(value):
        try:
            return datetime.strptime(value, "%Y-%m-%d").strftime("%d-%m-%Y")
        except ValueError:
            return None
    if _DATETIME_RE.match(value):
        try:
            moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if moment.tzinfo is not None:
            moment = moment.astimezone(_FARM_TZ)
        return moment.strftime("%d-%m-%Y")
    return None


def _cut(text: str) -> str:
    if len(text) <= MAX_TEXT:
        return text
    head = text[:MAX_TEXT].rsplit(" ", 1)[0].rstrip(" ,.;:")
    return (head or text[:MAX_TEXT]) + "…"


class _Words:
    """Turns stored values into what the farmer reads, in one language."""

    def __init__(self, language: str, value_labels: Optional[Mapping[str, str]]):
        self.lang = lang_code(language, _TEXT)
        self.text = _TEXT[self.lang]
        self.risk_text = _WEATHER_TEXT.get(self.lang, _WEATHER_TEXT["en"])
        self.values = value_labels or {}

    def risk(self, value: Any) -> str:
        key = clean(value).lower() if isinstance(value, str) else ""
        return f"{_RISK_ICON[key]} {self.risk_text[key]}" if key in _RISK_ICON else ""

    def status(self, value: Any) -> str:
        key = clean(value).lower() if isinstance(value, str) else ""
        word = self.text["statuses"].get(key)
        if not word:
            return clean(value) if isinstance(value, str) else ""
        icon = _STATUS_ICON.get(key)
        return f"{icon} {word}" if icon else word

    def value(self, column: str, value: Any) -> str:
        """What the farmer reads for one cell; '' for an empty cell."""
        if value is None:
            return ""
        if isinstance(value, bool):
            return "✓" if value else "✗"
        if _is_number(value):
            return _number_text(value)
        if not isinstance(value, str):
            return _cut(str(value))
        text = value.strip()
        if not text:
            return ""
        if column in _RISK_COLUMNS and self.risk(text):
            return self.risk(text)
        if column == _STATUS_COLUMN:
            return self.status(text)
        if text.lower() in _TABLE_TOPICS:
            return self.text["topics"][_TABLE_TOPICS[text.lower()]]
        parsed = _json_value(text)
        if isinstance(parsed, list):
            return _cut(", ".join(clean(str(v)) for v in parsed if v not in (None, "") and clean(str(v))))
        date = _date_text(text)
        if date:
            return date
        if column in _WORD_COLUMNS:
            word = self.values.get(text.lower(), self.values.get(text))
            # No farmer word for it (English, or a breed name): the stored word, capitalized ("goat" -> "Goat").
            text = word if word else text[:1].upper() + text[1:]
        return _cut(text)

    def heading(self, raw: str, shown: str) -> str:
        """The column heading: the query agent's localized one; for a heading
        it has no word for (an alias like COUNT(*) or "total"), a plain one."""
        if shown and shown != raw:
            return shown
        match = _AGGREGATE_RE.match(raw)
        if match and match.group(1).lower() in _AGGREGATE_WORD:
            return self.text[_AGGREGATE_WORD[match.group(1).lower()]]
        pretty = raw.replace("_", " ").strip()
        return pretty[:1].upper() + pretty[1:] if pretty else raw


def _visible_columns(columns: list[str], rows: list[list[Any]]) -> list[int]:
    """Indexes of the columns worth showing: no IDs or login fields, no
    JSON objects, no column that is empty in every row."""
    keep = []
    for i, raw in enumerate(columns):
        name = raw.strip().lower()
        if name in _HIDDEN or name.endswith("_id"):
            continue
        cells = [r[i] for r in rows if r[i] not in (None, "")]
        if not cells:
            continue
        if all(isinstance(_json_value(c), dict) for c in cells):
            continue
        if all(isinstance(c, str) and c.strip().lower() in _INTERNAL_VALUES for c in cells):
            continue
        keep.append(i)
    return keep


def _title_column(columns: list[str], visible: list[int], rows: list[list[Any]],
                  fallback: bool = True) -> Optional[int]:
    """The column each card is titled by: the animal, else what happened,
    else the species; with `fallback`, else the first text column."""
    def rank(i: int) -> Optional[int]:
        name = columns[i].strip().lower()
        if any(_is_number(r[i]) for r in rows):
            return None
        if name == "tag_or_name":
            return 0
        if name in _EVENT_TITLE_COLUMNS:
            return 2
        if _ANIMAL_TITLE_RE.search(name):
            return 1
        return 3 if name == "species" else None
    ranked = sorted((rank(i), pos, i) for pos, i in enumerate(visible) if rank(i) is not None)
    if ranked:
        return ranked[0][2]
    if not fallback:
        return None
    for i in visible:
        if not any(_is_number(r[i]) for r in rows):
            return i
    return visible[0] if visible else None


def _topic(columns: list[str]) -> Optional[str]:
    names = {c.strip().lower() for c in columns}
    for topic, marks in _TOPIC_COLUMNS:
        if names & marks:
            return topic
    return None


def _is_breakdown(visible: list[int], rows: list[list[Any]]) -> Optional[tuple[int, int]]:
    """(label column, number column) when the rows are groups with a number each."""
    if len(visible) != 2 or len(rows) < 2:
        return None
    a, b = visible
    for label, number in ((a, b), (b, a)):
        if all(_is_number(r[number]) for r in rows) and not any(_is_number(r[label]) for r in rows):
            return label, number
    return None


def _summary(columns: list[str], visible: list[int], rows: list[list[Any]], words: _Words) -> str:
    """"🔴 High risk: 1 · 🟢 Low risk: 3" over all returned rows, for a risk or status column."""
    for i in visible:
        name = columns[i].strip().lower()
        if name in _RISK_COLUMNS:
            show = words.risk
        elif name == _STATUS_COLUMN:
            show = words.status
        else:
            continue
        counts: dict[str, int] = {}
        for r in rows:
            label = show(r[i]) if isinstance(r[i], str) else ""
            if label:
                counts[label] = counts.get(label, 0) + 1
        if name in _RISK_COLUMNS:
            order = [words.risk(level) for level in ("high", "medium", "low")]
            ordered = [(k, counts[k]) for k in order if k in counts]
        else:
            ordered = list(counts.items())
        if ordered and sum(counts.values()) >= 2:
            return " · ".join(f"{label}: {n}" for label, n in ordered[:4])
    return ""


def build_query_widget(result: Any, language: str, surface_id: str = "query",
                       value_labels: Optional[Mapping[str, str]] = None,
                       today: Optional[_date] = None) -> Optional[list[dict]]:
    """A2UI v0.9 messages for the records card, or None when there is
    nothing a card would add (no data, one value, failed query). `today`
    (for overdue dates) defaults to today in India."""
    built = _build(result, language, surface_id, value_labels, today)
    return built[0] if built else None


def _datasets(result: dict) -> list[Any]:
    """The lookups for this answer: every distinct one the agent made
    (data_sets), or just its last one (data)."""
    sets = result.get("data_sets")
    if isinstance(sets, list) and len([d for d in sets if isinstance(d, dict)]) >= 2:
        return [d for d in sets if isinstance(d, dict)]
    return [result.get("data")]


def _build(result: Any, language: str, surface_id: str, value_labels: Optional[Mapping[str, str]],
           today: Optional[_date] = None) -> Optional[tuple[list[dict], str, int]]:
    """(messages, shape, cards or groups shown), or None."""
    if not isinstance(result, dict):
        return None
    words = _Words(language, value_labels)
    today = today or datetime.now(_FARM_TZ).date()
    components: list[dict[str, Any]] = [{"id": "root", "component": "Card", "child": "card"}]
    sets = _datasets(result)
    # Lookups that add something (a single count does not), the last MAX_SECTIONS of them.
    useful = [d for d in sets if _section(d, words, today, [], "") is not None][-MAX_SECTIONS:]
    sections = []
    for k, data in enumerate(useful):
        # One lookup keeps the plain ids ("title", "i0"); several get a prefix each.
        section = _section(data, words, today, components, f"s{k}_" if len(useful) > 1 else "")
        if section:
            sections.append(section)
    if not sections:
        return None
    children: list[str] = []
    for n, (ids, _shape, _shown) in enumerate(sections):
        if n:
            components.append({"id": f"sep{n}", "component": "Divider"})
            children.append(f"sep{n}")
        children += ids
    components.insert(1, {"id": "card", "component": "Column", "children": children})
    shape = "+".join(sec[1] for sec in sections)
    return surface_messages(surface_id, components, "/query", {}), shape, sum(sec[2] for sec in sections)


def _section(data: Any, words: _Words, today: _date, components: list[dict[str, Any]],
             p: str) -> Optional[tuple[list[str], str, int]]:
    """Components for one lookup's rows, added to `components`: (the ids that
    go into the card, shape, cards or groups shown), or None when the rows
    would add nothing (no rows, one value, unusable data)."""
    if not isinstance(data, dict):
        return None
    columns = data.get("columns")
    if not isinstance(columns, list) or not columns or not all(isinstance(c, str) for c in columns):
        return None
    rows = [r for r in (data.get("rows") or []) if isinstance(r, list) and len(r) == len(columns)]
    if not rows:
        return None
    display = data.get("display") if isinstance(data.get("display"), dict) else {}
    shown_columns = display.get("columns")
    if not (isinstance(shown_columns, list) and len(shown_columns) == len(columns)):
        shown_columns = columns
    visible = _visible_columns(columns, rows)
    if not visible or (len(rows) == 1 and len(visible) == 1):
        return None
    if not any(not _is_number(r[i]) for i in visible for r in rows):
        return None  # numbers with nothing saying what they are ("0, 0, 0") help no one

    raw = [c.strip().lower() for c in columns]
    heading = {i: words.heading(columns[i], clean(str(shown_columns[i]))) for i in visible}
    total = data.get("row_count") if _is_number(data.get("row_count")) else len(rows)
    total = max(int(total), len(rows))
    truncated = bool(data.get("truncated"))
    topic = _topic(columns)
    topic_word = words.text["topics"].get(topic, "") if topic else ""
    status_i = next((i for i, name in enumerate(raw) if name == _STATUS_COLUMN), None)
    children: list[str] = []

    def text(cid: str, value: str, variant: str = "body") -> str:
        components.append({"id": p + cid, "component": "Text", "text": value, "variant": variant})
        return p + cid

    def cell(i: int, row: list[Any]) -> str:
        """One field as the farmer reads it; a passed due date (not done yet) is marked overdue."""
        value = words.value(raw[i], row[i])
        if value and raw[i] == _DUE_COLUMN and isinstance(row[i], str) and _DATE_RE.match(row[i].strip()):
            done = status_i is not None and clean(str(row[status_i])).lower() in _DONE_STATUSES
            try:
                passed = _date.fromisoformat(row[i].strip()) < today
            except ValueError:
                passed = False
            if passed and not done:
                value = f"{value} ⚠️ {words.text['overdue']}"
        return value

    breakdown = _is_breakdown(visible, rows)
    if len(rows) == 1:
        shape = "details"
        row = rows[0]
        title = _title_column(columns, visible, rows, fallback=False)
        title_value = words.value(raw[title], row[title]) if title is not None else ""
        if p and topic_word and title_value:
            # One of several sections: say what it is too ("Health problems · Gauri").
            title_value = f"{topic_word} · {title_value}"
        children.append(text("title", title_value or topic_word or words.text["details"], "h4"))
        if not p:  # a section already has a line above it
            components.append({"id": p + "divider", "component": "Divider"})
            children.append(p + "divider")
        order = [i for i in visible if raw[i] in _RISK_COLUMNS] + [i for i in visible if raw[i] not in _RISK_COLUMNS]
        lines = 0
        for i in order:
            if i == title or lines >= MAX_DETAILS:
                continue
            value = cell(i, row)
            if value:
                risk = raw[i] in _RISK_COLUMNS and value.startswith(tuple(_RISK_ICON.values()))
                children.append(text(f"f{i}", value if risk else f"{heading[i]}: {value}"))
                lines += 1
        shown = 1
    elif breakdown:
        shape = "breakdown"
        label_i, number_i = breakdown
        counts = bool(_COUNT_COLUMN_RE.search(columns[number_i])) and all(
            float(r[number_i]).is_integer() and r[number_i] >= 0 for r in rows)
        title = heading[label_i] if counts else f"{heading[label_i]} · {heading[number_i]}"
        children.append(text("title", title, "h4"))
        groups = rows[:MAX_GROUPS]
        whole = sum(r[number_i] for r in rows) if counts else 0
        for g, r in enumerate(groups):
            value = _number_text(r[number_i])
            if counts and whole > 0:
                value = f"{value} · {round(100 * r[number_i] / whole)}%"
            label = words.value(raw[label_i], r[label_i]) or "–"
            components.append({"id": f"{p}g{g}_l", "component": "Column", "weight": 3,
                               "children": [text(f"g{g}_lt", label)]})
            components.append({"id": f"{p}g{g}_v", "component": "Column", "weight": 2, "align": "center",
                               "children": [text(f"g{g}_vt", value, "h5")]})
            components.append({"id": f"{p}g{g}", "component": "Row", "children": [f"{p}g{g}_l", f"{p}g{g}_v"]})
            children.append(f"{p}g{g}")
        if counts and not truncated:
            components.append({"id": p + "divider", "component": "Divider"})
            children.append(p + "divider")
            components.append({"id": p + "sum_l", "component": "Column", "weight": 3,
                               "children": [text("sum_lt", words.text["total"], "h5")]})
            components.append({"id": p + "sum_v", "component": "Column", "weight": 2, "align": "center",
                               "children": [text("sum_vt", _number_text(whole), "h5")]})
            components.append({"id": p + "sum", "component": "Row", "children": [p + "sum_l", p + "sum_v"]})
            children.append(p + "sum")
        shown = len(groups)
        if shown < len(rows) or truncated:
            children.append(text("more", words.text["showing"].format(
                shown=shown, total=f"{total}+" if truncated else total), "caption"))
    else:
        shape = "list"
        count = f"{total}+" if truncated else str(total)
        children.append(text("title", f"{topic_word} ({count})" if topic_word
                             else words.text["records"].format(n=count), "h4"))
        summary = _summary(columns, visible, rows, words)
        if summary:
            children.append(text("summary", summary))
        title = _title_column(columns, visible, rows)
        risk_cols = [i for i in visible if raw[i] in _RISK_COLUMNS and i != title]
        # Species, breed, sex read on their own, so they share one line without labels.
        kind_cols = sorted((i for i in visible if raw[i] in _WORD_COLUMNS and i != title),
                           key=lambda i: _KIND_ORDER.index(raw[i]))
        other_cols = [i for i in visible if i != title and i not in risk_cols and i not in kind_cols]
        items = rows[:MAX_ITEMS]
        for n, r in enumerate(items):
            cells = [text(f"i{n}_t", words.value(raw[title], r[title]) or "–", "h5")] if title is not None else []
            # Risk right under the name, without a label: on a health record it matters most.
            for i in risk_cols:
                value = cell(i, r)
                if value:
                    cells.append(text(f"i{n}_f{i}", value))
            kind = " · ".join(v for v in (words.value(raw[i], r[i]) for i in kind_cols) if v)
            if kind:
                cells.append(text(f"i{n}_kind", kind))
            lines = 0
            for i in other_cols:
                if lines >= MAX_FIELDS:
                    break
                value = cell(i, r)
                if value:
                    cells.append(text(f"i{n}_f{i}", f"{heading[i]}: {value}", "caption"))
                    lines += 1
            components.append({"id": f"{p}i{n}_col", "component": "Column", "children": cells})
            components.append({"id": f"{p}i{n}", "component": "Card", "child": f"{p}i{n}_col"})
            children.append(f"{p}i{n}")
        shown = len(items)
        if shown < len(rows) or truncated:
            children.append(text("more", words.text["showing"].format(shown=shown, total=count), "caption"))
    return children, shape, shown


def query_widget_for(farmer_id: str, session_id: str, result: Any, language: str) -> Optional[list[dict]]:
    """The card for this farm-records reply, or None. Never raises: a
    problem building the card only drops the card, never the reply."""
    if not widgets_enabled() or not isinstance(result, dict) or not isinstance(result.get("data"), dict):
        return None
    try:
        value_labels = None
        try:
            # The same farmer words registration reads back (goat -> बकरी,
            # female -> मादा), so a record reads the same everywhere.
            from services.animal_registration import service as registration
            value_labels = registration._VALUE_LABELS.get(lang_code(language, registration._VALUE_LABELS))
        except Exception as exc:  # stored English words are still readable
            _log.warning("a2ui query widget without value words farmer=%s err=%s", farmer_id, exc)
        built = _build(result, language, f"query-{session_id}", value_labels)
    except Exception as exc:  # the reply must never fail because of the card
        _log.warning("a2ui query widget skipped farmer=%s err=%s", farmer_id, exc)
        return None
    if not built:
        return None
    messages, shape, shown = built
    _log.info("a2ui query widget sent farmer=%s shape=%s rows=%s shown=%s lookups=%d",
              farmer_id, shape, result["data"].get("row_count"), shown, len(_datasets(result)))
    return messages
