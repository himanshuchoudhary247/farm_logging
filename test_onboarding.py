"""Comprehensive accuracy test for the farmer onboarding API."""
import requests
import json
import time
import warnings
warnings.filterwarnings("ignore")

API = "https://65.0.181.84:8004/onboarding"

def call_api(text, current_field=None, existing=None, history=None):
    payload = {
        "text": text,
        "existing": existing or {"farmer": {}, "farm": {}},
        "current_field": current_field,
        "conversation_history": history
    }
    try:
        r = requests.post(API, json=payload, timeout=60, verify=False)
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def check(expected, actual, field_type="farmer"):
    data = actual.get(field_type, {})
    for k, v in expected.items():
        actual_val = data.get(k)
        if isinstance(v, int):
            if actual_val != v:
                return False, f"{k}: expected {v}, got {actual_val}"
        else:
            if str(actual_val).lower() != str(v).lower():
                return False, f"{k}: expected '{v}', got '{actual_val}'"
    return True, "OK"

results = []
accumulated_farmer = {}
accumulated_farm = {}

def test(test_id, desc, text, current_field, expected_farmer=None, expected_farm=None, history=None, use_accumulated=False):
    global accumulated_farmer, accumulated_farm
    existing = {"farmer": accumulated_farmer, "farm": accumulated_farm} if use_accumulated else {"farmer": {}, "farm": {}}
    resp = call_api(text, current_field, existing=existing, history=history)
    # Update accumulated data from response
    if not resp.get("error"):
        for k, v in resp.get("farmer", {}).items():
            if v:
                accumulated_farmer[k] = v
        for k, v in resp.get("farm", {}).items():
            if v:
                accumulated_farm[k] = v
    farmer_ok = True
    farm_ok = True
    farmer_msg = ""
    farm_msg = ""
    if expected_farmer:
        farmer_ok, farmer_msg = check(expected_farmer, resp, "farmer")
    if expected_farm:
        farm_ok, farm_msg = check(expected_farm, resp, "farm")
    passed = farmer_ok and farm_ok
    msg = farmer_msg if not farmer_ok else (farm_msg if not farm_ok else "OK")
    results.append({
        "id": test_id, "desc": desc, "input": text, "field": current_field,
        "passed": passed, "msg": msg, "response": resp
    })
    status = "PASS" if passed else "FAIL"
    print(f"{status} {test_id}: {desc}")
    if not passed:
        print(f"   {msg}")

# CATEGORY 1: SINGLE WORD ANSWERS
print("\n=== CATEGORY 1: SINGLE WORD ANSWERS ===")
test("1.1", "Name (single word)", "Himanshu", "name", {"name": "Himanshu"})
test("1.2", "Name (single word 2)", "Ramu", "name", {"name": "Ramu"})
test("1.3", "City (single word)", "Bangalore", "city", {"city": "Bangalore"})
test("1.4", "City (single word 2)", "Mysore", "city", {"city": "Mysore"})
test("1.5", "Phone (digits)", "9876543210", "phone", {"phone": "9876543210"})
test("1.6", "Sheep count", "200", "sheepCount", None, {"sheepCount": 200})
test("1.7", "Goat count", "50", "goatCount", None, {"goatCount": 50})
test("1.8", "State", "Karnataka", "state", {"state": "Karnataka"})
test("1.9", "Pincode", "560001", "pincode", {"pincode": "560001"})
test("1.10", "Gender", "male", "gender", {"gender": "male"})
test("1.11", "Aadhar", "123456789012", "aadharNo", {"aadharNo": "123456789012"})
test("1.12", "Farm name", "Green Valley Farm", "farmName", None, {"farmName": "Green Valley Farm"})

# CATEGORY 2: CONVERSATIONAL PHRASES
print("\n=== CATEGORY 2: CONVERSATIONAL PHRASES ===")
test("2.1", "'My name is X'", "My name is Ramu", "name", {"name": "Ramu"})
test("2.2", "'I am X'", "I am Himanshu", "name", {"name": "Himanshu"})
test("2.3", "'I live in X'", "I live in Bangalore", "city", {"city": "Bangalore"})
test("2.4", "'My number is X'", "My number is 9876543210", "phone", {"phone": "9876543210"})
test("2.5", "'I told you X'", "I told you Himanshu", "name", {"name": "Himanshu"})
test("2.6", "'already said X'", "already said Ramu", "name", {"name": "Ramu"})
test("2.7", "'I have X sheep'", "I have 300 sheep", "sheepCount", None, {"sheepCount": 300})
test("2.8", "'I'm from X'", "I'm from Chennai", "city", {"city": "Chennai"})

# CATEGORY 3: MULTI-FIELD EXTRACTION
print("\n=== CATEGORY 3: MULTI-FIELD EXTRACTION ===")
test("3.1", "Name + City + Sheep + Goat",
     "I am Ramu from Bangalore with 200 sheep and 50 goats", "city",
     {"name": "Ramu", "city": "Bangalore"}, {"sheepCount": 200, "goatCount": 50})
test("3.2", "Name + Phone + City",
     "My name is Suresh, phone 9988776655, from Hyderabad", "name",
     {"name": "Suresh", "phone": "9988776655", "city": "Hyderabad"})
test("3.3", "Sheep + Goat only",
     "200 sheep and 100 goats on my farm", "sheepCount", None,
     {"sheepCount": 200, "goatCount": 100})

# CATEGORY 4: HINDI PATTERNS
print("\n=== CATEGORY 4: HINDI PATTERNS ===")
test("4.1", "'mera naam X hai'", "mera naam Ramu hai", "name", {"name": "Ramu"})
test("4.2", "'mai X mein rehta hoon'", "Mai Bangalore mein rehta hoon", "city", {"city": "Bangalore"})
test("4.3", "'X bhed hai'", "Mere paas 200 bhed hai", "sheepCount", None, {"sheepCount": 200})
test("4.4", "'X bakri hai'", "50 bakri hai", "goatCount", None, {"goatCount": 50})
test("4.5", "'mera phone X hai'", "Mera phone 9876543210 hai", "phone", {"phone": "9876543210"})

# CATEGORY 5: MULTI-TURN CONVERSATION FLOW
print("\n=== CATEGORY 5: MULTI-TURN CONVERSATION FLOW ===")
accumulated_farmer = {}
accumulated_farm = {}
test("5.1", "Turn 1: Name", "Himanshu", "name", {"name": "Himanshu"}, use_accumulated=True)
time.sleep(0.5)
test("5.2", "Turn 2: Phone", "9876543210", "phone",
     {"name": "Himanshu", "phone": "9876543210"}, None,
     [{"role": "assistant", "content": "What is your name?"}, {"role": "user", "content": "Himanshu"}],
     use_accumulated=True)
time.sleep(0.5)
test("5.3", "Turn 3: City", "Bangalore", "city",
     {"name": "Himanshu", "phone": "9876543210", "city": "Bangalore"}, None,
     [{"role": "assistant", "content": "What is your name?"}, {"role": "user", "content": "Himanshu"},
      {"role": "assistant", "content": "What is your phone number?"}, {"role": "user", "content": "9876543210"}],
     use_accumulated=True)
time.sleep(0.5)
test("5.4", "Turn 4: Sheep", "200", "sheepCount",
     {"name": "Himanshu", "phone": "9876543210", "city": "Bangalore"}, {"sheepCount": 200},
     [{"role": "assistant", "content": "What is your name?"}, {"role": "user", "content": "Himanshu"},
      {"role": "assistant", "content": "What is your phone number?"}, {"role": "user", "content": "9876543210"},
      {"role": "assistant", "content": "Which city?"}, {"role": "user", "content": "Bangalore"}],
     use_accumulated=True)

# CATEGORY 6: EDGE CASES
print("\n=== CATEGORY 6: EDGE CASES ===")
accumulated_farmer = {}
accumulated_farm = {}
test("6.1", "Greeting (no info)", "hello", "name", {})
test("6.2", "Non-answer", "I don't know", "name", {})
test("6.3", "'about 200'", "about 200", "sheepCount", None, {"sheepCount": 200})
test("6.4", "'two hundred'", "two hundred", "sheepCount", None, {"sheepCount": 200})

# RESULTS SUMMARY
print("\n" + "=" * 60)
print("RESULTS SUMMARY")
print("=" * 60)

total = len(results)
passed = sum(1 for r in results if r["passed"])
failed = total - passed
accuracy = (passed / total * 100) if total > 0 else 0

print(f"\nTotal tests: {total}")
print(f"Passed: {passed}")
print(f"Failed: {failed}")
print(f"Accuracy: {accuracy:.1f}%")

categories = {}
for r in results:
    cat = r["id"].split(".")[0]
    if cat not in categories:
        categories[cat] = {"total": 0, "passed": 0}
    categories[cat]["total"] += 1
    if r["passed"]:
        categories[cat]["passed"] += 1

cat_names = {"1": "Single Word", "2": "Conversational", "3": "Multi-Field", "4": "Hindi", "5": "Multi-Turn", "6": "Edge Cases"}
print("\nPer-Category Accuracy:")
for cat, data in sorted(categories.items()):
    acc = data["passed"] / data["total"] * 100 if data["total"] > 0 else 0
    name = cat_names.get(cat, cat)
    print(f"  {name}: {data['passed']}/{data['total']} ({acc:.0f}%)")

if failed > 0:
    print("\nFailed Tests Detail:")
    for r in results:
        if not r["passed"]:
            print(f"  {r['id']}: {r['desc']}")
            print(f"    Input: '{r['input']}' | Field: {r['field']}")
            print(f"    Issue: {r['msg']}")
