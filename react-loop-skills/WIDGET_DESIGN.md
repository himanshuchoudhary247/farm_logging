# Widget-Based Interaction Design

## Overview

Replace open-ended text inputs with widget-based selections and progressive verification for better UX.

---

## Flow 1: Animal Selection with Widget

### Current Flow
```
Bot: What is the animal name or tag?
User: 1122
Bot: What is the issue?
```

### Enhanced Flow with Widget
```
Bot: Select your animal:
[Widget Options]
┌─────────────────────────────────────┐
│ 🐄 Gauri (COW001)     [Button]      │
│ 🐃 Lakshmi (BUF001)   [Button]      │
│ 🐐 Moti (GOAT001)     [Button]      │
│ 🔍 Search by tag...   [Button]      │
│ ✏️ Other (type name)  [Button]      │
└─────────────────────────────────────┘
```

**User clicks "Other":**
```
Bot: Please type the animal name or tag:
[Text Input]
User: 5555
```

**Progressive Verification:**
```
Bot: I found these animals matching "5555":
┌─────────────────────────────────────┐
│ 🐄 5555-Brown-Cow   [Select]        │
│ 🐃 5555-White-Buffalo [Select]       │
│ ✏️ None of these    [Type Again]    │
└─────────────────────────────────────┘
```

---

## Flow 2: Issue Selection with Widget

### Widget Display
```
Bot: What's the issue?
┌─────────────────────────────────────┐
│ 🏥 Select Common Issues:            │
│                                     │
│ [Not Eating] [Fever] [Cough]         │
│ [Diarrhea] [Limping] [Injury]      │
│ [Breathing Issue] [Skin Problem]   │
│                                     │
│ ✏️ [Describe Other Issue...]        │
└─────────────────────────────────────┘
```

**If user clicks "Describe Other Issue":**
```
Bot: Please describe the issue:
[Text Input with placeholder: "e.g., swollen leg, eye infection"]
```

---

## Flow 3: Symptoms Selection (Multi-Select)

```
Bot: What symptoms do you observe?
┌─────────────────────────────────────┐
│ Select all that apply:              │
│                                     │
│ [✓] Loss of appetite                │
│ [ ] Weight loss                     │
│ [✓] Lethargy (low energy)           │
│ [ ] Fever                           │
│ [ ] Vomiting                        │
│ [ ] Nasal discharge                 │
│                                     │
│ ✏️ [Describe other symptoms...]     │
└─────────────────────────────────────┘

User selects: Loss of appetite, Lethargy

Bot: Any other symptoms? or [Continue] if done
```

---

## Flow 4: Date & Time Selection Widget

### Date Widget
```
Bot: Select appointment date:
┌─────────────────────────────────────┐
│ 📅 Quick Options:                   │
│                                     │
│ [Today] [Tomorrow]                  │
│                                     │
│ Or pick a date:                     │
│ [Sun 19] [Mon 20] [Tue 21]        │
│ [Wed 22] [Thu 23] [Fri 24]        │
│ [Sat 25] [Sun 26] [Mon 27]        │
│                                     │
│ [📅 Pick custom date...]           │
└─────────────────────────────────────┘
```

### Time Widget
```
Bot: Select time:
┌─────────────────────────────────────┐
│ 🕐 Morning (9AM - 12PM)            │
│ [9:00] [9:30] [10:00] [10:30]     │
│ [11:00] [11:30] [12:00]             │
│                                     │
│ 🕐 Afternoon (12PM - 5PM)           │
│ [12:30] [1:00] [1:30] [2:00]       │
│ [2:30] [3:00] [3:30] [4:00]        │
│ [4:30] [5:00]                       │
│                                     │
│ 🕐 Evening (5PM - 8PM)              │
│ [5:30] [6:00] [6:30] [7:00]        │
│                                     │
│ ✏️ [Custom time...]                 │
└─────────────────────────────────────┘
```

---

## Flow 5: Progressive Confirmation

**After EACH field, confirm immediately:**

```
Bot: ✓ Animal selected: Gauri (COW001)
     Is this correct?

┌─────────────────────────────────────┐
│ [Yes ✓] [No, change animal ✗]     │
└─────────────────────────────────────┘

If "No":
Bot: Let's select the animal again...
[Show animal widget again]
```

**Summary Confirmation (After all fields):**
```
Bot: Here's your appointment summary:
┌─────────────────────────────────────┐
│ 📋 APPOINTMENT DETAILS              │
│ ━━━━━━━━━━━━━━━━━━━━━━━            │
│ Animal:    Gauri (COW001) ✓        │
│ Issue:     Not eating     ✓        │
│ Symptoms:  Loss of appetite,       │
│            Lethargy        ✓        │
│ Date:      Tomorrow, Sep 20 ✓      │
│ Time:      10:00 AM       ✓        │
│                                     │
│ [Edit ✏️]          [Submit ✅]      │
└─────────────────────────────────────┘
```

---

## Implementation Structure

### Widget Response Format
```json
{
  "agent": "appointment_booking",
  "reply_text": "Select your animal:",
  "reply_type": "widget",
  "widget": {
    "type": "single_select",
    "title": "Select Animal",
    "options": [
      {"id": "animal_001", "label": "🐄 Gauri", "value": "COW001", "type": "button"},
      {"id": "animal_002", "label": "🐃 Lakshmi", "value": "BUF001", "type": "button"},
      {"id": "animal_003", "label": "🐐 Moti", "value": "GOAT001", "type": "button"},
      {"id": "search", "label": "🔍 Search by tag", "value": "search", "type": "action"},
      {"id": "other", "label": "✏️ Other", "value": "other", "type": "text_input"}
    ]
  },
  "_meta": {
    "field": "animal_identifier",
    "required_follow_up": true,
    "widget_type": "single_select"
  }
}
```

### Text Input Widget
```json
{
  "reply_text": "Please type the animal tag:",
  "reply_type": "text_input",
  "widget": {
    "type": "text_input",
    "placeholder": "e.g., COW001, 1122",
    "validation": {
      "pattern": "^[A-Za-z0-9]+$",
      "min_length": 2,
      "max_length": 20
    }
  }
}
```

### Multi-Select Widget
```json
{
  "reply_text": "Select symptoms (choose all that apply):",
  "reply_type": "widget",
  "widget": {
    "type": "multi_select",
    "title": "Symptoms",
    "min_selections": 1,
    "max_selections": 5,
    "options": [
      {"id": "symptom_1", "label": "Loss of appetite", "value": "not_eating"},
      {"id": "symptom_2", "label": "Lethargy", "value": "low_energy"},
      {"id": "symptom_3", "label": "Fever", "value": "fever"},
      {"id": "symptom_4", "label": "Other", "value": "other", "type": "text_input"}
    ],
    "continue_button": "Continue"
  }
}
```

---

## State Machine

```
[START]
  ↓
[Show Animal Widget]
  ↓ (user selects or types)
[Verify Animal]
  ← (if wrong, go back)
  ↓ (if correct)
[Show Issue Widget]
  ↓
[Verify Issue]
  ← (if wrong, go back)
  ↓
[Show Symptoms Widget]
  ↓
[Verify Symptoms]
  ← (if wrong, go back)
  ↓
[Show Date Widget]
  ↓
[Show Time Widget]
  ↓
[Show Summary with Edit/Submit]
  ↓ (user clicks Submit)
[Save Appointment]
  ↓
[Show Success + Book Another?]
```

---

## Fuzzy Matching for "Other" Input

When user types in "Other":

1. **Search database:**
   - Tag numbers containing input
   - Names similar to input
   - Recently accessed animals

2. **Show top 3 matches:**
```
Bot: Did you mean one of these?
┌─────────────────────────────────────┐
│ Matching "555":                     │
│                                     │
│ 🐄 555-Cow-1        [Select]        │
│ 🐃 555-Buffalo-2    [Select]        │
│ 🐐 555-Goat-3       [Select]        │
│                                     │
│ ✏️ None of these    [Type Again]   │
└─────────────────────────────────────┘
```

---

## Benefits

1. **Faster Input** - Click vs type
2. **No Typos** - Predefined options
3. **Progressive Validation** - Confirm each field
4. **Discoverability** - Shows available options
5. **Accessibility** - Buttons easier than typing
6. **Mobile Friendly** - Touch-optimized
