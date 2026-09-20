#!/bin/bash
# Quick test script for React Loop Skills

echo "🤖 React Loop Skills - Quick Test"
echo "=================================="
echo ""

cd /Users/sudhanshu/code/farmer_chat/react-loop-skills

# Check if server is running
if ! curl -s http://localhost:3001/health > /dev/null; then
    echo "❌ Server not running. Starting..."
    nohup node server-fixed.js > server.log 2>&1 &
    sleep 2
fi

echo "✅ Server is running"
echo ""

# Test 1: Health check
echo "Test 1: Health Check"
curl -s http://localhost:3001/health | python3 -m json.tool 2>/dev/null || curl -s http://localhost:3001/health
echo ""

# Test 2: List skills
echo "Test 2: List Skills"
curl -s http://localhost:3001/skills | python3 -m json.tool 2>/dev/null || curl -s http://localhost:3001/skills
echo ""

# Test 3: Chat - Farm QA
echo "Test 3: Chat - Farm QA"
SESSION=$(curl -s -X POST http://localhost:3001/farmers/farmer_001/chat/session | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
echo "Session: $SESSION"

echo "  User: 'How many animals do I have?'"
curl -s -X POST http://localhost:3001/farmers/farmer_001/chat/turn \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"$SESSION\", \"text\": \"How many animals do I have?\"}" | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print(f\"  Bot: {d['reply_text']}\")" 2>/dev/null || \
  curl -s -X POST http://localhost:3001/farmers/farmer_001/chat/turn \
    -H "Content-Type: application/json" \
    -d "{\"session_id\": \"$SESSION\", \"text\": \"How many animals do I have?\"}"
echo ""

# Test 4: Chat - Weather with fragment
echo "Test 4: Chat - Weather with fragment"
SESSION2=$(curl -s -X POST http://localhost:3001/farmers/farmer_001/chat/session | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
echo "Session: $SESSION2"

echo "  User: 'What is the weather?'"
curl -s -X POST http://localhost:3001/farmers/farmer_001/chat/turn \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"$SESSION2\", \"text\": \"What is the weather?\"}" | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print(f\"  Bot: {d['reply_text']}\")" 2>/dev/null || \
  curl -s -X POST http://localhost:3001/farmers/farmer_001/chat/turn \
    -H "Content-Type: application/json" \
    -d "{\"session_id\": \"$SESSION2\", \"text\": \"What is the weather?\"}"

echo "  User: 'Delhi' (bare reply)"
curl -s -X POST http://localhost:3001/farmers/farmer_001/chat/turn \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"$SESSION2\", \"text\": \"Delhi\"}" | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print(f\"  Bot: {d['reply_text']}\")" 2>/dev/null || \
  curl -s -X POST http://localhost:3001/farmers/farmer_001/chat/turn \
    -H "Content-Type: application/json" \
    -d "{\"session_id\": \"$SESSION2\", \"text\": \"Delhi\"}"
echo ""

echo "=================================="
echo "✅ Tests complete!"
echo ""
echo "To run interactive CLI:"
echo "  node cli-batch.js       # Batch mode with defaults"
echo "  node cli-simple.js      # Interactive mode"
echo ""
echo "To run comprehensive tests:"
echo "  node test-conversation.js  # Specific conversation"
echo "  node test-long-conversations.js  # Full test suite"
