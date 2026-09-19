# React Loop Skills - Local Access

## 🌐 Localhost URLs

Your React Loop Skills server is running at:

### **Main Server (Port 3001)**
```
http://localhost:3001
```

**Endpoints:**
- `http://localhost:3001/health` - Health check
- `http://localhost:3001/skills` - List all skills
- `http://localhost:3001/farmers/farmer_001` - Get farmer data
- `http://localhost:3001/farmers/farmer_001/animals` - Get animals
- `http://localhost:3001/farmers/farmer_001/appointments` - Get appointments
- `POST http://localhost:3001/farmers/farmer_001/chat/session` - Create session
- `POST http://localhost:3001/farmers/farmer_001/chat/turn` - Send message

### **Appointment Server (Port 3002)**
```
http://localhost:3002
```

For testing appointment booking with slot filling.

---

## 🔗 Quick Access Links

Open these in your browser:

**Health Check:**
```
http://localhost:3001/health
```

**List Skills:**
```
http://localhost:3001/skills
```

**Farmer Data:**
```
http://localhost:3001/farmers/farmer_001
```

---

## 📱 Testing from Browser

### Method 1: Direct API Test
Open browser and go to:
```
http://localhost:3001/health
```

You should see:
```json
{"status":"ok","timestamp":"2026-09-19T..."}
```

### Method 2: Interactive Web Interface
Unfortunately, there's no built-in web UI. Use the CLI tools instead:

```bash
# In Terminal 1: Start server
cd /Users/sudhanshu/code/farmer_chat/react-loop-skills
node server-fixed.js

# In Terminal 2: Run CLI
node cli-simple.js
```

---

## 🌐 Exposing to Internet (Optional)

If you want to share this with others outside your machine, use **ngrok**:

### Install ngrok
```bash
# macOS
brew install ngrok

# Or download from https://ngrok.com/download
```

### Start Tunnel
```bash
# Terminal 1: Make sure server is running
node server-fixed.js

# Terminal 2: Create tunnel
ngrok http 3001
```

You'll get a public URL like:
```
https://abc123.ngrok.io
```

Share this link! It forwards to your localhost:3001

---

## 📋 Copy-Paste Commands

### Start Everything
```bash
cd /Users/sudhanshu/code/farmer_chat/react-loop-skills

# Start server in background
nohup node server-fixed.js > server.log 2>&1 &

# Quick test
./test-quick.sh

# Or run CLI
node cli-batch.js
```

### Check Server Status
```bash
curl http://localhost:3001/health
curl http://localhost:3001/skills
```

### Create Session & Chat
```bash
# Create session
SESSION=$(curl -s -X POST http://localhost:3001/farmers/farmer_001/chat/session | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
echo "Session: $SESSION"

# Send message
curl -X POST http://localhost:3001/farmers/farmer_001/chat/turn \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"$SESSION\", \"text\": \"How many animals do I have?\"}"
```

---

## 🔍 Access Summary

| Service | URL | Port | Status |
|---------|-----|------|--------|
| Main Server | http://localhost:3001 | 3001 | ✅ Running |
| Appointment Server | http://localhost:3002 | 3002 | ⚠️ Optional |
| Health Check | http://localhost:3001/health | - | ✅ Active |
| Skills API | http://localhost:3001/skills | - | ✅ Active |
| Chat API | http://localhost:3001/farmers/:id/chat/turn | - | ✅ Active |

---

## 🚀 Quick Start

**Step 1:** Start server (if not already running)
```bash
cd /Users/sudhanshu/code/farmer_chat/react-loop-skills
node server-fixed.js
```

**Step 2:** Open browser or run tests
```bash
# Browser: http://localhost:3001/health
# OR
./test-quick.sh
# OR
node cli-batch.js
```

---

**Current Status:** Server is running on port 3001
