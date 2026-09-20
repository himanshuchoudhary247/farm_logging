#!/usr/bin/env node
const http = require('http');

function makeRequest(path, method, data) {
  return new Promise((resolve, reject) => {
    const options = { hostname: 'localhost', port: 3002, path, method, headers: { 'Content-Type': 'application/json' } };
    const req = http.request(options, (res) => { let body = ''; res.on('data', c => body += c); res.on('end', () => { try { resolve(JSON.parse(body)); } catch (e) { resolve(body); } }); });
    req.on('error', reject);
    if (data) req.write(JSON.stringify(data));
    req.end();
  });
}

const conversation = [
  { text: "I'd like to book an appointment", note: "Start appointment flow" },
  { text: "1122", note: "Should go to animal_identifier" },
  { text: "not eating", note: "Should go to issue" },
  { text: "tomorrow 5 evening", note: "Should extract date and time" },
  { text: "cool", note: "Should ask to confirm" },
  { text: "yes", note: "Should submit" },
  { text: "done??", note: "Should NOT loop, ask what's next" },
  { text: "yes", note: "Should NOT show same confirmation" },
];

async function main() {
  console.log('='.repeat(80));
  console.log('TESTING SPECIFIC CONVERSATION FLOW');
  console.log('='.repeat(80));
  
  const session = (await makeRequest('/farmers/farmer_001/chat/session', 'POST', {})).session;
  console.log('Session:', session.id);
  
  for (const turn of conversation) {
    console.log('\n' + '-'.repeat(80));
    console.log('User: "' + turn.text + '"');
    console.log('Note:', turn.note);
    
    const resp = await makeRequest('/farmers/farmer_001/chat/turn', 'POST', { session_id: session.id, text: turn.text });
    console.log('Bot:', resp.reply_text);
    console.log('Mode:', resp._meta?.mode, '| AwaitingConfirmation:', resp._meta?.awaiting_confirmation, '| Submitted:', resp._meta?.submitted);
  }
  
  console.log('\n' + '='.repeat(80));
}

main().catch(console.error);
