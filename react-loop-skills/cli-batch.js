#!/usr/bin/env node
/**
 * React Loop Skills - Batch CLI
 * Send multiple messages from stdin or command line
 */

const http = require('http');

const PORT = process.env.PORT || 3001;
const FARMER_ID = process.env.FARMER_ID || 'farmer_001';

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
  // Check server
  try {
    await makeRequest('/health');
  } catch (e) {
    console.error('❌ Server not running on port', PORT);
    console.error('   Start with: node server-fixed.js');
    process.exit(1);
  }

  // Create session
  const sessionResp = await makeRequest(`/farmers/${FARMER_ID}/chat/session`, 'POST', {});
  const sessionId = sessionResp.session.id;

  console.log('🤖 React Loop Skills - Batch Mode');
  console.log('='.repeat(60));
  console.log('Session:', sessionId);
  console.log('Farmer:', FARMER_ID);
  console.log('='.repeat(60));
  console.log();

  // Read messages from stdin or use default
  const input = await new Promise((resolve) => {
    let data = '';
    process.stdin.setEncoding('utf8');
    
    process.stdin.on('data', chunk => {
      data += chunk;
    });
    
    process.stdin.on('end', () => {
      resolve(data);
    });
    
    // If no stdin, resolve with empty
    setTimeout(() => {
      if (!data) resolve('');
    }, 100);
  });

  let messages = [];
  
  if (input.trim()) {
    // Parse messages from stdin
    messages = input.split('\n').filter(l => l.trim());
  } else {
    // Default test messages
    messages = [
      "hello",
      "what is the weather?",
      "Delhi",
      "and tomorrow?",
      "How many animals do I have?",
      "show my cows",
      "thanks",
    ];
    console.log('No input provided. Using default test messages:');
    console.log();
  }

  for (const text of messages) {
    if (!text.trim() || text.toLowerCase() === 'quit') continue;
    
    console.log('You:', text);
    
    try {
      const response = await makeRequest(
        `/farmers/${FARMER_ID}/chat/turn`,
        'POST',
        { session_id: sessionId, text: text }
      );
      
      console.log('🤖', response.reply_text);
      
      // Show metadata
      const meta = response._meta || {};
      const details = [];
      if (meta.confidence !== undefined) {
        details.push(`confidence: ${Math.round(meta.confidence * 100)}%`);
      }
      if (meta.session_context?.active_skill) {
        details.push(`skill: ${meta.session_context.active_skill}`);
      }
      if (meta.is_bare_reply) {
        details.push('bare reply');
      }
      if (meta.is_continuation) {
        details.push('continuation');
      }
      if (details.length > 0) {
        console.log('   [', details.join(' | '), ']');
      }
      console.log();
    } catch (err) {
      console.log('❌ Error:', err.message);
      console.log();
    }
  }

  console.log('='.repeat(60));
  console.log('✅ Conversation complete!');
}

main().catch(err => {
  console.error('Error:', err);
  process.exit(1);
});
