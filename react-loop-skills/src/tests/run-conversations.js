#!/usr/bin/env node
/**
 * Conversation Test Runner - Live Testing of React Loop Skills
 * Tests conversations with fillers, incomplete info, follow-ups, and disambiguation
 */

const path = require('path');

// Simple console colors
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
};

// Mock data
const mockDatabase = {
  farmers: [
    { id: 'farmer_001', name: 'Rajesh Kumar', phone: '9876543210', village: 'Khera', district: 'Muzaffarnagar', state: 'Uttar Pradesh' },
  ],
  animals: [
    { id: 'animal_001', farmer_id: 'farmer_001', tag_number: 'COW001', name: 'Gauri', type: 'cow', breed: 'Sahiwal', health_status: 'healthy' },
    { id: 'animal_002', farmer_id: 'farmer_001', tag_number: 'BUF001', name: 'Lakshmi', type: 'buffalo', breed: 'Murrah', health_status: 'healthy' },
    { id: 'animal_003', farmer_id: 'farmer_001', tag_number: 'GOAT001', name: 'Moti', type: 'goat', breed: 'Jamunapari', health_status: 'healthy' },
  ],
  appointments: [
    { id: 'apt_001', farmer_id: 'farmer_001', type: 'veterinary', date: '2026-09-20', time: '10:00', status: 'confirmed', reason: 'Vaccination' },
  ],
};

// Conversation Logger
class ConversationLogger {
  constructor(sessionId) {
    this.sessionId = sessionId;
    this.logs = [];
    this.logFile = path.join(__dirname, '..', 'logs', `conversation_${sessionId}_${Date.now()}.json`);
  }

  log(level, component, message, data) {
    const entry = {
      timestamp: new Date().toISOString(),
      level,
      component,
      message,
      data,
    };
    this.logs.push(entry);
    
    const prefix = `[${entry.timestamp}] [${level.toUpperCase()}] [${component}]`;
    if (data) {
      console.log(`${colors.dim}${prefix}${colors.reset}`, message, JSON.stringify(data, null, 2));
    } else {
      console.log(`${colors.dim}${prefix}${colors.reset}`, message);
    }
  }

  debug(component, message, data) { this.log('debug', component, message, data); }
  info(component, message, data) { this.log('info', component, message, data); }
  warn(component, message, data) { this.log('warn', component, message, data); }
  error(component, message, data) { this.log('error', component, message, data); }

  export() {
    return JSON.stringify(this.logs, null, 2);
  }
}

// Context Window - keeps last N turns
class ContextWindow {
  constructor(maxTurns = 10) {
    this.maxTurns = maxTurns;
    this.turns = [];
    this.toolHistory = [];
  }

  addUserTurn(content) {
    this.turns.push({ role: 'user', content, timestamp: new Date() });
    this.trim();
  }

  addAssistantTurn(content, skillId, toolCalls) {
    this.turns.push({ role: 'assistant', content, skillId, toolCalls, timestamp: new Date() });
    
    if (toolCalls) {
      toolCalls.forEach(tc => {
        this.toolHistory.push({
          skillId,
          toolName: tc.tool_name,
          timestamp: new Date(),
          params: tc.parameters,
        });
      });
    }
    
    this.trim();
  }

  trim() {
    if (this.turns.length > this.maxTurns * 2) {
      this.turns = this.turns.slice(-this.maxTurns * 2);
    }
  }

  getRecentTurns(count = this.maxTurns) {
    return this.turns.slice(-count * 2);
  }

  getContextString() {
    return this.turns.map(t => `${t.role}: ${t.content}`).join('\n');
  }

  getToolHistory() {
    return this.toolHistory;
  }

  getRecentTools(count = 5) {
    return this.toolHistory.slice(-count);
  }

  getLastSkill() {
    for (let i = this.turns.length - 1; i >= 0; i--) {
      if (this.turns[i].skillId) return this.turns[i].skillId;
    }
    return null;
  }
}

// Skills configuration
const skills = {
  weather: {
    id: 'weather',
    name: 'Weather Service',
    intents: ['weather', 'forecast', 'rain', 'temperature', 'will it rain', 'how hot', 'how cold'],
    keywords: ['weather', 'rain', 'sunny', 'cloudy', 'storm', 'temperature', 'humidity', 'forecast'],
    tools: {
      get_current_weather: {
        name: 'get_current_weather',
        description: 'Get current weather',
        required: ['location'],
        optional: ['units'],
        handler: (params) => {
          const location = params.location || 'Delhi';
          return {
            success: true,
            data: {
              location,
              temperature: 32,
              conditions: 'Sunny',
              humidity: 45,
              wind_speed: 12,
            },
          };
        },
      },
      get_forecast: {
        name: 'get_forecast',
        description: 'Get weather forecast',
        required: ['location'],
        optional: ['days'],
        handler: (params) => {
          const location = params.location || 'Delhi';
          return {
            success: true,
            data: {
              location,
              forecast: [
                { date: '2026-09-20', high: 33, low: 24, conditions: 'Sunny', rain_chance: 10 },
                { date: '2026-09-21', high: 32, low: 25, conditions: 'Partly Cloudy', rain_chance: 20 },
              ],
            },
          };
        },
      },
    },
  },
  'farm-qa': {
    id: 'farm-qa',
    name: 'Farm Q&A',
    intents: ['farm', 'animal', 'crop', 'cow', 'buffalo', 'goat', 'how many', 'my farm', 'my animals'],
    keywords: ['farm', 'animal', 'crop', 'cow', 'buffalo', 'goat', 'count', 'how many', 'show', 'my'],
    tools: {
      query_animals: {
        name: 'query_animals',
        description: 'Query animals',
        required: ['farmer_id'],
        optional: ['animal_type'],
        handler: (params) => {
          const farmerId = params.farmer_id;
          let animals = mockDatabase.animals.filter(a => a.farmer_id === farmerId);
          
          if (params.animal_type && params.animal_type !== 'all') {
            animals = animals.filter(a => a.type === params.animal_type);
          }
          
          const byType = animals.reduce((acc, a) => {
            acc[a.type] = (acc[a.type] || 0) + 1;
            return acc;
          }, {});
          
          return {
            success: true,
            data: {
              count: animals.length,
              by_type: byType,
              animals: animals.map(a => ({ name: a.name, type: a.type, breed: a.breed })),
            },
          };
        },
      },
      query_animal_details: {
        name: 'query_animal_details',
        description: 'Get animal details',
        required: ['animal_id'],
        handler: (params) => {
          const animal = mockDatabase.animals.find(a => 
            a.id === params.animal_id || a.name.toLowerCase() === params.animal_id.toLowerCase()
          );
          
          if (!animal) {
            return { success: false, error: 'Animal not found' };
          }
          
          return {
            success: true,
            data: { animal },
          };
        },
      },
    },
  },
  appointments: {
    id: 'appointments',
    name: 'Appointment Manager',
    intents: ['appointment', 'schedule', 'book', 'vet', 'doctor', 'visit'],
    keywords: ['appointment', 'schedule', 'book', 'vet', 'doctor', 'time', 'slot'],
    tools: {
      get_appointments: {
        name: 'get_appointments',
        description: 'Get appointments',
        required: ['farmer_id'],
        handler: (params) => {
          const apps = mockDatabase.appointments.filter(a => a.farmer_id === params.farmer_id);
          return {
            success: true,
            data: { count: apps.length, appointments: apps },
          };
        },
      },
      book_appointment: {
        name: 'book_appointment',
        description: 'Book appointment',
        required: ['farmer_id', 'type', 'date', 'time'],
        optional: ['reason'],
        handler: (params) => {
          return {
            success: true,
            data: {
              appointment_id: `apt_${Date.now()}`,
              status: 'confirmed',
              message: `Appointment booked for ${params.date} at ${params.time}.`,
            },
          };
        },
      },
    },
  },
  'market-prices': {
    id: 'market-prices',
    name: 'Market Prices',
    intents: ['price', 'market', 'mandi', 'rate', 'cost', 'sell', 'buy'],
    keywords: ['price', 'market', 'mandi', 'rate', 'cost', 'sell', 'buy', 'rupees'],
    tools: {
      get_market_prices: {
        name: 'get_market_prices',
        description: 'Get market prices',
        required: ['commodity'],
        optional: ['market'],
        handler: (params) => {
          return {
            success: true,
            data: {
              commodity: params.commodity,
              market: params.market || 'Delhi',
              min_price: 2100,
              max_price: 2300,
              modal_price: 2200,
              unit: 'per quintal',
            },
          };
        },
      },
    },
  },
};

// Enhanced Agent Loop
class EnhancedAgentLoop {
  constructor(sessionId, context, config = {}) {
    this.sessionId = sessionId;
    this.context = context;
    this.config = config;
    this.contextWindow = new ContextWindow(config.max_context_turns || 10);
    this.logger = new ConversationLogger(sessionId);
    this.waitingForClarification = null;
    this.partialParams = {};
  }

  async *run(userInput) {
    this.logger.info('AgentLoop', 'Processing user input', { input: userInput });
    
    // Check if waiting for clarification
    if (this.waitingForClarification) {
      this.logger.debug('AgentLoop', 'Resolving clarification', { waitingFor: this.waitingForClarification });
      
      const lower = userInput.toLowerCase().trim();
      if (['cancel', 'never mind', 'forget it', 'stop'].includes(lower)) {
        this.waitingForClarification = null;
        this.partialParams = {};
        yield {
          type: 'response',
          data: { content: 'No problem! Let me know if you need anything else.' },
        };
        return;
      }
      
      // Try to resolve
      const resolved = this.resolveClarification(userInput);
      if (resolved) {
        this.logger.info('AgentLoop', 'Clarification resolved', this.partialParams);
        yield { type: 'thinking', data: { message: 'Thank you! Processing your request...' } };
        
        // Execute with resolved params
        const result = await this.executeSkill(this.waitingForClarification.skillId, this.waitingForClarification.toolName, this.partialParams);
        yield* this.handleResult(result, this.waitingForClarification.skillId);
        
        this.waitingForClarification = null;
        return;
      }
    }
    
    // Add to context
    this.contextWindow.addUserTurn(userInput);
    
    // Step 1: Detect intent
    const intent = this.detectIntent(userInput);
    this.logger.info('IntentDetection', 'Intent detected', intent);
    
    yield { type: 'intent_detected', data: intent };
    
    if (!intent.skill) {
      yield { 
        type: 'clarification_needed', 
        data: { 
          message: 'I\'m not sure what you\'re asking about. I can help with weather, appointments, market prices, or farm information.',
          options: ['Weather', 'Appointments', 'Market Prices', 'Farm Information'],
        },
      };
      this.waitingForClarification = { type: 'disambiguation' };
      return;
    }
    
    // Low confidence - ask for clarification
    if (intent.confidence < 0.7) {
      this.logger.warn('IntentDetection', 'Low confidence', { confidence: intent.confidence });
      yield {
        type: 'clarification_needed',
        data: {
          message: `I'm not entirely sure. Did you mean ${intent.skill}?`,
          options: [intent.skill, 'Something else'],
        },
      };
      this.waitingForClarification = { type: 'disambiguation', originalSkill: intent.skill };
      return;
    }
    
    const skill = skills[intent.skill];
    if (!skill) {
      yield { type: 'error', data: { message: 'Skill not available' } };
      return;
    }
    
    yield { type: 'skill_loaded', data: skill };
    
    // Step 2: Select tool and extract parameters
    const toolName = intent.suggestedTool || Object.keys(skill.tools)[0];
    const tool = skill.tools[toolName];
    
    if (!tool) {
      yield { type: 'error', data: { message: 'Tool not found' } };
      return;
    }
    
    // Extract parameters
    const params = this.extractParameters(userInput, tool);
    this.logger.debug('ParameterExtraction', 'Extracted params', params);
    
    // Check for missing required params
    const missing = tool.required.filter(r => !(r in params) || params[r] == null);
    
    if (missing.length > 0) {
      this.logger.info('SlotFilling', 'Missing parameters', { missing });
      
      const firstMissing = missing[0];
      const prompt = this.getFollowUpPrompt(firstMissing);
      
      this.partialParams = { ...params };
      this.waitingForClarification = {
        type: 'missing_parameter',
        skillId: skill.id,
        toolName,
        param: firstMissing,
      };
      
      yield {
        type: 'follow_up',
        data: { message: prompt, missing_param: firstMissing },
      };
      return;
    }
    
    // Execute tool
    yield { type: 'tool_selected', data: { tool: toolName, params } };
    
    const result = await this.executeSkill(skill.id, toolName, params);
    yield* this.handleResult(result, skill.id);
  }
  
  detectIntent(input) {
    const lower = input.toLowerCase();
    const words = lower.split(/\s+/);
    
    let bestMatch = null;
    let bestScore = 0;
    
    for (const [skillId, skill] of Object.entries(skills)) {
      let score = 0;
      
      // Check intents
      for (const intent of skill.intents) {
        if (lower.includes(intent)) {
          score += 1.0;
        }
      }
      
      // Check keywords
      for (const keyword of skill.keywords) {
        if (words.includes(keyword) || lower.includes(keyword)) {
          score += 0.5;
        }
      }
      
      // Context boost - if same skill was used recently
      const lastSkill = this.contextWindow.getLastSkill();
      if (lastSkill === skillId) {
        score += 0.3;
      }
      
      if (score > bestScore) {
        bestScore = score;
        bestMatch = skill;
      }
    }
    
    if (bestMatch) {
      const suggestedTool = Object.keys(bestMatch.tools)[0];
      return {
        skill: bestMatch.id,
        confidence: Math.min(bestScore / 2, 1.0),
        suggestedTool,
      };
    }
    
    return { skill: null, confidence: 0 };
  }
  
  extractParameters(input, tool) {
    const params = { farmer_id: this.context.farmer_id };
    const lower = input.toLowerCase();
    
    // Extract location
    if (tool.required.includes('location') || tool.optional?.includes('location')) {
      const patterns = [
        /(?:in|at|for|near)\s+([A-Za-z\s]+)/i,
        /\b(Delhi|Mumbai|Bangalore|Chennai|Kolkata|Hyderabad|Pune|Ahmedabad|Jaipur|Lucknow)\b/i,
      ];
      
      for (const pattern of patterns) {
        const match = input.match(pattern);
        if (match) {
          params.location = (match[1] || match[0]).trim();
          break;
        }
      }
      
      if (!params.location && this.context.location) {
        params.location = this.context.location;
      }
    }
    
    // Extract animal type
    if (tool.required.includes('animal_type') || tool.optional?.includes('animal_type')) {
      const types = ['cow', 'buffalo', 'goat', 'sheep', 'chicken', 'bull'];
      for (const type of types) {
        if (lower.includes(type)) {
          params.animal_type = type;
          break;
        }
      }
    }
    
    // Extract commodity
    if (tool.required.includes('commodity') || tool.optional?.includes('commodity')) {
      const commodities = ['wheat', 'rice', 'cotton', 'corn', 'maize', 'sugarcane'];
      for (const comm of commodities) {
        if (lower.includes(comm)) {
          params.commodity = comm;
          break;
        }
      }
    }
    
    // Extract date
    if (tool.required.includes('date') || tool.optional?.includes('date')) {
      if (lower.includes('today')) {
        params.date = new Date().toISOString().split('T')[0];
      } else if (lower.includes('tomorrow')) {
        const tomorrow = new Date();
        tomorrow.setDate(tomorrow.getDate() + 1);
        params.date = tomorrow.toISOString().split('T')[0];
      }
    }
    
    // Extract time
    if (tool.required.includes('time') || tool.optional?.includes('time')) {
      const timeMatch = input.match(/(\d{1,2}):(\d{2})\s*(am|pm)?/i);
      if (timeMatch) {
        params.time = `${timeMatch[1].padStart(2, '0')}:${timeMatch[2]}`;
      }
    }
    
    // Extract animal name from context
    if (tool.required.includes('animal_id')) {
      const names = ['gauri', 'lakshmi', 'moti'];
      for (const name of names) {
        if (lower.includes(name)) {
          params.animal_id = name;
          break;
        }
      }
    }
    
    return params;
  }
  
  async executeSkill(skillId, toolName, params) {
    const skill = skills[skillId];
    const tool = skill.tools[toolName];
    
    try {
      const result = await tool.handler(params);
      return { success: true, ...result, skillId, toolName };
    } catch (error) {
      return { success: false, error: String(error), skillId, toolName };
    }
  }
  
  async *handleResult(result, skillId) {
    if (!result.success) {
      yield { type: 'error', data: { message: result.error } };
      return;
    }
    
    // Generate contextual response
    const response = this.generateResponse(result, skillId);
    
    // Add to context window
    this.contextWindow.addAssistantTurn(
      response,
      skillId,
      [{ tool_name: result.toolName, parameters: {}, result }]
    );
    
    yield { type: 'response', data: { content: response } };
    yield { type: 'complete', data: { success: true } };
  }
  
  generateResponse(result, skillId) {
    const data = result.data;
    
    switch (skillId) {
      case 'weather':
        if (data.forecast) {
          return `Here's the weather forecast for ${data.location}: ${data.forecast.map(f => 
            `${f.date}: ${f.conditions}, ${f.high}°C/${f.low}°C`
          ).join('; ')}.`;
        }
        return `Currently in ${data.location}: ${data.conditions}, ${data.temperature}°C, humidity ${data.humidity}%.`;
        
      case 'farm-qa':
        if (data.count !== undefined) {
          const breakdown = Object.entries(data.by_type || {})
            .map(([type, count]) => `${count} ${type}${count > 1 ? 's' : ''}`)
            .join(', ');
          return `You have ${data.count} animals total: ${breakdown}.`;
        }
        if (data.animal) {
          const a = data.animal;
          return `${a.name} is a ${a.breed} ${a.type}, health status: ${a.health_status}.`;
        }
        return `Here's what I found: ${JSON.stringify(data)}`;
        
      case 'appointments':
        if (data.appointments) {
          return `You have ${data.count} appointment(s). Next: ${data.appointments[0]?.date} at ${data.appointments[0]?.time}.`;
        }
        if (data.appointment_id) {
          return data.message;
        }
        return `Appointment information retrieved.`;
        
      case 'market-prices':
        return `Current ${data.commodity} prices at ${data.market}: ₹${data.min_price}-${data.max_price} ${data.unit} (modal: ₹${data.modal_price}).`;
        
      default:
        return `Here's the information: ${JSON.stringify(data)}`;
    }
  }
  
  getFollowUpPrompt(param) {
    const prompts = {
      location: 'Which location would you like to know about? (e.g., Delhi, Mumbai, or your village name)',
      date: 'Which date? (today, tomorrow, or YYYY-MM-DD)',
      time: 'What time? (e.g., 10:00 AM)',
      animal_type: 'Which type of animals? (cow, buffalo, goat, sheep)',
      commodity: 'Which commodity? (wheat, rice, cotton, corn)',
      farmer_id: 'Please provide your farmer ID or phone number.',
    };
    return prompts[param] || `Please provide the ${param}.`;
  }
  
  resolveClarification(input) {
    const lower = input.toLowerCase().trim();
    
    if (this.waitingForClarification?.type === 'disambiguation') {
      // Map input to skill
      const skillMap = {
        'weather': 'weather',
        'appointments': 'appointments',
        'appointment': 'appointments',
        'market prices': 'market-prices',
        'prices': 'market-prices',
        'farm': 'farm-qa',
        'farm information': 'farm-qa',
        'animals': 'farm-qa',
      };
      
      for (const [key, skill] of Object.entries(skillMap)) {
        if (lower.includes(key)) {
          this.waitingForClarification = { ...this.waitingForClarification, skillId: skill };
          return true;
        }
      }
      
      // Try number selection
      const num = parseInt(lower);
      if (!isNaN(num) && num >= 1 && num <= 4) {
        const skills_list = ['weather', 'appointments', 'market-prices', 'farm-qa'];
        this.waitingForClarification = { ...this.waitingForClarification, skillId: skills_list[num - 1] };
        return true;
      }
      
      return false;
    }
    
    if (this.waitingForClarification?.type === 'missing_parameter') {
      const param = this.waitingForClarification.param;
      
      // Simple validation
      if (input.length < 2) return false;
      
      // Store the value
      this.partialParams[param] = input;
      return true;
    }
    
    return false;
  }
  
  getContext() {
    return {
      turns: this.contextWindow.getRecentTurns(),
      toolHistory: this.contextWindow.getRecentTools(),
      lastSkill: this.contextWindow.getLastSkill(),
    };
  }
}

// Test conversations
const testConversations = [
  {
    name: 'Weather with Location Follow-up',
    farmerId: 'farmer_001',
    context: { location: 'Delhi', language: 'en' },
    turns: [
      { user: 'What\'s the weather like?', expectedSkill: 'weather', expectedFollowUp: true },
      { user: 'In Mumbai', expectedSkill: 'weather', expectedFollowUp: false },
      { user: 'And tomorrow?', expectedSkill: 'weather', expectedFollowUp: false },
    ],
  },
  {
    name: 'Farm Animal Queries',
    farmerId: 'farmer_001',
    context: { location: 'Delhi', language: 'en' },
    turns: [
      { user: 'How many animals do I have?', expectedSkill: 'farm-qa', expectedFollowUp: false },
      { user: 'Show me my cows', expectedSkill: 'farm-qa', expectedFollowUp: false },
      { user: 'What about Gauri?', expectedSkill: 'farm-qa', expectedFollowUp: false },
    ],
  },
  {
    name: 'Disambiguation Scenario',
    farmerId: 'farmer_001',
    context: { location: 'Delhi', language: 'en' },
    turns: [
      { user: 'I need help with something', expectedSkill: null, expectedFollowUp: true },
      { user: 'Weather', expectedSkill: 'weather', expectedFollowUp: true },
      { user: 'Delhi', expectedSkill: 'weather', expectedFollowUp: false },
    ],
  },
  {
    name: 'Complex Conversation',
    farmerId: 'farmer_001',
    context: { location: 'Delhi', language: 'en' },
    turns: [
      { user: 'Will it rain this week?', expectedSkill: 'weather', expectedFollowUp: false },
      { user: 'How about my animals?', expectedSkill: 'farm-qa', expectedFollowUp: false },
      { user: 'What\'s the price of wheat?', expectedSkill: 'market-prices', expectedFollowUp: false },
      { user: 'Book a vet appointment for tomorrow at 10', expectedSkill: 'appointments', expectedFollowUp: false },
    ],
  },
  {
    name: 'Incomplete and Vague',
    farmerId: 'farmer_001',
    context: { location: 'Delhi', language: 'en' },
    turns: [
      { user: 'Hmm...', expectedSkill: null, expectedFollowUp: true },
      { user: 'My farm', expectedSkill: 'farm-qa', expectedFollowUp: false },
      { user: 'How many', expectedSkill: 'farm-qa', expectedFollowUp: false },
    ],
  },
];

// Run tests
async function runTests() {
  console.log(`${colors.bright}${colors.cyan}`);
  console.log('╔════════════════════════════════════════════════════════════════╗');
  console.log('║     React Loop Skills - Conversation Test Runner              ║');
  console.log('╚════════════════════════════════════════════════════════════════╝');
  console.log(`${colors.reset}\n`);
  
  console.log(`${colors.yellow}Initializing system...${colors.reset}\n`);
  
  const results = [];
  
  for (let i = 0; i < testConversations.length; i++) {
    const conv = testConversations[i];
    
    console.log(`${colors.bright}${'='.repeat(80)}${colors.reset}`);
    console.log(`${colors.green}TEST ${i + 1}: ${conv.name}${colors.reset}`);
    console.log(`${colors.dim}Description: Testing ${conv.turns.length} turns${colors.reset}`);
    console.log(`${colors.bright}${'='.repeat(80)}${colors.reset}\n`);
    
    const agent = new EnhancedAgentLoop(
      `session_${i}`,
      { ...conv.context, farmer_id: conv.farmerId },
      { max_context_turns: 10 }
    );
    
    for (let turnIdx = 0; turnIdx < conv.turns.length; turnIdx++) {
      const turn = conv.turns[turnIdx];
      
      console.log(`${colors.cyan}--- Turn ${turnIdx + 1} ---${colors.reset}`);
      console.log(`${colors.yellow}User:${colors.reset} "${turn.user}"`);
      
      const events = [];
      let actualSkill = null;
      let actualFollowUp = false;
      
      for await (const event of agent.run(turn.user)) {
        events.push(event);
        
        if (event.type === 'skill_loaded') {
          actualSkill = event.data.id;
        }
        
        if (event.type === 'follow_up' || event.type === 'clarification_needed') {
          actualFollowUp = true;
          const msg = event.data?.message || event.data?.content || '';
          console.log(`${colors.magenta}Assistant:${colors.reset} "${msg.substring(0, 100)}${msg.length > 100 ? '...' : ''}"`);
          if (event.data?.options) {
            console.log(`${colors.dim}Options: ${event.data.options.join(', ')}${colors.reset}`);
          }
        }
        
        if (event.type === 'response') {
          const content = event.data?.content || event.data;
          if (typeof content === 'string') {
            console.log(`${colors.green}Assistant:${colors.reset} "${content.substring(0, 120)}${content.length > 120 ? '...' : ''}"`);
          }
        }
      }
      
      // Validate
      const errors = [];
      if (turn.expectedSkill && actualSkill !== turn.expectedSkill) {
        errors.push(`Expected '${turn.expectedSkill}', got '${actualSkill}'`);
      }
      if (turn.expectedFollowUp !== actualFollowUp) {
        errors.push(`Follow-up: expected ${turn.expectedFollowUp}, got ${actualFollowUp}`);
      }
      
      if (errors.length > 0) {
        console.log(`${colors.red}❌ Errors: ${errors.join(', ')}${colors.reset}`);
      } else {
        console.log(`${colors.green}✅ Pass${colors.reset}`);
      }
      
      results.push({
        conversation: conv.name,
        turn: turnIdx + 1,
        success: errors.length === 0,
        errors,
      });
      
      console.log();
    }
    
    // Show context
    const ctx = agent.getContext();
    console.log(`${colors.dim}Context: ${ctx.turns.length} turns, ${ctx.toolHistory.length} tool calls${colors.reset}`);
    console.log(`${colors.dim}Last skill: ${ctx.lastSkill || 'none'}${colors.reset}\n`);
  }
  
  // Summary
  console.log(`${colors.bright}${'='.repeat(80)}${colors.reset}`);
  console.log(`${colors.bright}TEST SUMMARY${colors.reset}`);
  console.log(`${colors.bright}${'='.repeat(80)}${colors.reset}\n`);
  
  const total = results.length;
  const passed = results.filter(r => r.success).length;
  const failed = total - passed;
  
  console.log(`Total Turns: ${total}`);
  console.log(`${colors.green}✅ Passed: ${passed} (${((passed/total)*100).toFixed(1)}%)${colors.reset}`);
  console.log(`${colors.red}❌ Failed: ${failed} (${((failed/total)*100).toFixed(1)}%)${colors.reset}\n`);
  
  if (failed > 0) {
    console.log(`${colors.red}Failed Tests:${colors.reset}`);
    results.filter(r => !r.success).forEach(r => {
      console.log(`  ${colors.red}•${colors.reset} ${r.conversation} - Turn ${r.turn}: ${r.errors.join(', ')}`);
    });
  }
  
  console.log(`\n${colors.green}Test run complete!${colors.reset}\n`);
}

// Run
runTests().catch(err => {
  console.error('Test failed:', err);
  process.exit(1);
});
