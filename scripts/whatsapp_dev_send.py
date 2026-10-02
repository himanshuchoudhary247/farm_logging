#!/usr/bin/env python3
"""Local development harness for the WhatsApp channel.

Fires a canned inbound webhook body at `POST /whatsapp/webhook` on a
locally-running uvicorn, so the whole channel pipeline (dedupe -> rate
limit -> farmer resolve -> language detect -> route_turn_adk -> reply
send) can be exercised without a real Meta or Twilio account. Uses
provider=mock by default (defined in config/channels.yaml or set via
`WHATSAPP_PROVIDER=mock` on the server before starting it).

Usage:
    python scripts/whatsapp_dev_send.py --text "how many animals do I have"
    python scripts/whatsapp_dev_send.py --text "बकरी की जानकारी दिखाओ" --from "+919876543210"
    python scripts/whatsapp_dev_send.py --text "book vet visit" --from "+911111111111"

The server must be running (default: http://127.0.0.1:8000) with
WHATSAPP_ENABLED=1 and WHATSAPP_PROVIDER=mock, so the mock provider's
`verify_signature` (always True) lets the request through the webhook
gate. The mock provider records outbound sends in-process; check the
server logs (INFO level, look for `whatsapp send_text` / router info
lines) to see what got dispatched and what the router replied with.

Exit code: 0 on 2xx, 1 on any other status.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request


def main() -> int:
    p = argparse.ArgumentParser(description="Fire a canned WhatsApp inbound at localhost")
    p.add_argument("--text", required=True, help="message text")
    p.add_argument("--from", dest="from_phone", default="+919876543210",
                   help="sender phone (default: +919876543210)")
    p.add_argument("--id", default=None,
                   help="message id (default: auto-generated per call)")
    p.add_argument("--url", default="http://127.0.0.1:8000/whatsapp/webhook",
                   help="webhook URL (default: local uvicorn on 8000)")
    args = p.parse_args()

    body = {
        "from_phone": args.from_phone,
        "text": args.text,
        "id": args.id or f"dev-{time.time_ns()}",
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        args.url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(f"HTTP {resp.status}")
            print(resp.read().decode("utf-8"))
            return 0 if 200 <= resp.status < 300 else 1
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code}: {exc.reason}")
        try:
            print(exc.read().decode("utf-8"))
        except Exception:
            pass
        return 1
    except urllib.error.URLError as exc:
        print(f"connection error: {exc.reason}")
        print("Is the server running with WHATSAPP_ENABLED=1 WHATSAPP_PROVIDER=mock?")
        return 1


if __name__ == "__main__":
    sys.exit(main())
