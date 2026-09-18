"""End-to-end automation to register a test farmer in flokiq-sandbox.

Runs the whole login + KYC flow without touching the mobile UI:
  1. POST /auth/login with a phone number → sandbox generates OTP
  2. Read the OTP from the otpverifications table
  3. POST /auth/verify-otp → sandbox returns a bearer token
  4. PUT /farmers with a filled dummy KYC payload → farmer created

After running, log in on the app with the same phone; you skip the KYC
form and land on the real dashboard.

Usage:
    source ~/code/farmer_chat/venv/bin/activate
    python ~/code/farmer_chat/skills/register_test_farmer.py [phone]

Phone defaults to $OTP_DEFAULT_PHONE (or 9959737365).
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import pymysql
import requests

ENV_PATH = Path.home() / "code" / "flokiquser" / ".env"


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
    return env


def fetch_otp_by_id(env: dict[str, str], otp_id: str, tries: int = 6) -> int:
    for _ in range(tries):
        conn = pymysql.connect(
            host=env["DB_HOST"], user=env["DB_USER"], password=env["DB_PASSWORD"],
            database="flokiq-sandbox", port=int(env["DB_PORT"]), connect_timeout=15,
            cursorclass=pymysql.cursors.DictCursor,
        )
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT otp FROM otpverifications WHERE id=%s", (otp_id,))
                row = cur.fetchone()
        finally:
            conn.close()
        if row and row["otp"] is not None:
            return int(row["otp"])
        time.sleep(0.5)
    raise RuntimeError(f"OTP for otpId={otp_id} not written within retry budget")


DUMMY_KYC = {
    "aadharNo": "999999999999",
    "fullName": "Test Farmer",
    "gender": "male",
    "fatherOrSpouseName": "Test Parent",
    "dob": "1990-01-01",
    "alternateMobile": "",
    "email": "",
    "hasPanCard": "no",
    "panNo": "",
    "religion": "",
    "caste": "",
    "address_1": "123 Test Street",
    "address_2": "",
    "city": "Hyderabad",
    "state": "Telangana",
    "pincode": "500001",
    "country": "India",
    "aadharPhoto": "",
    "governmentIdPhoto": "",
    "education": "Primary",
    "otherEducation": "",
    "occupation": "Farmer",
    "otherOccupation": "",
    "farmingExperience": "1 to 3",
    "landHolding": "1 acre",
    "organizations": [],
    "otherOrganizations": "",
    "hasGovernmentId": "no",
    "isAadharVerified": False,
    "isPanVerified": False,
    "panVerifiedData": {},
    "boardingDetails": {"category": "livestock-details"},
}


def main() -> None:
    env = load_env()
    api_base = env.get("VITE_SITE_KEY", "https://sandboxapi.flokiq.com/api/v1")
    phone = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("OTP_DEFAULT_PHONE", "9959737365")

    print(f"1/4 login → {phone}")
    r = requests.post(f"{api_base}/auth/login", json={"phone": phone}, timeout=15)
    r.raise_for_status()
    body = r.json()
    otp_id = body.get("otpId")
    if not otp_id:
        raise RuntimeError(f"no otpId in /auth/login response: {body}")

    print(f"2/4 fetching OTP from DB (otpId={otp_id})")
    otp = fetch_otp_by_id(env, otp_id)
    print(f"    OTP = {otp}")

    print("3/4 verify-otp → bearer token")
    r = requests.post(f"{api_base}/auth/verify-otp", json={"id": otp_id, "otp": str(otp)}, timeout=15)
    r.raise_for_status()
    body = r.json()
    token = body.get("tokens", {}).get("access", {}).get("token")
    if not token:
        raise RuntimeError(f"no token in verify-otp response: {body}")
    print(f"    token (truncated) = {token[:24]}...")

    print("4/4 PUT /farmers with dummy KYC payload")
    payload = {**DUMMY_KYC, "mobileNo": phone}
    r = requests.put(
        f"{api_base}/farmers",
        json=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30,
    )
    if not r.ok:
        print(f"    HTTP {r.status_code}")
        print(f"    body: {r.text[:400]}")
        raise SystemExit(1)
    body = r.json()
    print(f"    farmer created: id={body.get('id')}")
    print()
    print(f"DONE. Log in on the app with phone={phone} and any OTP fetched from")
    print("     the local http://localhost:5555/ helper — you should land on")
    print("     the real dashboard, not the KYC form.")


if __name__ == "__main__":
    main()
