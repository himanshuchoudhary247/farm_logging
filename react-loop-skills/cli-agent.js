#!/usr/bin/env node
/**
 * Interactive CLI for React Loop Skills
 * Chat with the agent directly from command line
 */

const readline = require('readline');
const http = require('http');

const PORT = 3001;  // or 3002 for appointment server
const BASE_URL = `http://localhost:${PORT}`;

// Colors for terminal output
const colors = {
  reset: '\x1b[0m',
  bright: '\x1b[1m',
  dim: '\x1b[2m',
  red: '\x1b[31m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  magenta: '\x1b[35m',
  cyan: '\x1b[36m',
  gray: '\x1b[90m',
};

function colorize(color, text) {
  return colors[color] + text + colors.reset;
}

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

    req.on('error', (err) => {
      reject(new Error(`Cannot connect to server at ${BASE_URL}. Is it running?`));
    });

    if (data) {
      req.write(JSON.stringify(data));
    }

    req.end();
  });
}

class InteractiveAgent {
  constructor() {
    this.rl = readline.createInterface({
      input: process.stdin,
      output: process.stdout,
    });
    
    this.farmerId = 'farmer_001';
    this.sessionId = null;
    this.context = {
      activeSkill: null,
      collectedParams: {},
    };
    this.history = [];
    this.turnCount = 0;
  }

  async start() {
    console.clear();
    console.log(colorize('cyan', '='.repeat(80)));
    console.log(colorize('bright', colorize('cyan', '  🤖 React Loop Skills - Interactive CLI Agent')));
    console.log(colorize('cyan', '='.repeat(80)));
    console.log();
    console.log(colorize('gray', `  Server: ${BASE_URL}`));
    console.log(colorize('gray', `  Farmer: ${this.farmerId}`));
    console.log();
    
    // Check server health
    try {
      await makeRequest('/health');
      console.log(colorize('green', '  ✅ Server is running'));
    } catch (err) {
      console.log(colorize('red', `  ❌ ${err.message}`));
      console.log();
      console.log(colorize('yellow', '  Start the server with:'));
      console.log(colorize('gray', '    cd react-loop-skills'));
      console.log(colorize('gray', '    node server-fixed.js'));
      console.log();
      process.exit(1);
    }
    
    // Create session
    try {
      const resp = await makeRequest(`/farmers/${this.farmerId}/chat/session`, 'POST', {});
      this.sessionId = resp.session?.id;
      console.log(colorize('green', `  ✅ Session created: ${this.sessionId}`));
    } catch (err) {
      console.log(colorize('red', `  ❌ Failed to create session: ${err.message}`));
      process.exit(1);
    }
    
    console.log();
    console.log(colorize('cyan', '='.repeat(80)));
    console.log();
    console.log(colorize('yellow', '  Type your message and press Enter to chat.'));
    console.log(colorize('gray', '  Commands:'));
    console.log(colorize('gray', '    /help     - Show help'));
    console.log(colorize('gray', '    /context  - Show current context'));
    console.log(colorize('gray', '    /history  - Show conversation history'));
    console.log(colorize('gray', '    /clear    - Clear screen'));
    console.log(colorize('gray', '    /quit     - Exit'));
    console.log();
    console.log(colorize('cyan', '='.repeat(80)));
    console.log();
    
    this.prompt();
  }

  async sendMessage(text, silent = false) {
    this.turnCount++;
    
    try {
      const response = await makeRequest(
        `/farmers/${this.farmerId}/chat/turn`,
        'POST',
        { session_id: this.sessionId, text: text, language: 'en-IN' }
      );
      
      // Store in history
      this.history.push({
        turn: this.turnCount,
        user: text,
        bot: response.reply_text,
        skill: response.agent,
        confidence: response._meta?.confidence,
        metadata: response._meta,
      });
      
      // Update context
      if (response._meta?.session_context) {
        this.context = response._meta.session_context;
      }
      
      if (!silent) {
        this.displayResponse(response);
      }
      
      return response;
    } catch (err) {
      console.log(colorize('red', `\n  ❌ Error: ${err.message}\n`));
    }
  }

  displayResponse(response) {
    const meta = response._meta || {};
    
    // Bot response
    console.log(colorize('green', `🤖 Agent:`));
    console.log(`   ${response.reply_text}`);
    console.log();
    
    // Debug info (dim)
    if (meta.confidence !== undefined) {
      const conf = Math.round(meta.confidence * 100);
      const confColor = conf > 80 ? 'green' : conf > 50 ? 'yellow' : 'red';
      console.log(colorize('gray', `   Confidence: ${colorize(confColor, conf + '%')}`));
    }
    
    if (meta.session_context?.active_skill) {
      console.log(colorize('gray', `   Active Skill: ${meta.session_context.active_skill}`));
    }
    
    if (meta.expected_field) {
      console.log(colorize('yellow', `   ⏳ Waiting for: ${meta.expected_field}`));
    }
    
    if (meta.is_bare_reply) {
      console.log(colorize('cyan', '   📎 Bare reply detected'));
    }
    
    if (meta.is_continuation) {
      console.log(colorize('cyan', '   🔄 Flow continuation'));
    }
    
    if (meta.confirmation_signal) {
      console.log(colorize('magenta', `   ✓ Confirmation: ${meta.confirmation_signal}`));
    }
    
    if (meta.required_follow_up) {
      console.log(colorize('yellow', '   ⚠️  Follow-up required'));
    }
    
    if (Object.keys(meta.session_context?.collected_params || {}).length > 0) {
      const params = Object.entries(meta.session_context.collected_params)
        .map(([k, v]) => `${k}=${v}`)
        .join(', ');
      console.log(colorize('gray', `   Collected: ${params}`));
    }
    
    console.log();
  }

  prompt() {
    this.rl.question(colorize('blue', 'You: '), async (input) => {
      const text = input.trim();
      
      if (!text) {
        this.prompt();
        return;
      }
      
      // Handle commands
      if (text.startsWith('/')) {
        await this.handleCommand(text);
        this.prompt();
        return;
      }
      
      // Send message
      await this.sendMessage(text);
      this.prompt();
    });
  }

  async handleCommand(cmd) {
    const [command, ...args] = cmd.split(' ');
    
    switch (command) {
      case '/help':
        this.showHelp();
        break;
        
      case '/context':
        this.showContext();
        break;
        
      case '/history':
        this.showHistory();
        break;
        
      case '/clear':
        console.clear();
        console.log(colorize('cyan', 'Screen cleared. Conversation continues...'));
        console.log();
        break;
        
      case '/quit':
      case '/exit':
        this.quit();
        break;
        
      case '/test':
        await this.runTestScenario(args[0]);
        break;
        
      default:
        console.log(colorize('red', `Unknown command: ${command}`));
        console.log(colorize('gray', 'Type /help for available commands'));
        console.log();
    }
  }

  showHelp() {
    console.log();
    console.log(colorize('cyan', 'Available Commands:'));
    console.log();
    console.log(colorize('yellow', '  General:'));
    console.log('    /help          - Show this help message');
    console.log('    /context       - Show current conversation context');
    console.log('    /history       - Show conversation history');
    console.log('    /clear         - Clear the screen');
    console.log('    /quit          - Exit the application');
    console.log();
    console.log(colorize('yellow', '  Test Scenarios:'));
    console.log('    /test weather  - Run weather conversation test');
    console.log('    /test farm     - Run farm QA test');
    console.log('    /test appt     - Run appointment booking test');
    console.log('    /test market   - Run market prices test');
    console.log();
    console.log(colorize('yellow', '  Example Messages:'));
    console.log('    "What is the weather?"');
    console.log('    "How many animals do I have?"');
    console.log('    "Book an appointment"');
    console.log('    "What is the price of wheat?"');
    console.log();
  }

  showContext() {
    console.log();
    console.log(colorize('cyan', 'Current Context:'));
    console.log();
    console.log(`  Session ID: ${this.sessionId}`);
    console.log(`  Farmer ID: ${this.farmerId}`);
    console.log(`  Turn Count: ${this.turnCount}`);
    console.log(`  Active Skill: ${this.context.activeSkill || 'none'}`);
    console.log(`  Collected Params: ${JSON.stringify(this.context.collectedParams, null, 2)}`);
    console.log();
  }

  showHistory() {
    console.log();
    console.log(colorize('cyan', 'Conversation History:'));
    console.log();
    
    if (this.history.length === 0) {
      console.log(colorize('gray', '  No messages yet.'));
      console.log();
      return;
    }
    
    this.history.forEach((h) => {
      console.log(colorize('gray', `  [Turn ${h.turn}]`));
      console.log(`  You:  ${h.user}`);
      console.log(colorize('green', `  Bot:  ${h.bot}`));
      console.log(colorize('gray', `  Skill: ${h.skill} (${Math.round(h.confidence * 100)}%)`));
      console.log();
    });
  }

  async runTestScenario(scenario) {
    const scenarios = {
      weather: [
        "What's the weather?",
        "Delhi",
        "and tomorrow?",
        "Mumbai",
        "thanks",
      ],
      farm: [
        "How many animals do I have?",
        "Show me my cows",
        "and buffalo?",
        "total count?",
      ],
      appt: [
        "Book an appointment",
        "vet",
        "tomorrow 10am",
        "yes",
      ],
      market: [
        "What's the price of wheat?",
        "and rice?",
        "thanks",
      ],
    };
    
    const test = scenarios[scenario];
    if (!test) {
      console.log(colorize('red', `Unknown test scenario: ${scenario}`));
      console.log(colorize('gray', 'Available: weather, farm, appt, market'));
      console.log();
      return;
    }
    
    console.log();
    console.log(colorize('cyan', `Running ${scenario} test scenario...`));
    console.log(colorize('gray', '----------------------------------------'));
    console.log();
    
    for (const msg of test) {
      console.log(colorize('blue', `You: ${msg}`));
      await this.sendMessage(msg);
      await this.sleep(500);  // Small delay between messages
    }
    
    console.log(colorize('gray', '----------------------------------------'));
    console.log(colorize('green', 'Test scenario complete!'));
    console.log();
  }

  sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  quit() {
    console.log();
    console.log(colorize('cyan', 'Thank you for chatting! 👋'));
    console.log();
    this.rl.close();
    process.exit(0);
  }
}

// Handle Ctrl+C gracefully
process.on('SIGINT', () => {
  console.log();
  console.log(colorize('cyan', '\nGoodbye! 👋'));
  process.exit(0);
});

// Start the interactive agent
const agent = new InteractiveAgent();
agent.start().catch(console.error);
