#!/usr/bin/env python3
"""
Local test for the Farmer Onboarding Service.

Runs a conversational session: starts with empty data, feeds turns,
prints progress and final JSON output.

Usage:
  python3 test_farmer_onboarding.py

Note: Requires AWS credentials with Bedrock access (uses the same
BedrockTextAdapter as the main app).
"""

from services.farmer_onboarding_service.models import OnboardingRequest
from services.farmer_onboarding_service.service import build_final_output, process_turn

# ── sample multi-turn conversations ───────────────────────────────

SCENARIOS = {
    "english_basic": [
        "My name is Ram Singh. I have a farm in Jaipur, Rajasthan.",
        "My phone number is 9876543210 and my email is ram@farm.com",
        "I have 30 goats and 15 sheep. My farm can hold 60 animals total.",
        "My Aadhar number is 1234-5678-9012. I was born on 1985-06-15.",
        "I studied up to 10th standard and have been farming for 15 years. I own 5 acres of land.",
    ],
    "hindi_mix": [
        "Mera naam Suresh Kumar hai, main Uttar Pradesh ke Lucknow district mein rehta hoon",
        "Mera phone number 9876543210 hai",
        "Mere paas 20 bakriyan aur 10 bhed hain",
        "Mera Aadhar number 2345-6789-0123 hai",
        "Maine 8th tak padhai ki hai, 10 saal se kheti kar raha hoon",
    ],
    "kannada_mix": [
        "Nanna hesaru Venkatesh. Namma farm Bengaluru district alli ide.",
        "Nanna phone number 9876543210. Namma farm alli 25 adugal mattu 10 kuri ide.",
        "Nanna Aadhar number 3456-7890-1234",
    ],
}


def run_scenario(name: str, turns: list[str]) -> None:
    print(f"\n{'='*60}")
    print(f"  SCENARIO: {name}")
    print(f"{'='*60}")

    accumulated = {"farmer": {}, "farm": {}}

    for i, text in enumerate(turns, 1):
        print(f"\n  --- Turn {i} ---")
        print(f"  👤 Farmer: {text}")

        req = OnboardingRequest(text=text, existing=accumulated, language="en")
        resp = process_turn(req)

        accumulated["farmer"] = resp.farmer
        accumulated["farm"] = resp.farm

        if resp.follow_up_question:
            print(f"  🤖 Bot: {resp.follow_up_question}")
        if resp.complete:
            print(f"  ✅ ALL FIELDS COLLECTED!")

    # Final output
    final = build_final_output(resp.farmer, resp.farm)
    farmer_count = len(final["farmer"])
    farm_count = len(final["farm"])
    print(f"\n  📦 Final JSON ({farmer_count} farmer fields + {farm_count} farm fields):")
    print(f"  Farmer: {final['farmer']}")
    print(f"  Farm:    {final['farm']}")
    print(f"  Complete: {resp.complete}")
    if resp.missing_fields:
        print(f"  ⚠️  Still missing: {resp.missing_fields}")


def main():
    print("Farmer Onboarding Service — Local Test")
    print("(requires Bedrock access via AWS credentials)\n")

    for name, turns in SCENARIOS.items():
        run_scenario(name, turns)


if __name__ == "__main__":
    main()
