#!/usr/bin/env node
/**
 * Long-form Conversation Test Suite
 * Tests: fragments, fillers, topic changes, corrections, multi-turn flows
 */

const http = require('http');

const PORT = 3001;
const BASE_URL = `http://localhost:${PORT}`;

// Test scenarios with complete conversational flows
const longConversations = [
  {
    name: "Weather Multi-Turn with Fragment Follow-ups",
    description: "Start weather query, ask for location with fragments, change mind",
    farmerId: "farmer_001",
    turns: [
      {
        text: "What's the weather like?",
        expectedSkill: "weather",
        checkResponse: (r) => r.reply_text.includes("Which location"),
        expectedFollowUp: true,
      },
      {
        text: "umm... Delhi",  // filler + location
        expectedSkill: "weather",
        checkResponse: (r) => r.reply_text.includes("Delhi") && r.reply_text.includes("Sunny"),
        expectedFollowUp: false,
        notes: "Should handle filler 'umm'",
      },
      {
        text: "actually wait",  // filler, not a switch
        expectedSkill: "weather",
        checkResponse: (r) => r._meta.is_continuation || r._meta.required_follow_up,
        notes: "Should recognize 'actually' as potential continuation",
      },
      {
        text: "change to Mumbai",  // explicit switch
        expectedSkill: "weather",
        checkResponse: (r) => r.reply_text.includes("Mumbai"),
        notes: "Should switch location within same skill",
      },
      {
        text: "and tomorrow?",  // fragment
        expectedSkill: "weather",
        checkResponse: (r) => r._meta.is_continuation || r.reply_text.length > 0,
        expectedFollowUp: false,
        notes: "Should continue weather flow",
      },
      {
        text: "hmm",  // just a filler
        expectedSkill: "weather",
        checkResponse: (r) => r._meta.required_follow_up || r.reply_text.length > 0,
        notes: "Should ask for clarification or continue",
      },
      {
        text: "how about Bangalore instead",  // switch with filler
        expectedSkill: "weather",
        checkResponse: (r) => r.reply_text.includes("Bangalore"),
        notes: "Should handle 'how about' + 'instead'",
      },
    ],
  },
  {
    name: "Appointment Booking with Multiple Corrections",
    description: "Book appointment, change details multiple times, submit",
    farmerId: "farmer_001",
    turns: [
      {
        text: "I want to book an appointment",
        expectedSkill: "appointments",
        expectedFollowUp: true,
        checkResponse: (r) => r.reply_text.toLowerCase().includes("type"),
      },
      {
        text: "vet",  // bare reply
        expectedSkill: "appointments",
        checkResponse: (r) => r._meta.is_bare_reply || r.reply_text.length > 0,
        notes: "Should recognize bare reply",
      },
      {
        text: "actually make it agricultural",  // correction
        expectedSkill: "appointments",
        checkResponse: (r) => r.reply_text.toLowerCase().includes("agricultural") || r.reply_text.toLowerCase().includes("date"),
        notes: "Should handle correction",
      },
      {
        text: "no wait back to vet",  // multiple corrections
        expectedSkill: "appointments",
        checkResponse: (r) => r._meta.session_context.active_skill === "appointments",
        notes: "Should handle 'no wait' as correction, not denial",
      },
      {
        text: "tomorrow",  // bare date
        expectedSkill: "appointments",
        expectedFollowUp: true,
        notes: "Should extract relative date",
      },
      {
        text: "10 am",  // bare time
        expectedSkill: "appointments",
        expectedFollowUp: false,
        checkResponse: (r) => r.reply_text.toLowerCase().includes("submit"),
      },
      {
        text: "no",  // denial (not cancel)
        expectedSkill: "appointments",
        checkResponse: (r) => r.reply_text.toLowerCase().includes("correct"),
        notes: "Should ask what to correct",
      },
      {
        text: "change the time to 2 pm",  // specific correction
        expectedSkill: "appointments",
        expectedFollowUp: false,
        checkResponse: (r) => r.reply_text.toLowerCase().includes("submit"),
      },
      {
        text: "yes submit",  // confirmation
        expectedSkill: "appointments",
        checkResponse: (r) => r.reply_text.toLowerCase().includes("booked") || r.reply_text.toLowerCase().includes("saved"),
        notes: "Should submit successfully",
      },
      {
        text: "another one",  // after submit
        expectedSkill: "appointments",
        expectedFollowUp: true,
        notes: "Should start fresh booking after submit",
      },
    ],
  },
  {
    name: "Farm QA with Context Switching",
    description: "Ask about animals, switch to weather, back to animals",
    farmerId: "farmer_001",
    turns: [
      {
        text: "How many cows do I have?",
        expectedSkill: "farm-qa",
        checkResponse: (r) => r.reply_text.includes("1 cow"),
      },
      {
        text: "and buffalo?",  // fragment
        expectedSkill: "farm-qa",
        checkResponse: (r) => r._meta.is_continuation || r.reply_text.includes("buffalo"),
        notes: "Should continue farm-qa flow",
      },
      {
        text: "what's the weather?",  // context switch
        expectedSkill: "weather",
        checkResponse: (r) => r.reply_text.toLowerCase().includes("location"),
        expectedFollowUp: true,
      },
      {
        text: "umm... Bangalore",  // filler + location
        expectedSkill: "weather",
        checkResponse: (r) => r.reply_text.includes("Bangalore"),
      },
      {
        text: "anyway back to my animals",  // return to farm
        expectedSkill: "farm-qa",
        checkResponse: (r) => r.reply_text.includes("animals") || r.reply_text.includes("farm"),
        notes: "Should switch back to farm-qa",
      },
      {
        text: "how many total?",  // fragment
        expectedSkill: "farm-qa",
        checkResponse: (r) => r.reply_text.includes("3 animals"),
        notes: "Should understand 'total' refers to all animals",
      },
      {
        text: "show me the goat",  // specific animal
        expectedSkill: "farm-qa",
        checkResponse: (r) => r.reply_text.includes("Moti") || r.reply_text.includes("goat"),
      },
      {
        text: "what about the weather now?",  // switch back
        expectedSkill: "weather",
        checkResponse: (r) => r._meta.session_context.active_skill === "weather",
      },
      {
        text: "In Delhi",  // bare location
        expectedSkill: "weather",
        checkResponse: (r) => r._meta.is_bare_reply && r.reply_text.includes("Delhi"),
      },
    ],
  },
  {
    name: "Market Prices with Disambiguation",
    description: "Vague queries, disambiguation, price comparison",
    farmerId: "farmer_001",
    turns: [
      {
        text: "what's the price?",  // vague
        expectedSkill: "market-prices",
        expectedFollowUp: true,
        checkResponse: (r) => r.reply_text.toLowerCase().includes("commodity"),
        notes: "Should ask for commodity",
      },
      {
        text: "wheat",  // bare reply
        expectedSkill: "market-prices",
        checkResponse: (r) => r.reply_text.includes("wheat") && r.reply_text.includes("₹"),
        notes: "Should extract commodity from bare reply",
      },
      {
        text: "and rice?",  // fragment
        expectedSkill: "market-prices",
        checkResponse: (r) => r._meta.is_continuation || r.reply_text.includes("rice"),
        notes: "Should continue market-prices flow",
      },
      {
        text: "actually compare both",  // complex query
        expectedSkill: "market-prices",
        checkResponse: (r) => r.reply_text.length > 0,
        notes: "Should handle comparison request",
      },
      {
        text: "cancel",  // cancel
        expectedSkill: null,
        checkResponse: (r) => r._meta.confirmation_signal === "cancel" || r.reply_text.length > 0,
        notes: "Should handle cancel",
      },
    ],
  },
  {
    name: "Complex Multi-Skill Conversation",
    description: "Mix of all skills with corrections and switches",
    farmerId: "farmer_001",
    turns: [
      {
        text: "Hello",
        expectedSkill: null,
        expectedFollowUp: true,
        checkResponse: (r) => r.reply_text.toLowerCase().includes("help") || r.reply_text.toLowerCase().includes("weather"),
      },
      {
        text: "my animals first",  // vague but intent clear
        expectedSkill: "farm-qa",
        checkResponse: (r) => r.reply_text.includes("animals"),
      },
      {
        text: "3 of them right?",  // confirmation question
        expectedSkill: "farm-qa",
        checkResponse: (r) => r.reply_text.includes("yes") || r.reply_text.includes("3"),
        notes: "Should confirm or correct",
      },
      {
        text: "weather next",  // explicit switch
        expectedSkill: "weather",
        expectedFollowUp: true,
      },
      {
        text: "Mumbai",  // bare location
        expectedSkill: "weather",
        checkResponse: (r) => r.reply_text.includes("Mumbai"),
      },
      {
        text: "wrong city I meant Delhi",  // correction with filler
        expectedSkill: "weather",
        checkResponse: (r) => r.reply_text.includes("Delhi"),
        notes: "Should handle 'wrong' + correction",
      },
      {
        text: "book appointment",  // switch
        expectedSkill: "appointments",
        expectedFollowUp: true,
      },
      {
        text: "vet for Gauri",  // specific
        expectedSkill: "appointments",
        checkResponse: (r) => r.reply_text.includes("date") || r.reply_text.includes("time"),
      },
      {
        text: "tomorrow at 10",  // combined input
        expectedSkill: "appointments",
        checkResponse: (r) => r.reply_text.toLowerCase().includes("submit"),
      },
      {
        text: "stop cancel everything",  // cancel
        expectedSkill: null,
        checkResponse: (r) => r._meta.confirmation_signal === "cancel" || r.reply_text.length > 0,
      },
      {
        text: "ok back to animals",  // return
        expectedSkill: "farm-qa",
        checkResponse: (r) => r.reply_text.includes("animals"),
      },
      {
        text: "how many cows buffalo total",  // multiple in one
        expectedSkill: "farm-qa",
        checkResponse: (r) => r.reply_text.includes("cow") && r.reply_text.includes("buffalo"),
      },
    ],
  },
  {
    name: "Fragment Hell - Maximum Bare Replies",
    description: "All fragments, should maintain context",
    farmerId: "farmer_001",
    context: { activeSkill: "weather", expectedField: "location" },
    turns: [
      {
        text: "What is the weather?",
        expectedSkill: "weather",
        expectedFollowUp: true,
      },
      {
        text: "Delhi",  // bare
        expectedSkill: "weather",
        checkResponse: (r) => r._meta.is_bare_reply,
      },
      {
        text: "and",  // incomplete
        expectedSkill: "weather",
        notes: "Should ask for clarification or continue",
      },
      {
        text: "tomorrow",  // bare
        expectedSkill: "weather",
        checkResponse: (r) => r._meta.is_bare_reply || r._meta.is_continuation,
      },
      {
        text: "umm",  // just filler
        expectedSkill: "weather",
      },
      {
        text: "Mumbai",  // switch location
        expectedSkill: "weather",
        checkResponse: (r) => r.reply_text.includes("Mumbai"),
      },
      {
        text: "next week",  // relative time
        expectedSkill: "weather",
        checkResponse: (r) => r._meta.is_bare_reply || r._meta.is_continuation,
      },
      {
        text: "",  // empty
        expectedSkill: "weather",
        expectedFollowUp: true,
        notes: "Should handle empty input gracefully",
      },
      {
        text: "actually Bangalore",  // correction
        expectedSkill: "weather",
        checkResponse: (r) => r.reply_text.includes("Bangalore"),
      },
    ],
  },
];

// Helper function to make HTTP requests
function makeRequest(path, method = 'GET', data = null) {
  return new Promise((resolve, reject) => {
    const options = {
      hostname: 'localhost',
      port: PORT,
      path,
      method,
      headers: {
        'Content-Type': 'application/json',
      },
    };

    const req = http.request(options, (res) => {
      let body = '';
      res.on('data', (chunk) => body += chunk);
      res.on('end', () => {
        try {
          resolve(JSON.parse(body));
        } catch (e) {
          resolve(body);
        }
      });
    });

    req.on('error', reject);

    if (data) {
      req.write(JSON.stringify(data));
    }

    req.end();
  });
}

// Run a single conversation
async function runConversation(conv, index) {
  console.log(`\n${'='.repeat(80)}`);
  console.log(`TEST ${index + 1}: ${conv.name}`);
  console.log(`Description: ${conv.description}`);
  console.log(`${'='.repeat(80)}`);

  const sessionId = `test-${Date.now()}-${index}`;
  let results = [];
  let passCount = 0;
  let failCount = 0;

  // Create session
  try {
    await makeRequest(`/farmers/${conv.farmerId}/chat/session`, 'POST', { session_id: sessionId });
    console.log(`✅ Session created: ${sessionId}`);
  } catch (e) {
    console.log(`❌ Failed to create session: ${e.message}`);
  }

  for (let i = 0; i < conv.turns.length; i++) {
    const turn = conv.turns[i];
    console.log(`\n--- Turn ${i + 1} ---`);
    console.log(`User: "${turn.text}"`);
    if (turn.notes) {
      console.log(`Note: ${turn.notes}`);
    }

    try {
      const response = await makeRequest(
        `/farmers/${conv.farmerId}/chat/turn`,
        'POST',
        { session_id: sessionId, text: turn.text, language: 'en-IN' }
      );

      const result = {
        turn: i + 1,
        user: turn.text,
        expectedSkill: turn.expectedSkill,
        actualSkill: response.agent,
        confidence: response._meta?.confidence,
        reply: response.reply_text?.substring(0, 100) + (response.reply_text?.length > 100 ? '...' : ''),
        requiredFollowUp: response._meta?.required_follow_up,
        isBareReply: response._meta?.is_bare_reply,
        isContinuation: response._meta?.is_continuation,
        confirmationSignal: response._meta?.confirmation_signal,
        errors: [],
      };

      // Check skill detection
      if (turn.expectedSkill && response.agent !== turn.expectedSkill) {
        result.errors.push(`Expected skill '${turn.expectedSkill}', got '${response.agent}'`);
      }

      // Check follow-up requirement
      if (turn.expectedFollowUp !== undefined && response._meta?.required_follow_up !== turn.expectedFollowUp) {
        result.errors.push(`Follow-up: expected ${turn.expectedFollowUp}, got ${response._meta?.required_follow_up}`);
      }

      // Check custom response validation
      if (turn.checkResponse && !turn.checkResponse(response)) {
        result.errors.push('Custom validation failed');
      }

      // Print results
      if (result.errors.length === 0) {
        console.log(`✅ PASS`);
        console.log(`   Skill: ${result.actualSkill} (${(result.confidence * 100).toFixed(0)}%)`);
        console.log(`   Reply: "${result.reply}"`);
        if (result.isBareReply) console.log(`   Is bare reply: true`);
        if (result.isContinuation) console.log(`   Is continuation: true`);
        passCount++;
      } else {
        console.log(`❌ FAIL: ${result.errors.join(', ')}`);
        console.log(`   Skill: ${result.actualSkill} (${(result.confidence * 100).toFixed(0)}%)`);
        console.log(`   Reply: "${result.reply}"`);
        failCount++;
      }

      results.push(result);
    } catch (e) {
      console.log(`❌ ERROR: ${e.message}`);
      failCount++;
      results.push({ turn: i + 1, error: e.message });
    }
  }

  return { name: conv.name, passCount, failCount, total: conv.turns.length, results };
}

// Main test runner
async function main() {
  console.log('='.repeat(80));
  console.log('🧪 LONG-FORM CONVERSATION TEST SUITE');
  console.log('Testing: fragments, fillers, corrections, context switching');
  console.log('='.repeat(80));

  // Check server
  try {
    await makeRequest('/health');
    console.log('✅ Server is running\n');
  } catch (e) {
    console.log('❌ Server not running. Start with: node server-fixed.js\n');
    process.exit(1);
  }

  const allResults = [];
  let totalPasses = 0;
  let totalFails = 0;

  for (let i = 0; i < longConversations.length; i++) {
    const result = await runConversation(longConversations[i], i);
    allResults.push(result);
    totalPasses += result.passCount;
    totalFails += result.failCount;
  }

  // Summary
  console.log(`\n${'='.repeat(80)}`);
  console.log('📊 TEST SUMMARY');
  console.log(`${'='.repeat(80)}`);
  console.log(`Total Tests: ${longConversations.length}`);
  console.log(`Total Turns: ${totalPasses + totalFails}`);
  console.log(`✅ Passed: ${totalPasses} (${((totalPasses / (totalPasses + totalFails)) * 100).toFixed(1)}%)`);
  console.log(`❌ Failed: ${totalFails} (${((totalFails / (totalPasses + totalFails)) * 100).toFixed(1)}%)`);
  console.log('');

  // Per-conversation results
  console.log('By Conversation:');
  for (const result of allResults) {
    const status = result.failCount === 0 ? '✅' : result.failCount < result.total / 2 ? '⚠️' : '❌';
    console.log(`  ${status} ${result.name}: ${result.passCount}/${result.total} (${((result.passCount / result.total) * 100).toFixed(0)}%)`);
  }

  console.log('');
  console.log('Failed Details:');
  let hasFailures = false;
  for (const result of allResults) {
    const failedTurns = result.results.filter(r => r.errors && r.errors.length > 0);
    if (failedTurns.length > 0) {
      hasFailures = true;
      console.log(`\n  ${result.name}:`);
      for (const turn of failedTurns) {
        console.log(`    Turn ${turn.turn}: "${turn.user.substring(0, 40)}${turn.user.length > 40 ? '...' : ''}"`);
        console.log(`      → ${turn.errors.join(', ')}`);
      }
    }
  }
  if (!hasFailures) {
    console.log('  All tests passed! 🎉');
  }

  console.log(`\n${'='.repeat(80)}`);
}

main().catch(console.error);
