"""
Stress test: 100 simulated onboarding conversations with batched multi-field turns.
Covers all 5 languages (en/hi/kn/te/mix) with realistic multi-field utterances.
"""

import json
import os
import random
import statistics
import sys
import time
import traceback
from datetime import datetime
from typing import Any, Optional

import requests

API_URL = os.environ.get("ONBOARDING_API_URL", "http://localhost:8004")

FIRST_NAMES = {
    "en": ["Ramesh", "Suresh", "Dinesh", "Mahesh", "Ganesh", "Amit", "Vijay", "Rajesh", "Deepak", "Sunil"],
    "hi": ["रमेश", "सुरेश", "दीनेश", "महेश", "गणेश", "अमित", "विजय", "राजेश", "दीपक", "सुनील"],
    "kn": ["ರಮೇಶ್", "ಸುರೇಶ್", "ದಿನೇಶ್", "ಮಹೇಶ್", "ಗಣೇಶ್"],
    "te": ["రమేశ్", "సురేశ్", "దినేశ్", "మహేశ్", "గణేశ్"],
}

LAST_NAMES = ["Kumar", "Sharma", "Patel", "Singh", "Verma", "Reddy", "Naidu", "Yadav", "Gupta", "Joshi"]

CITIES = {
    "en": ["Jaipur", "Delhi", "Mumbai", "Bangalore", "Hyderabad", "Pune", "Ahmedabad", "Lucknow", "Chennai", "Indore"],
    "hi": ["जयपुर", "दिल्ली", "मुंबई", "बंगलौर", "हैदराबाद", "पुणे"],
    "kn": ["ಜೈಪುರ", "ಬೆಂಗಳೂರು", "ಮೈಸೂರು", "ಹುಬ್ಬಳ್ಳಿ", "ಮಂಗಳೂರು"],
    "te": ["జైపూర్", "హైదరాబాద్", "విశాఖపట్నం", "విజయవాడ", "గుంటూరు"],
}

STATES = ["Rajasthan", "Delhi", "Maharashtra", "Karnataka", "Telangana", "Uttar Pradesh", "Gujarat", "Tamil Nadu", "Madhya Pradesh", "Punjab"]
GENDERS = ["male", "female"]
EDUCATION_LEVELS = ["10th", "12th", "Graduate", "Post Graduate", "Diploma", "Illiterate"]
OCCUPATIONS = ["Farmer", "Laborer", "Business", "Teacher", "Driver", "Government Job"]
RELIGIONS = ["Hindu", "Muslim", "Sikh", "Christian", "Jain"]
CASTE_CATEGORIES = ["General", "OBC", "SC", "ST"]
FARM_NAMES = ["Green Farm", "Laxmi Dairy", "Shiv Agro", "Ganga Farm", "Krishna Farm", "Om Sai Farm", "Durga Poultry", "Radhey Dairy"]
DISTRICTS = ["Jaipur", "Ajmer", "Jodhpur", "Udaipur", "Kota", "Bikaner", "Alwar", "Bharatpur"]

LANGUAGES = ["en", "hi", "kn", "te", "mix"]

FARMER_FIELD_NAMES = {"name", "fatherOrSpouseName", "gender", "dob", "phone", "alternateMobile", "email", "address_1", "city", "state", "pincode", "aadharNo", "hasPanCard", "panNo", "education", "occupation", "religion", "caste", "farmingExperience", "landHolding"}
FARM_FIELD_NAMES = {"farmName", "farmPhone", "address", "farmCity", "district", "farmState", "farmPincode", "totalAnimalCapacity", "sheepCount", "goatCount"}


class SimulatedFarmer:
    def __init__(self):
        lang = random.choice(LANGUAGES)
        ld = lang if lang in FIRST_NAMES else "en"
        first = random.choice(FIRST_NAMES[ld])
        last = random.choice(LAST_NAMES)
        name = f"{first} {last}" if lang == "en" else first
        city_en = random.choice(CITIES["en"])
        self.lang = lang
        self.ground_truth = {
            "name": name,
            "fatherOrSpouseName": f"{random.choice(FIRST_NAMES['en'])} {last}",
            "gender": random.choice(GENDERS),
            "dob": f"{random.randint(1960, 2000)}-{random.randint(1,12):02d}-{random.randint(1,28):02d}",
            "phone": f"{random.randint(7000000000, 9999999999)}",
            "alternateMobile": "",
            "email": f"farmer{random.randint(100,999)}@test.in",
            "address_1": f"{random.randint(1,999)}, {random.choice(['Main Road', 'Gandhi Nagar', 'Shastri Colony', 'Railway Station Rd'])}",
            "city": city_en,
            "state": random.choice(STATES),
            "pincode": f"{random.randint(100000, 999999)}",
            "aadharNo": f"{random.randint(100000000000, 999999999999)}",
            "hasPanCard": random.choice(["yes", "no"]),
            "panNo": "",
            "education": random.choice(EDUCATION_LEVELS),
            "occupation": random.choice(OCCUPATIONS),
            "religion": random.choice(RELIGIONS),
            "caste": random.choice(CASTE_CATEGORIES),
            "farmingExperience": str(random.randint(1, 40)),
            "landHolding": random.randint(1, 50),
        }
        self.farm_truth = {
            "farmName": random.choice(FARM_NAMES),
            "farmPhone": f"{random.randint(7000000000, 9999999999)}",
            "address": f"{random.randint(1,999)}, {random.choice(['Farm Road', 'Village Rd', 'Agri Colony'])}",
            "farmCity": random.choice(CITIES["en"]),
            "district": random.choice(DISTRICTS),
            "farmState": random.choice(STATES),
            "farmPincode": f"{random.randint(100000, 999999)}",
            "totalAnimalCapacity": random.randint(10, 200),
            "sheepCount": random.randint(0, 50),
            "goatCount": random.randint(0, 50),
        }
        if self.ground_truth["hasPanCard"] == "yes":
            self.ground_truth["panNo"] = f"{random.choice('ABCDEFGH')}{random.choice('ABCDEFGH')}{random.choice('ABCDEFGH')}{random.choice('ABCDEFGH')}{random.randint(1000,9999)}{random.choice('ABCDEFGH')}"

    def batched_utterances(self) -> list[str]:
        """Return 5 batched utterances with explicit section context."""
        gt = self.ground_truth
        ft = self.farm_truth
        pan_txt = f" My PAN is {gt['panNo']}." if gt.get('panNo') else " I do not have a PAN card."
        rel_txt = f" I follow {gt['religion']}." if random.random() < 0.6 else ""
        caste_txt = f" I belong to {gt['caste']} category." if random.random() < 0.4 else ""

        return [
            # Farmer personal details — explicitly "my" context
            f"My name is {gt['name']}. My father's name is {gt['fatherOrSpouseName']}. "
            f"My personal address is {gt['address_1']}. I live in {gt['city']} city, {gt['state']}, pincode {gt['pincode']}.",

            # Farmer contact & ID — more "my" context
            f"My phone number is {gt['phone']}. My email address is {gt['email']}. "
            f"I am {gt['gender']}, my date of birth is {gt['dob']}. My Aadhar number is {gt['aadharNo']}.{pan_txt}",

            # Farmer background
            f"I studied {gt['education']} and I work as a {gt['occupation']}.{rel_txt}{caste_txt} "
            f"I have {gt['farmingExperience']} years of farming experience and {gt['landHolding']} acres of land.",

            # Farm details — explicitly "farm" context
            f"My farm name is {ft['farmName']}. The farm address is {ft['address']}. Farm city is {ft['farmCity']}, "
            f"{ft['district']} district, {ft['farmState']}, pincode {ft['farmPincode']}. Farm phone number is {ft['farmPhone']}.",

            # Farm livestock
            f"My farm can hold {ft['totalAnimalCapacity']} animals. Currently I have {ft['sheepCount']} sheep and {ft['goatCount']} goats.",
        ]

    def all_expected(self) -> dict:
        d = {}
        for k, v in self.ground_truth.items():
            if v not in (None, "", 0, "0"):
                d[k] = v
        for k, v in self.farm_truth.items():
            if v not in (None, "", 0, "0"):
                d[k] = v
        return d


def run_conversation_batched(farmer: SimulatedFarmer) -> dict:
    """Simulate a full onboarding with 5 batched turns."""
    state = {"farmer": {}, "farm": {}}
    utterances = farmer.batched_utterances()

    for text in utterances:
        body = {"text": text, "existing": state, "language": farmer.lang}
        try:
            resp = requests.post(f"{API_URL}/onboarding", json=body, timeout=30)
            data = resp.json()
        except Exception:
            data = {"farmer": {}, "farm": {}}

        for section in ("farmer", "farm"):
            for k, v in data.get(section, {}).items():
                if v not in (None, "", 0, "0"):
                    state[section][k] = v

    return state


# ── Analysis ───────────────────────────────────────────────────

def analyze(conversations: list[dict], farmers: list[SimulatedFarmer]) -> dict:
    results = {
        "total": len(conversations),
        "passed": 0,
        "failed": 0,
        "errors": [],
        "field_accuracy": {},
        "field_coverage": {},
        "language_stats": {},
        "latency_ms": [],
    }

    for i, (final, farmer) in enumerate(zip(conversations, farmers)):
        lang = farmer.lang
        gt = farmer.ground_truth
        ft = farmer.farm_truth
        merged = {}
        merged.update(final.get("farmer", {}))
        merged.update(final.get("farm", {}))

        results["language_stats"].setdefault(lang, {"count": 0, "passed": 0})
        results["language_stats"][lang]["count"] += 1

        conv_errors = []

        for field, expected in list(gt.items()) + list(ft.items()):
            if expected in (None, "", 0, "0"):
                continue
            actual = merged.get(field)
            expected_str = str(expected)
            actual_str = str(actual) if actual is not None else ""

            if field in ("hasPanCard", "panNo") and gt.get("hasPanCard") == "no":
                continue

            results["field_accuracy"].setdefault(field, {"correct": 0, "total": 0})
            results["field_accuracy"][field]["total"] += 1

            if actual_str == expected_str:
                results["field_accuracy"][field]["correct"] += 1
            else:
                conv_errors.append(f"  Field '{field}': expected='{expected_str}' got='{actual_str}'")

        if conv_errors:
            results["failed"] += 1
            results["errors"].append({"index": i, "lang": lang, "errors": conv_errors})
        else:
            results["passed"] += 1
            results["language_stats"][lang]["passed"] += 1

    # Coverage
    all_merged = []
    for final, _ in zip(conversations, farmers):
        m = {}
        m.update(final.get("farmer", {}))
        m.update(final.get("farm", {}))
        all_merged.append(m)

    for field in sorted(set(list(FARMER_FIELD_NAMES) + list(FARM_FIELD_NAMES))):
        filled = sum(1 for m in all_merged if m.get(field) not in (None, "", 0, "0"))
        results["field_coverage"][field] = filled

    return results


# ── Main ───────────────────────────────────────────────────────

def main(count: int = 100):
    print(f"\n{'='*60}")
    print(f"  STRESS TEST: {count} Onboarding Conversations (batched)")
    print(f"  API: {API_URL}")
    print(f"{'='*60}\n")

    try:
        h = requests.get(f"{API_URL}/onboarding/health", timeout=5)
        assert h.status_code == 200
        print(f"  ✓ API healthy ({h.json()['status']})\n")
    except Exception as e:
        print(f"  ✗ API unreachable: {e}")
        sys.exit(1)

    farmers: list[SimulatedFarmer] = []
    conversations: list[dict] = []
    latencies = []

    for i in range(1, count + 1):
        farmer = SimulatedFarmer()
        farmers.append(farmer)

        t0 = time.time()
        try:
            final = run_conversation_batched(farmer)
        except Exception as e:
            print(f"  [{i:3d}/{count}] ✗ CRASH: {e}")
            traceback.print_exc()
            final = {"farmer": {}, "farm": {}}
        elapsed = (time.time() - t0) * 1000
        latencies.append(elapsed)

        conversations.append(final)
        lang_flag = farmer.lang.upper()
        name = farmer.ground_truth["name"][:15]
        filled = sum(1 for v in final.get("farmer", {}).values() if v not in (None, "", 0, "0")) + sum(1 for v in final.get("farm", {}).values() if v not in (None, "", 0, "0"))
        total_fields = len(FARMER_FIELD_NAMES | FARM_FIELD_NAMES)

        print(f"  [{i:3d}/{count}] {lang_flag:4s} {name:15s} {filled:2d}/{total_fields:2d} fields  {elapsed:6.0f}ms")

    # ── Analysis ────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("  ANALYSIS")
    print(f"{'='*60}\n")

    results = analyze(conversations, farmers)

    print(f"  Total:  {results['total']}")
    print(f"  Passed: {results['passed']}")
    print(f"  Failed: {results['failed']}")
    pass_pct = results['passed'] / max(results['total'], 1) * 100
    print(f"  Rate:   {pass_pct:.1f}%\n")

    if results["errors"]:
        print("  --- Sample Errors (first 10) ---")
        for err in results["errors"][:10]:
            print(f"  [{err['index']}] lang={err['lang']}")
            for e in err["errors"][:5]:
                print(f"    {e}")
        print()

    print("  --- Field Accuracy ---")
    accuracies = []
    for fld in sorted(results["field_accuracy"].keys()):
        s = results["field_accuracy"][fld]
        pct = s["correct"] / max(s["total"], 1) * 100
        accuracies.append((fld, pct))
        bar = "▓" * int(pct / 5) + "░" * (20 - int(pct / 5))
        print(f"    {fld:25s} {bar} {pct:5.1f}% ({s['correct']}/{s['total']})")

    overall_acc = statistics.mean([a[1] for a in accuracies]) if accuracies else 0
    print(f"\n    {'OVERALL':25s} {'─'*22} {overall_acc:5.1f}%\n")

    print(f"  --- Field Coverage (filled across {count} convos) ---")
    for fld in sorted(results["field_coverage"].keys()):
        c = results["field_coverage"][fld]
        bar = "▓" * int(c / max(count, 1) * 50) + "░" * (50 - int(c / max(count, 1) * 50))
        print(f"    {fld:25s} {bar} {c:4d}/{count}")

    print("\n  --- Language Stats ---")
    for lang in sorted(results["language_stats"].keys()):
        s = results["language_stats"][lang]
        rate = s["passed"] / max(s["count"], 1) * 100
        print(f"    {lang:4s}: {s['count']:3d} conversations, {s['passed']:3d} passed ({rate:.0f}%)")

    print(f"\n  --- Latency ---")
    if latencies:
        print(f"    Mean:   {statistics.mean(latencies):.0f}ms")
        print(f"    Median: {statistics.median(latencies):.0f}ms")
        print(f"    P95:    {sorted(latencies)[int(len(latencies)*0.95)]:.0f}ms")
        print(f"    Max:    {max(latencies):.0f}ms")

    # Save report
    report = {
        "timestamp": datetime.utcnow().isoformat(),
        "total": results["total"],
        "passed": results["passed"],
        "failed": results["failed"],
        "pass_rate_pct": round(pass_pct, 1),
        "overall_field_accuracy_pct": round(overall_acc, 1),
        "field_accuracy": {f: round(v["correct"] / max(v["total"], 1) * 100, 1) for f, v in results["field_accuracy"].items()},
        "field_coverage": results["field_coverage"],
        "language_stats": results["language_stats"],
        "latency_ms": {
            "mean": round(statistics.mean(latencies), 0) if latencies else 0,
            "median": round(statistics.median(latencies), 0) if latencies else 0,
            "p95": round(sorted(latencies)[int(len(latencies)*0.95)], 0) if latencies else 0,
            "max": round(max(latencies), 0) if latencies else 0,
        },
        "errors": results["errors"][:20],
    }

    report_path = "onboarding_stress_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n  📄 Report saved: {report_path}")

    return results["failed"] == 0


if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    ok = main(count)
    sys.exit(0 if ok else 1)
