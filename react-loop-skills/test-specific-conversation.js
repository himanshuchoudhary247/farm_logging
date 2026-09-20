const http = require('http');

const PORT = 3001;

function makeRequest(path, method = 'GET', data = null) {
  return new Promise((resolve, reject) => {
    const options = {
      hostname: 'localhost',
      port: PORT,
      path,
      method,
      headers: { 'Content-Type': 'application/json' },
    };

    const req = http.request(options, (res) => {
      let body = '';
      res.on('data', (chunk) => body += chunk);
      res.on('end', () => {
        try { resolve(JSON.parse(body)); } catch (e) { resolve(body); }
      });
    });

    req.on('error', reject);
    if (data) req.write(JSON.stringify(data));
    req.end();
  });
}

const conversation = [
  { text: "I'd like to book an appointment", expected: "appointment" },
  { text: "1122", note: "bare reply - should go to animal_identifier" },
  { text: "not eating", note: "bare reply - should go to issue" },
  { text: "tomorrow 5 evening", note: "should extract date and time" },
  { text: "cool", note: "should ask to confirm/submit" },
  { text: "yes", note: "should confirm and submit" },
  { text: "done??", note: "should start fresh booking or ask" },
  { text: "yes", note: "should NOT show same confirmation loop" },
];

async function main() {
  console.log('='.repeat(80));
  console.log('TESTING SPECIFIC CONVERSATION FLOW');
  console.log('Issue: Bare replies, slot filling, confirmation loop bug');
  console.log('='.repeat(80));
  console.log();

  const sessionId = `test-specific-${Date.now()}`;
  await makeRequest(`/farmers/farmer_001/chat/session`, 'POST', { session_id: sessionId });
  console.log(`Session: ${sessionId}\n`);

  for (let i = 0; i < conversation.length; i++) {
    const turn = conversation[i];
    console.log(`Turn ${i + 1}: "${turn.text}"`);
    if (turn.note) console.log(`  Note: ${turn.note}`);
    
    const response = await makeRequest(
      `/farmers/farmer_001/chat/turn`,
      'POST',
      { session_id: sessionId, text: turn.text }
    );
    
    console.log(`  Skill: ${response.agent} (${(response._meta?.confidence * 100 || 0).toFixed(0)}%)`);
    console.log(`  Reply: "${response.reply_text}"`);
    console.log(`  State: activeSkill=${response._meta?.session_context?.active_skill}, expectedField=${response._meta?.expected_field}`);
    console.log(`  Meta: isBareReply=${response._meta?.is_bare_reply}, confirmationSignal=${response._meta?.confirmation_signal}`);
    console.log();
  }

  console.log('='.repeat(80));
}

main().catch(console.error);
