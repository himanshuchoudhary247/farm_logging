# React Loop Skills - Complete Overview

## 📊 Skills Summary

| # | Skill ID | Name | Tools | Category | Activation Confidence |
|---|----------|------|-------|----------|---------------------|
| 1 | weather | Weather Service | 3 | Information | 0.6 |
| 2 | appointments | Appointment Manager | 4 | Management | 0.6 |
| 3 | market-prices | Market Prices | 3 | Information | 0.6 |
| 4 | farm-qa | Farm Q&A | 10 | Information | 0.5 |
| | **TOTAL** | | **20 tools** | | |

---

## 🌤️ 1. Weather Service (`weather`)

**Description:** Get weather information and alerts for your location  
**Category:** Information  
**Icon:** 🌤️

### Activation
- **Intents:** weather, forecast, rain, temperature, will it rain, how hot, how cold, weather report, climate
- **Keywords:** weather, rain, sunny, cloudy, storm, temperature, humidity, forecast
- **Confidence Threshold:** 0.6

### Tools (3)

| Tool | Description | Parameters | Returns |
|------|-------------|------------|---------|
| `get_current_weather` | Get current weather conditions | `location` (required), `units` (celsius/fahrenheit) | temperature, conditions, humidity, wind_speed, location, timestamp |
| `get_forecast` | Get weather forecast | `location` (required), `days` (1-7), `units` | location, forecast array with date, temp high/low, conditions, rain_chance |
| `check_weather_alerts` | Check weather warnings | `location` (required) | has_alerts, alerts array with severity, title, description, valid_until |

---

## 📅 2. Appointment Manager (`appointments`)

**Description:** Manage veterinary and agricultural appointments  
**Category:** Management  
**Icon:** 📅

### Activation
- **Intents:** appointment, schedule, book, vet, veterinary, doctor, visit, checkup
- **Keywords:** appointment, schedule, book, vet, doctor, visit, time, slot
- **Confidence Threshold:** 0.6

### Tools (4)

| Tool | Description | Parameters | Returns |
|------|-------------|------------|---------|
| `get_appointments` | Get upcoming appointments | `farmer_id` (required), `status` (pending/confirmed/completed/cancelled/all), `limit` | appointments array, count |
| `book_appointment` | Book a new appointment | `farmer_id`, `type` (veterinary/agricultural/consultation), `date`, `time` (required), `reason`, `animal_id` | appointment_id, status, message |
| `cancel_appointment` | Cancel existing appointment | `appointment_id` (required), `reason` | success, message |
| `check_availability` | Check available time slots | `type`, `date` (required), `start_time`, `end_time` | available_slots array, date |

---

## 💰 3. Market Prices (`market-prices`)

**Description:** Get current market prices for agricultural commodities  
**Category:** Information  
**Icon:** 💰

### Activation
- **Intents:** price, market, mandi, rate, cost, sell, buy, commodity
- **Keywords:** price, market, mandi, rate, cost, sell, buy, rupees, rs, ₹, quintal, kg
- **Confidence Threshold:** 0.6

### Tools (3)

| Tool | Description | Parameters | Returns |
|------|-------------|------------|---------|
| `get_market_prices` | Get current prices | `commodity` (required), `market`, `state` | commodity, market, min_price, max_price, modal_price, unit, date |
| `get_price_history` | Get historical prices | `commodity` (required), `market`, `days` | commodity, market, history array with date, price, trend |
| `compare_prices` | Compare across markets | `commodity` (required), `markets` (array) | commodity, comparisons array |

---

## 🌾 4. Farm Q&A (`farm-qa`) - NEW!

**Description:** Answer questions about farm data, animals, crops, and farmer information from the database  
**Category:** Information  
**Icon:** 🌾

### Activation
- **Intents:** farm, animal, crop, cow, buffalo, goat, sheep, field, land, farmer, my farm, my animals, my crops, show me, tell me about, what is, how many, when did, where is
- **Keywords:** farm, animal, crop, cow, buffalo, goat, sheep, field, land, farmer, health, vaccination, milk, production, area, size, count, total, my
- **Confidence Threshold:** 0.5

### Allowed Database Tables
- farmers
- animals
- animal_health
- vaccinations
- production
- farms
- crops
- fields

### Tools (10)

| Tool | Description | Parameters | Returns |
|------|-------------|------------|---------|
| `query_farmer_profile` | Get farmer profile info | `farmer_id` (required), `include_farm_summary` | farmer details, farm summary (animals count, land area, active crops) |
| `query_animals` | Query animals with filters | `farmer_id` (required), `animal_type` (cow/buffalo/goat/etc), `status`, `limit` | animals array, count, by_type breakdown |
| `query_animal_details` | Get detailed animal info | `animal_id` (required), `include_health`, `include_production`, `include_vaccinations` | animal details, health records, production data, vaccination history |
| `query_crops` | Query planted crops | `farmer_id` (required), `season` (kharif/rabi/summer), `status`, `year` | crops array, total_area, crop_count |
| `query_farm_land` | Get farm land info | `farmer_id` (required), `include_fields` | farm details, fields array with area, current crop, soil quality |
| `query_health_records` | Query health records | `farmer_id` (required), `animal_id`, `from_date`, `to_date`, `record_type`, `limit` | health records array, count, pending_followups |
| `query_production_data` | Query milk production | `farmer_id` (required), `from_date`, `to_date`, `animal_id`, `group_by` | summary (total, average, best animal), records array |
| `query_vaccination_schedule` | Get vaccination schedule | `farmer_id`, `animal_id`, `upcoming_only`, `days_ahead` | vaccinations array, upcoming_count, overdue_count |
| `ask_database` | Natural language to SQL | `question` (required), `farmer_id` (required), `context` | question, sql_query, answer, data, confidence |
| `get_summary` | Comprehensive farm summary | `farmer_id` (required), `include` (array: animals/crops/production/health/vaccinations) | farmer_name, generated_at, summary, sections |

---

## 🔌 Usage Examples

### Weather Skill
```typescript
// User asks: "What's the weather like today?"
const intent = await detectIntent("What's the weather like today?");
// → { skill: "weather", confidence: 0.92 }

await loadSkill("weather");
const result = await executeTool("get_current_weather", { location: "Delhi" });
// → { temperature: 32, conditions: "Sunny", humidity: 45 }
```

### Farm Q&A Skill
```typescript
// User asks: "How many cows do I have?"
const intent = await detectIntent("How many cows do I have?");
// → { skill: "farm-qa", confidence: 0.88 }

await loadSkill("farm-qa");
const result = await executeTool("query_animals", { 
  farmer_id: "farmer_001", 
  animal_type: "cow" 
});
// → { count: 3, animals: [...], by_type: { cow: 3 } }
```

### Natural Language Query
```typescript
// User asks: "What was my milk production last week?"
const result = await executeTool("ask_database", {
  question: "What was my milk production last week?",
  farmer_id: "farmer_001"
});
// → { 
//   sql_query: "SELECT SUM(quantity) FROM production WHERE farmer_id = 'farmer_001' AND date >= '2026-09-12'",
//   answer: "Your milk production last week was 455 liters.",
//   confidence: 0.85
// }
```

---

## 🗄️ Database Schema (Farm Q&A)

The Farm Q&A skill can query these tables:

```sql
-- Farmers
farmers (id, name, phone, email, address, village, district, state, registration_date)

-- Animals
animals (id, farmer_id, tag_number, name, type, breed, date_of_birth, gender, color, weight, health_status, acquisition_date, purchase_price)

-- Farms
farms (id, farmer_id, name, total_area, area_unit, soil_type, irrigation_type, address, coordinates)

-- Fields
fields (id, farm_id, name, area, current_crop, soil_quality)

-- Crops
crops (id, farmer_id, name, variety, field_id, area_acres, planting_date, expected_harvest, status, season, yield_expected)

-- Health Records
health_records (id, animal_id, farmer_id, date, type, symptoms, diagnosis, treatment, vet_name, follow_up_required)

-- Production
production (id, animal_id, date, quantity, unit, quality)

-- Vaccinations
vaccinations (id, animal_id, farmer_id, vaccine_name, scheduled_date, completed_date, status, next_due, vet_name)
```

---

## 🎯 Intent Matching Examples

| User Query | Detected Skill | Confidence | Matched Intent |
|------------|---------------|------------|----------------|
| "What's the weather?" | weather | 0.95 | weather |
| "Will it rain tomorrow?" | weather | 0.92 | rain |
| "Book a vet appointment" | appointments | 0.90 | appointment |
| "Show my upcoming visits" | appointments | 0.85 | visit |
| "What is the price of wheat?" | market-prices | 0.91 | price |
| "Mandi rates for rice" | market-prices | 0.88 | market |
| "How many cows do I have?" | farm-qa | 0.89 | animal |
| "Show my farm summary" | farm-qa | 0.87 | farm |
| "When was my cow vaccinated?" | farm-qa | 0.90 | vaccination |
| "My buffalo's milk production" | farm-qa | 0.86 | production |

---

## 📈 Tool Categories

### By Database Access
- **Read-Only:** weather, market-prices
- **Read + Query:** farm-qa (10 tools with DB access)
- **CRUD:** appointments (create, read, update, delete)

### By Data Type
- **Animals:** query_animals, query_animal_details, query_health_records, query_vaccination_schedule (farm-qa)
- **Crops/Land:** query_crops, query_farm_land (farm-qa)
- **Production:** query_production_data (farm-qa)
- **Finance:** get_market_prices, get_price_history, compare_prices (market-prices)
- **Scheduling:** get_appointments, book_appointment, cancel_appointment, check_availability (appointments)
- **General:** query_farmer_profile, ask_database, get_summary (farm-qa)

---

*Last updated: September 19, 2026*
