# React Loop Skills - Testing Guide

## 🚀 Quick Start

### 1. Start the Server

```bash
cd react-loop-skills
node server-fixed.js
```

Server will start on **http://localhost:3001**

### 2. Run Quick Tests

```bash
# Run automated quick tests
./test-quick.sh

# Or manually test with curl
curl http://localhost:3001/health
curl http://localhost:3001/skills
```

## 🧪 Testing Options

### Option 1: Quick Test Script (Recommended)
```bash
./test-quick.sh
```
Runs 4 basic tests:
- ✅ Health check
- ✅ List skills
- ✅ Farm QA query
- ✅ Weather with bare reply

### Option 2: Batch Mode (Non-Interactive)
```bash
# Use default test messages
node cli-batch.js

# Pipe your own messages
echo -e "hello\nwhat is the weather?\nDelhi" | node cli-batch.js
```

**Example Output:**
```
🤖 React Loop Skills - Batch Mode
============================================================
Session: sess_xxx

You: hello
🤖 I'm not sure what you're asking about...
   [ confidence: 0% ]

You: what is the weather?
🤖 Which location would you like the weather for?
   [ confidence: 75% | skill: weather ]

You: Delhi
🤖 Currently in Delhi: Sunny, 32°C, humidity 45%.
   [ confidence: 95% | skill: weather | bare reply ]
```

### Option 3: Interactive CLI

**Simple Version:**
```bash
node cli-simple.js
```
Then type messages interactively.

**Full Featured Version:**
```bash
node cli-agent.js
```
Supports commands:
- `/help` - Show help
- `/context` - Show current context
- `/history` - Show conversation history
- `/clear` - Clear screen
- `/test weather` - Run test scenarios
- `/quit` - Exit

### Option 4: Specific Conversation Test
```bash
node test-conversation.js
```
Tests the exact conversation flow from your requirements:
- "I'd like to book an appointment"
- "1122"
- "not eating"
- "tomorrow 5 evening"
- "cool"
- "yes"
- etc.

### Option 5: Comprehensive Test Suite
```bash
node test-long-conversations.js
```
Runs 6 comprehensive conversation scenarios with 52 total turns.

## 📊 Manual Testing with curl

### Health Check
```bash
curl http://localhost:3001/health
```

### List Skills
```bash
curl http://localhost:3001/skills
```

### Create Session
```bash
curl -X POST http://localhost:3001/farmers/farmer_001/chat/session
```

### Send Chat Message
```bash
# Create session first
SESSION=$(curl -s -X POST http://localhost:3001/farmers/farmer_001/chat/session | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)

# Send message
curl -X POST http://localhost:3001/farmers/farmer_001/chat/turn \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"$SESSION\", \"text\": \"How many animals do I have?\"}"
```

### Get Farmer Data
```bash
curl http://localhost:3001/farmers/farmer_001
curl http://localhost:3001/farmers/farmer_001/animals
curl http://localhost:3001/farmers/farmer_001/appointments
```

## 🎯 Test Scenarios

### Scenario 1: Weather with Fragments
```
You: What is the weather?
Bot: Which location would you like the weather for?

You: Delhi
Bot: Currently in Delhi: Sunny, 32°C...

You: and tomorrow?
Bot: Currently in Delhi: Sunny, 32°C...
   [ is_continuation: true ]
```

### Scenario 2: Farm QA
```
You: How many animals do I have?
Bot: You have 3 animals total: 1 cow, 1 buffalo, 1 goat.
   [ confidence: 100% ]

You: show my cows
Bot: You have 1 animals: 1 cow.
   [ is_continuation: true ]
```

### Scenario 3: Appointment Booking
```
You: I'd like to book an appointment
Bot: What type of appointment?

You: vet
Bot: What is the animal name or tag?

You: 1122
Bot: What is the issue?

You: not eating
Bot: What are the symptoms?

You: tomorrow 10am
Bot: Would you like to submit?

You: yes
Bot: Appointment saved successfully!
```

## 🐛 Troubleshooting

### Server not running
```bash
# Check if server is running
curl http://localhost:3001/health

# Start server
node server-fixed.js &
```

### Port already in use
```bash
# Kill existing servers
pkill -f "server-fixed.js"
pkill -f "server-simple.js"

# Start fresh
node server-fixed.js &
```

### Permission denied
```bash
chmod +x test-quick.sh
chmod +x cli-batch.js
chmod +x cli-simple.js
```

## 📁 Test Files

| File | Purpose | Usage |
|------|---------|-------|
| `test-quick.sh` | Quick automated tests | `./test-quick.sh` |
| `cli-batch.js` | Batch mode testing | `node cli-batch.js` |
| `cli-simple.js` | Interactive CLI | `node cli-simple.js` |
| `cli-agent.js` | Full-featured CLI | `node cli-agent.js` |
| `test-conversation.js` | Specific conversation | `node test-conversation.js` |
| `test-long-conversations.js` | Comprehensive suite | `node test-long-conversations.js` |

## ✅ Success Criteria

- [ ] Server starts without errors
- [ ] Health check returns `{"status": "ok"}`
- [ ] `/skills` returns 4 skills
- [ ] Farm QA query returns animal count
- [ ] Weather query asks for location
- [ ] Bare replies (1-2 words) are detected
- [ ] Context is maintained across turns
- [ ] Fragment follow-ups work correctly
