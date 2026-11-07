"""Read a chat form's submit message without the model.

The app's forms (services/a2ui: the booking form, the add-animal form) send
one chat message "key: value; key: value" built from fixed keys
(flokiquser lib/a2ui.ts actionToChatText). That text is written by our own
app, so it is read here directly instead of asking the model -- seen live,
the model dropped fields from it (the booking date, the Hindi problem, the
goat's breed) and the farmer was asked again for what they had just picked.
No model call.
"""
from __future__ import annotations

from typing import Iterable, Mapping, Optional


def parse_form_reply(text: str, keys: Mapping[str, str],
                     free_text: Iterable[str] = ()) -> Optional[dict[str, str]]:
    """{field: value} when `text` is a form message using only `keys`
    (form key, any case -> field name), else None.

    Two or more "key: value" parts are required: a single one could just as
    well be typed by hand, and the model reads that as before.

    A key with an empty value ("breed: ") is a field left empty: it is
    skipped, not a reason to drop the whole message. (The app leaves empty
    fields out, but a part with nothing after the colon must not make every
    other field go to the model.) At least one value is needed.

    `free_text` names fields whose value is typed by the farmer (the
    booking's "other problem"): a ";" typed inside such a value stays part
    of it -- the part after it starts with no known key, so it continues
    that value. Anywhere else, a part with no known key means the text is
    not a form message."""
    wanted = {k.lower(): v for k, v in keys.items()}
    free = set(free_text)
    values: dict[str, str] = {}
    known_parts = 0
    current: Optional[str] = None
    for raw in (text or "").split(";"):
        part = raw.strip()
        if not part:
            continue
        key, sep, value = part.partition(":")
        key = key.strip().lower()
        if sep and key in wanted:
            known_parts += 1
            current = wanted[key]
            if value.strip():
                values[current] = value.strip()
            continue
        if current in free and current in values:
            values[current] = f"{values[current]}; {part}"
            continue
        return None
    if known_parts < 2 or not values:
        return None
    return values


def form_shape(text: str, keys: Mapping[str, str]) -> str:
    """"app" when `text` is written exactly the way the app's forms write
    it (the form's own keys, in the form's order, "key: value" joined by
    "; "), else "typed". Both are read the same way; this only tells a
    real form submit from a typed look-alike in the log."""
    order = list(keys)
    positions = []
    for part in (text or "").split("; "):
        key, sep, _ = part.partition(": ")
        if sep and key in order:
            positions.append(order.index(key))
    in_order = len(positions) >= 2 and positions == sorted(set(positions))
    return "app" if in_order and text == text.strip() else "typed"
