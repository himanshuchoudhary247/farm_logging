#!/bin/bash
# Test the specific conversation flow

pkill -f "server-fixed.js" 2>/dev/null
pkill -f "server-simple.js" 2>/dev/null
sleep 1

cd /Users/sudhanshu/code/farmer_chat/react-loop-skills
node server-appointment-fixed.js &
sleep 2

echo "Testing the specific conversation..."
echo ""

# Create session
SESSION=$(curl -s -X POST http://localhost:3002/farmers/farmer_001/chat/session | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
echo "Session: $SESSION"
echo ""

# Test each turn
curl -s -X POST http://localhost:3002/farmers/farmer_001/chat/turn \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"$SESSION\", \"text\": \"I'd like to book an appointment\"}"
echo ""

curl -s -X POST http://localhost:3002/farmers/farmer_001/chat/turn \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"$SESSION\", \"text\": \"1122\"}"
echo ""

curl -s -X POST http://localhost:3002/farmers/farmer_001/chat/turn \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"$SESSION\", \"text\": \"not eating\"}"
echo ""

curl -s -X POST http://localhost:3002/farmers/farmer_001/chat/turn \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"$SESSION\", \"text\": \"tomorrow 5 evening\"}"
echo ""

curl -s -X POST http://localhost:3002/farmers/farmer_001/chat/turn \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"$SESSION\", \"text\": \"cool\"}"
echo ""

curl -s -X POST http://localhost:3002/farmers/farmer_001/chat/turn \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"$SESSION\", \"text\": \"yes\"}"
echo ""

curl -s -X POST http://localhost:3002/farmers/farmer_001/chat/turn \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"$SESSION\", \"text\": \"done??\"}"
echo ""

curl -s -X POST http://localhost:3002/farmers/farmer_001/chat/turn \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"$SESSION\", \"text\": \"yes\"}"
echo ""

echo "=== Test Complete ==="
