#!/usr/bin/env node
/**
 * Simple CLI for React Loop Skills
 * Basic version without fancy formatting
 */

const readline = require('readline');
const http = require('http');

const PORT = 3001;

const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout,
});

function ask(question) {
  return new Promise(resolve => rl.question(question, resolve));
}

function makeRequest(path, method, data) {
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
      res.on('data', chunk => body += chunk);
      res.on('end', () => {
        try { resolve(JSON.parse(body)); } catch (e) { resolve(body); }
      });
    });

    req.on('error', reject);
    if (data) req.write(JSON.stringify(data));
    req.end();
  });
}

async function main() {
  console.log('🤖 React Loop Skills - Simple CLI');
  console.log('====================================');
  console.log();
  
  // Check server
  try {
    await makeRequest('/health');
    console.log('✅ Server is running on port', PORT);
  } catch (e) {
    console.log('❌ Server not running. Start with: node server-fixed.js');
    process.exit(1);
  }
  
  // Create session
  const farmerId = 'farmer_001';
  const sessionResp = await makeRequest(`/farmers/${farmerId}/chat/session`, 'POST', {});
  const sessionId = sessionResp.session.id;
  console.log('✅ Session created:', sessionId);
  console.log();
  console.log('Type your messages below. Type "quit" to exit.');
  console.log('====================================');
  console.log();
  
  while (true) {
    const text = await ask('You: ');
    
    if (text.toLowerCase() === 'quit' || text.toLowerCase() === 'exit') {
      console.log('\n👋 Goodbye!');
      rl.close();
      break;
    }
    
    try {
      const response = await makeRequest(
        `/farmers/${farmerId}/chat/turn`,
        'POST',
        { session_id: sessionId, text: text }
      );
      
      console.log('🤖 Agent:', response.reply_text);
      
      // Show metadata
      const meta = response._meta || {};
      if (meta.confidence !== undefined) {
        console.log('   Confidence:', Math.round(meta.confidence * 100) + '%');
      }
      if (meta.session_context?.active_skill) {
        console.log('   Skill:', meta.session_context.active_skill);
      }
      if (meta.expected_field) {
        console.log('   Waiting for:', meta.expected_field);
      }
      if (meta.is_bare_reply) {
        console.log('   [Bare reply detected]');
      }
      console.log();
    } catch (err) {
      console.log('❌ Error:', err.message);
      console.log();
    }
  }
}

main().catch(err => {
  console.error('Error:', err);
  rl.close();
});
