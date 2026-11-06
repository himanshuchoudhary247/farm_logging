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

from typing import Mapping, Optional


def parse_form_reply(text: str, keys: Mapping[str, str]) -> Optional[dict[str, str]]:
    """{field: value} when `text` is exactly a form message using only
    `keys` (form key, any case -> field name), else None.

    Two or more "key: value" parts are required: a single one could just as
    well be typed by hand, and the model reads that as before."""
    parts = [p.strip() for p in (text or "").split(";") if p.strip()]
    if len(parts) < 2:
        return None
    wanted = {k.lower(): v for k, v in keys.items()}
    values: dict[str, str] = {}
    for part in parts:
        key, sep, value = part.partition(":")
        key = key.strip().lower()
        if not sep or key not in wanted or not value.strip():
            return None
        values[wanted[key]] = value.strip()
    return values
