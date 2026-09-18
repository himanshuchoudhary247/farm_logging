"""Tiny local OTP-fetch server for the sandbox login flow.

Serves a page at http://localhost:5555/ with a phone-number input and a
button. Clicking the button queries the flokiq-sandbox otpverifications
table for the most recent OTP for that phone and shows it on the page.

Reads DB creds from ~/code/flokiquser/.env — never writes them out.

Run:
    source ~/code/farmer_chat/venv/bin/activate
    python ~/code/farmer_chat/skills/otp_server.py

Then open http://localhost:5555/ in a browser and click the button.
"""
from __future__ import annotations

import http.server
import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pymysql


PORT = int(os.environ.get("OTP_SERVER_PORT", "5555"))
DEFAULT_PHONE = os.environ.get("OTP_DEFAULT_PHONE", "9959737365")
ENV_PATH = Path.home() / "code" / "flokiquser" / ".env"


def _load_env() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("VITE_"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _fetch_otp(phone: str) -> dict:
    env = _load_env()
    conn = pymysql.connect(
        host=env["DB_HOST"], user=env["DB_USER"], password=env["DB_PASSWORD"],
        database="flokiq-sandbox", port=int(env["DB_PORT"]), connect_timeout=15,
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT u.phone, o.otp, o.createdAt "
                "FROM otpverifications o JOIN users u ON u.id = o.userId "
                "WHERE u.phone = %s "
                "ORDER BY o.createdAt DESC LIMIT 1",
                (phone,),
            )
            row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        return {"ok": False, "error": f"no OTP found for phone {phone}"}
    return {
        "ok": True,
        "phone": row["phone"],
        "otp": row["otp"],
        "createdAt": row["createdAt"].isoformat(),
    }


INDEX_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Sandbox OTP fetch</title>
<style>
  body {{ font-family: -apple-system, sans-serif; max-width: 480px; margin: 3rem auto; padding: 0 1rem; color: #222; }}
  h1 {{ font-size: 1.1rem; letter-spacing: 0.02em; text-transform: uppercase; color: #777; }}
  input, button {{ padding: 0.75rem 1rem; font-size: 1rem; border-radius: 8px; border: 1px solid #ccc; }}
  input {{ width: 100%; box-sizing: border-box; margin-bottom: 0.5rem; }}
  button {{ background: #b91c1c; color: white; border: 0; width: 100%; cursor: pointer; }}
  button:disabled {{ opacity: 0.5; cursor: wait; }}
  #out {{ margin-top: 1.5rem; padding: 1rem; border-radius: 8px; background: #f3f3f3; font-family: ui-monospace, monospace; white-space: pre-wrap; word-break: break-word; }}
  .otp {{ font-size: 2.5rem; font-weight: 700; letter-spacing: 0.15em; color: #b91c1c; margin: 0.5rem 0; }}
  .meta {{ font-size: 0.85rem; color: #666; }}
</style>
</head><body>
  <h1>Sandbox OTP fetch</h1>
  <input id="phone" value="{default_phone}" placeholder="10-digit phone" />
  <button id="btn" onclick="fetchOtp()">Get latest OTP</button>
  <div id="out"></div>
<script>
async function fetchOtp() {{
  const btn = document.getElementById('btn');
  const out = document.getElementById('out');
  const phone = document.getElementById('phone').value.trim();
  btn.disabled = true;
  out.textContent = 'querying...';
  try {{
    const r = await fetch('/otp?phone=' + encodeURIComponent(phone));
    const j = await r.json();
    if (j.ok) {{
      out.innerHTML = '<div class="otp">' + j.otp + '</div>'
        + '<div class="meta">phone: ' + j.phone + '<br>created: ' + j.createdAt + '</div>';
    }} else {{
      out.textContent = j.error || 'error';
    }}
  }} catch (e) {{
    out.textContent = 'error: ' + e.message;
  }} finally {{
    btn.disabled = false;
  }}
}}
</script>
</body></html>
"""


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            body = INDEX_HTML.format(default_phone=DEFAULT_PHONE).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/otp":
            qs = parse_qs(parsed.query)
            phone = (qs.get("phone") or [DEFAULT_PHONE])[0]
            try:
                result = _fetch_otp(phone)
                status = 200 if result.get("ok") else 404
            except Exception as exc:
                result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
                status = 500
            body = json.dumps(result, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, fmt, *args):
        return  # quiet


if __name__ == "__main__":
    print(f"OTP server listening on http://localhost:{PORT}/")
    http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
