#!/usr/bin/env node
/**
 * React Loop Skills - Simple Local Server (Updated with Fixes)
 * Incorporates fixes from fix/appointment-session-and-weather-followup-v2
 */

const express = require('express');
const cors = require('cors');

const app = express();
const PORT = process.env.PORT || 3001;

// Middleware
app.use(cors());
app.use(express.json());

// In-memory database
const db = {
  farmers: [
    { id: 'farmer_001', name: 'Rajesh Kumar', phone: '9876543210', village: 'Khera', district: 'Muzaffarnagar', state: 'Uttar Pradesh' },
    { id: 'farmer_002', name: 'Amit Singh', phone: '9876543211', village: 'Rampur', district: 'Meerut', state: 'Uttar Pradesh' },
  ],
  animals: [
    { id: 'animal_001', farmer_id: 'farmer_001', tag_number: 'COW001', name: 'Gauri', type: 'cow', breed: 'Sahiwal', health_status: 'healthy' },
    { id: 'animal_002', farmer_id: 'farmer_001', tag_number: 'BUF001', name: 'Lakshmi', type: 'buffalo', breed: 'Murrah', health_status: 'healthy' },
    { id: 'animal_003', farmer_id: 'farmer_001', tag_number: 'GOAT001', name: 'Moti', type: 'goat', breed: 'Jamunapari', health_status: 'healthy' },
  ],
  appointments: [
    { id: 'apt_001', farmer_id: 'farmer_001', type: 'veterinary', date: '2026-09-20', time: '10:00', status: 'confirmed', reason: 'Vaccination' },
  ],
  sessions: new Map(),
};

// FIX 1: Better intent detection with context awareness
function detectIntent(input, context = {}) {
  const lower = input.toLowerCase().trim();
  const words = lower.split(/\s+/).filter(w => w.length > 0);
  
  // FIX: Check for bare replies first (1-2 words that could be answers)
  const isBareReply = words.length <= 2 && !lower.match(/^(what|how|when|where|why|who|is|are|can|could|would|will|should)/);
  
  // FIX: If we have pending context from previous question, use that
  if (context.pendingQuestion && isBareReply) {
    console.log(`[Intent] Bare reply "${input}" answering pending question: ${context.pendingQuestion}`);
    return {
      skill: context.activeSkill,
      confidence: 0.95,
      isBareReply: true,
      answeringField: context.expectedField,
    };
  }
  
  let bestSkill = null;
  let bestScore = 0;
  
  const skills = {
    weather: {
      intents: ['weather', 'forecast', 'rain', 'temperature', 'will it rain', 'how hot', 'how cold'],
      keywords: ['weather', 'rain', 'sunny', 'cloudy', 'temperature', 'humidity', 'forecast'],
    },
    appointments: {
      intents: ['appointment', 'schedule', 'book', 'vet', 'doctor', 'visit', 'checkup'],
      keywords: ['appointment', 'schedule', 'book', 'vet', 'doctor', 'visit', 'time', 'slot'],
    },
    'farm-qa': {
      intents: ['farm', 'animal', 'crop', 'cow', 'buffalo', 'goat', 'how many', 'my farm', 'my animals', 'show me', 'tell me'],
      keywords: ['farm', 'animal', 'crop', 'cow', 'buffalo', 'goat', 'count', 'how many', 'show', 'my', 'total'],
    },
    'market-prices': {
      intents: ['price', 'market', 'mandi', 'rate', 'cost', 'sell', 'buy', 'rate'],
      keywords: ['price', 'market', 'mandi', 'rate', 'cost', 'sell', 'buy', 'rupees', 'quintal', 'kg'],
    },
  };
  
  // FIX: Check for explicit switch/cancel keywords
  const switchKeywords = ['switch', 'change', 'instead', 'different', 'cancel', 'stop', 'never mind', 'forget'];
  const hasSwitchKeyword = switchKeywords.some(k => lower.includes(k));
  
  // If no switch keyword and we have active skill, boost confidence for fragments
  if (!hasSwitchKeyword && context.activeSkill) {
    const lastSkill = skills[context.activeSkill];
    if (lastSkill) {
      // Check if input could be a continuation
      const couldBeContinuation = words.length <= 3 || 
        lastSkill.keywords.some(k => lower.includes(k));
      
      if (couldBeContinuation) {
        console.log(`[Intent] Continuing active skill: ${context.activeSkill}`);
        return {
          skill: context.activeSkill,
          confidence: 0.9,
          isContinuation: true,
        };
      }
    }
  }
  
  // Normal intent detection
  for (const [skillId, skill] of Object.entries(skills)) {
    let score = 0;
    
    // Intent matching
    for (const intent of skill.intents) {
      if (lower.includes(intent.toLowerCase())) {
        score += 1.0;
      }
    }
    
    // Keyword matching
    for (const keyword of skill.keywords) {
      if (words.includes(keyword) || lower.includes(keyword)) {
        score += 0.5;
      }
    }
    
    // FIX: Context boost - if same skill was used recently
    if (context.activeSkill === skillId) {
      score += 0.3;
    }
    
    if (score > bestScore) {
      bestScore = score;
      bestSkill = skillId;
    }
  }
  
  return {
    skill: bestSkill,
    confidence: Math.min(bestScore / 2, 1.0),
    isBareReply: false,
    hasSwitchKeyword,
  };
}

// FIX 2: Better confirmation signal classification (not just keyword matching)
function classifyConfirmation(input) {
  const lower = input.toLowerCase().trim();
  
  // FIX: Avoid misfires on words containing yes/no/cancel/submit
  // e.g., "enough" contains "no", "yesterday" contains "yes"
  const words = lower.split(/\s+/);
  
  // Check for standalone confirmation words
  const confirmWords = ['yes', 'yeah', 'yep', 'correct', 'right', 'ok', 'okay', 'sure', 'submit', 'book', 'save'];
  const denyWords = ['no', 'nope', 'nah', 'wrong', 'incorrect', 'cancel', 'stop', 'forget'];
  
  for (const word of words) {
    if (confirmWords.includes(word)) return 'yes';
    if (denyWords.includes(word)) return 'no';
  }
  
  // Check for phrases
  if (lower.match(/^(yes|yeah|yep|correct|right|ok|okay)\b/)) return 'yes';
  if (lower.match(/^(no|nope|nah|wrong|incorrect|cancel|stop)\b/)) return 'no';
  if (lower.match(/\b(submit|save|book)\b/)) return 'submit';
  if (lower.match(/\b(cancel|stop|forget|never mind)\b/)) return 'cancel';
  
  return null;
}

// FIX 3: Parameter extraction with pending question context
function extractParameters(input, skill, context = {}) {
  const params = { farmer_id: context.farmer_id };
  const lower = input.toLowerCase().trim();
  
  // FIX: If answering a pending question, use context to extract
  if (context.expectedField && context.pendingQuestion) {
    console.log(`[Extract] Using context for field: ${context.expectedField}`);
    
    switch (context.expectedField) {
      case 'location':
        // Bare reply like "Delhi" or "In Mumbai" should extract just the location
        params.location = input.replace(/^(in|at|for)\s+/i, '').trim();
        break;
      case 'commodity':
        params.commodity = lower.replace(/^(what is|show me|tell me)\s+/, '').replace(/\s+(price|rate|cost).*$/, '').trim();
        break;
      case 'animal_type':
        const types = ['cow', 'buffalo', 'goat', 'sheep', 'chicken'];
        for (const type of types) {
          if (lower.includes(type)) {
            params.animal_type = type;
            break;
          }
        }
        if (!params.animal_type) params.animal_type = 'all';
        break;
      case 'date':
        // Handle relative dates
        if (lower === 'today') {
          params.date = new Date().toISOString().split('T')[0];
        } else if (lower === 'tomorrow') {
          const tomorrow = new Date();
          tomorrow.setDate(tomorrow.getDate() + 1);
          params.date = tomorrow.toISOString().split('T')[0];
        } else {
          // Try to parse date formats
          const dateMatch = input.match(/(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{2,4})/);
          if (dateMatch) {
            params.date = `${dateMatch[3].length === 2 ? '20' + dateMatch[3] : dateMatch[3]}-${dateMatch[2].padStart(2, '0')}-${dateMatch[1].padStart(2, '0')}`;
          } else {
            params.date = input.trim();
          }
        }
        break;
      case 'time':
        const timeMatch = input.match(/(\d{1,2}):(\d{2})\s*(am|pm)?/i);
        if (timeMatch) {
          params.time = `${timeMatch[1].padStart(2, '0')}:${timeMatch[2]}`;
        } else {
          params.time = input.trim();
        }
        break;
      default:
        params[context.expectedField] = input.trim();
    }
    
    return params;
  }
  
  // Normal extraction with better patterns
  
  // FIX: Better location extraction - only match place names, not generic text
  if (lower.includes('weather') || lower.includes('forecast')) {
    // Look for location patterns but exclude "is the" etc.
    const locationPatterns = [
      /(?:in|at|for)\s+([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)/,  // Capitalized place names
      /\b(Delhi|Mumbai|Bangalore|Chennai|Kolkata|Hyderabad|Pune|Ahmedabad|Jaipur|Lucknow|Agra|Varanasi|Noida|Gurgaon)\b/i,
    ];
    
    for (const pattern of locationPatterns) {
      const match = input.match(pattern);
      if (match) {
        const candidate = match[1] || match[0];
        // Filter out non-location words
        if (!candidate.match(/\b(is|the|a|an|and|or|but)\b/i)) {
          params.location = candidate.trim();
          break;
        }
      }
    }
    
    // Default location from context
    if (!params.location && context.location) {
      params.location = context.location;
    }
  }
  
  // Animal type extraction
  if (lower.includes('cow') || lower.includes('buffalo') || lower.includes('goat')) {
    const types = ['cow', 'buffalo', 'goat', 'sheep', 'chicken', 'bull'];
    for (const type of types) {
      if (lower.includes(type)) {
        params.animal_type = type;
        break;
      }
    }
  }
  
  // Commodity extraction
  if (lower.includes('price') || lower.includes('rate') || lower.includes('cost')) {
    const commodities = ['wheat', 'rice', 'cotton', 'corn', 'maize', 'sugarcane', 'pulses', 'barley'];
    for (const comm of commodities) {
      if (lower.includes(comm)) {
        params.commodity = comm;
        break;
      }
    }
    // Remove price/rate/cost words
    if (!params.commodity) {
      params.commodity = lower.replace(/\s+(price|rate|cost|of)\s+/g, ' ').trim().split(/\s+/)[0];
    }
  }
  
  // Date extraction
  if (lower === 'today') {
    params.date = new Date().toISOString().split('T')[0];
  } else if (lower === 'tomorrow') {
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    params.date = tomorrow.toISOString().split('T')[0];
  } else if (lower === 'next week') {
    const nextWeek = new Date();
    nextWeek.setDate(nextWeek.getDate() + 7);
    params.date = nextWeek.toISOString().split('T')[0];
  }
  
  // Time extraction
  const timeMatch = input.match(/(\d{1,2}):(\d{2})\s*(am|pm)?/i);
  if (timeMatch) {
    params.time = timeMatch[1].padStart(2, '0') + ':' + timeMatch[2];
  }
  
  return params;
}

// Tool handlers
const tools = {
  query_animals: (params) => {
    let animals = db.animals.filter(a => a.farmer_id === params.farmer_id);
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
  
  get_current_weather: (params) => {
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
  
  get_appointments: (params) => {
    const apps = db.appointments.filter(a => a.farmer_id === params.farmer_id);
    return {
      success: true,
      data: { count: apps.length, appointments: apps },
    };
  },
  
  book_appointment: (params) => {
    return {
      success: true,
      data: {
        appointment_id: `apt_${Date.now()}`,
        status: 'confirmed',
        message: `Appointment booked for ${params.date} at ${params.time}.`,
      },
    };
  },
  
  get_market_prices: (params) => {
    const commodity = params.commodity || 'wheat';
    return {
      success: true,
      data: {
        commodity,
        market: params.market || 'Delhi',
        min_price: 2100,
        max_price: 2300,
        modal_price: 2200,
        unit: 'per quintal',
      },
    };
  },
};

// Health check
app.get('/health', (req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

// Get all skills
app.get('/skills', (req, res) => {
  res.json({
    skills: [
      { id: 'weather', name: 'Weather Service', description: 'Get weather information' },
      { id: 'appointments', name: 'Appointment Manager', description: 'Manage appointments' },
      { id: 'farm-qa', name: 'Farm Q&A', description: 'Answer farm questions' },
      { id: 'market-prices', name: 'Market Prices', description: 'Get market prices' },
    ],
  });
});

// Create chat session
app.post('/farmers/:farmerId/chat/session', (req, res) => {
  const sessionId = `sess_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  db.sessions.set(sessionId, {
    id: sessionId,
    farmer_id: req.params.farmerId,
    messages: [],
    context: {
      activeSkill: null,
      expectedField: null,
      pendingQuestion: null,
      collectedParams: {},
    },
    created_at: new Date().toISOString(),
  });
  res.json({ session: { id: sessionId } });
});

// MAIN CHAT ENDPOINT (with fixes)
app.post('/farmers/:farmerId/chat/turn', async (req, res) => {
  try {
    const { farmerId } = req.params;
    const { session_id, text, language = 'en-IN' } = req.body;
    
    console.log(`\n[Chat Turn] Farmer: ${farmerId}`);
    console.log(`[Chat Turn] User: "${text}"`);
    
    if (!text) {
      return res.status(400).json({ error: 'text is required' });
    }
    
    // Get or create session
    let session = db.sessions.get(session_id);
    if (!session) {
      session = {
        id: session_id || `sess_${Date.now()}`,
        farmer_id: farmerId,
        messages: [],
        context: {
          activeSkill: null,
          expectedField: null,
          pendingQuestion: null,
          collectedParams: { farmer_id: farmerId },
        },
      };
      db.sessions.set(session.id, session);
    }
    
    // FIX 4: Session continuation - clear submitted flag if present
    if (session.submitted) {
      console.log('[Session] Previous booking submitted, starting fresh');
      session.context = {
        activeSkill: null,
        expectedField: null,
        pendingQuestion: null,
        collectedParams: { farmer_id: farmerId },
      };
      session.submitted = false;
    }
    
    // Add user message
    session.messages.push({
      role: 'user',
      content: text,
      timestamp: new Date().toISOString(),
    });
    
    // Detect intent with context
    const intent = detectIntent(text, {
      activeSkill: session.context.activeSkill,
      expectedField: session.context.expectedField,
      pendingQuestion: session.context.pendingQuestion,
      farmer_id: farmerId,
      location: session.context.collectedParams.location,
    });
    
    console.log(`[Intent] Skill: ${intent.skill}, Confidence: ${(intent.confidence * 100).toFixed(0)}%`);
    console.log(`[Intent] Is bare reply: ${intent.isBareReply}, Is continuation: ${intent.isContinuation}`);
    
    // Check for confirmation signals
    const confirmation = classifyConfirmation(text);
    if (confirmation) {
      console.log(`[Confirmation] Detected: ${confirmation}`);
    }
    
    // Determine skill
    let detectedSkill = intent.skill;
    let requiredFollowUp = false;
    let expectedField = null;
    let responseText = '';
    
    // FIX: Handle bare replies with pending questions
    if (intent.isBareReply && session.context.expectedField) {
      console.log(`[Flow] Bare reply answering ${session.context.expectedField}`);
      detectedSkill = session.context.activeSkill;
    }
    
    // Extract parameters with context
    const params = extractParameters(text, detectedSkill, {
      ...session.context,
      farmer_id: farmerId,
      expectedField: session.context.expectedField,
      pendingQuestion: session.context.pendingQuestion,
    });
    
    // Merge with collected params
    Object.assign(session.context.collectedParams, params);
    
    // Execute skill
    if (detectedSkill === 'farm-qa') {
      if (text.toLowerCase().includes('how many') || text.toLowerCase().includes('count')) {
        const animalType = params.animal_type || 'all';
        const result = tools.query_animals({ 
          farmer_id: farmerId, 
          animal_type: animalType 
        });
        if (result.success) {
          const breakdown = Object.entries(result.data.by_type)
            .map(([type, count]) => `${count} ${type}${count > 1 ? 's' : ''}`)
            .join(', ');
          responseText = `You have ${result.data.count} animals total: ${breakdown}.`;
        }
      } else if (text.toLowerCase().includes('cow') || text.toLowerCase().includes('buffalo')) {
        // Handle "Show my cows" with filter
        const result = tools.query_animals({ 
          farmer_id: farmerId, 
          animal_type: params.animal_type || 'all'
        });
        if (result.success) {
          const breakdown = Object.entries(result.data.by_type)
            .map(([type, count]) => `${count} ${type}${count > 1 ? 's' : ''}`)
            .join(', ');
          responseText = `You have ${result.data.count} animals: ${breakdown}.`;
        }
      } else {
        responseText = "I can help you with information about your farm. You can ask about your animals, crops, or farm details.";
        requiredFollowUp = true;
      }
    } else if (detectedSkill === 'weather') {
      const location = session.context.collectedParams.location;
      
      if (!location && !params.location) {
        // FIX: Ask for location instead of using default
        responseText = "Which location would you like the weather for?";
        requiredFollowUp = true;
        expectedField = 'location';
        session.context.activeSkill = 'weather';
        session.context.expectedField = 'location';
        session.context.pendingQuestion = 'location';
      } else {
        const loc = params.location || location;
        const result = tools.get_current_weather({ location: loc });
        if (result.success) {
          responseText = `Currently in ${result.data.location}: ${result.data.conditions}, ${result.data.temperature}°C, humidity ${result.data.humidity}%.`;
          // Clear pending after successful response
          session.context.expectedField = null;
          session.context.pendingQuestion = null;
        }
      }
    } else if (detectedSkill === 'appointments') {
      if (confirmation === 'submit') {
        const result = tools.book_appointment(session.context.collectedParams);
        if (result.success) {
          responseText = result.data.message;
          session.submitted = true;  // Mark as submitted
          session.context.activeSkill = null;
        }
      } else if (text.toLowerCase().includes('book')) {
        responseText = "I can help you book an appointment. What type of appointment do you need? (veterinary, agricultural, or consultation)";
        requiredFollowUp = true;
        expectedField = 'appointment_type';
        session.context.activeSkill = 'appointments';
        session.context.expectedField = 'appointment_type';
      } else {
        const result = tools.get_appointments({ farmer_id: farmerId });
        if (result.success) {
          responseText = `You have ${result.data.count} appointment(s).`;
        }
      }
    } else if (detectedSkill === 'market-prices') {
      if (!params.commodity && !session.context.collectedParams.commodity) {
        responseText = "Which commodity are you asking about? (wheat, rice, cotton, etc.)";
        requiredFollowUp = true;
        expectedField = 'commodity';
        session.context.activeSkill = 'market-prices';
      } else {
        const commodity = params.commodity || session.context.collectedParams.commodity;
        const result = tools.get_market_prices({ commodity, farmer_id: farmerId });
        if (result.success) {
          responseText = `Current ${result.data.commodity} prices at ${result.data.market}: ₹${result.data.min_price}-${result.data.max_price} ${result.data.unit} (modal: ₹${result.data.modal_price}).`;
          session.context.activeSkill = null;
        }
      }
    } else {
      responseText = "I'm not sure what you're asking about. I can help with weather, appointments, market prices, or farm information.";
      requiredFollowUp = true;
      detectedSkill = null;
    }
    
    // Update context
    if (detectedSkill && !requiredFollowUp) {
      session.context.activeSkill = detectedSkill;
    }
    
    // Add assistant message
    session.messages.push({
      role: 'assistant',
      content: responseText,
      skill_id: detectedSkill,
      timestamp: new Date().toISOString(),
    });
    
    console.log(`[Response] "${responseText.substring(0, 100)}${responseText.length > 100 ? '...' : ''}"`);
    console.log(`[Follow-up] ${requiredFollowUp ? 'Required' : 'Not needed'}`);
    if (expectedField) {
      console.log(`[Expected Field] ${expectedField}`);
    }
    
    // Build response
    const response = {
      agent: detectedSkill || 'query_agent',
      intent: detectedSkill,
      result: {
        answer: responseText,
        sql: null,
        data: null,
      },
      reply_text: responseText,
      timing: { total_ms: 0 },
      _meta: {
        confidence: intent.confidence,
        required_follow_up: requiredFollowUp,
        expected_field: expectedField,
        is_bare_reply: intent.isBareReply,
        is_continuation: intent.isContinuation,
        confirmation_signal: confirmation,
        session_context: {
          active_skill: session.context.activeSkill,
          collected_params: Object.keys(session.context.collectedParams),
        },
      },
    };
    
    res.json(response);
  } catch (error) {
    console.error('[Chat Turn Error]', error);
    res.status(500).json({ error: error.message });
  }
});

// Get farmer
app.get('/farmers/:farmerId', (req, res) => {
  const farmer = db.farmers.find(f => f.id === req.params.farmerId);
  if (!farmer) {
    return res.status(404).json({ error: 'Farmer not found' });
  }
  res.json({ farmer });
});

// Get farmer animals
app.get('/farmers/:farmerId/animals', (req, res) => {
  const animals = db.animals.filter(a => a.farmer_id === req.params.farmerId);
  res.json({ animals });
});

// Get farmer appointments
app.get('/farmers/:farmerId/appointments', (req, res) => {
  const appointments = db.appointments.filter(a => a.farmer_id === req.params.farmerId);
  res.json({ appointments });
});

// Start server
app.listen(PORT, () => {
  console.log('='.repeat(70));
  console.log('🎉 React Loop Skills - Local Server (with Fixes from v2 branch)');
  console.log('='.repeat(70));
  console.log(`\n📍 Server running on http://localhost:${PORT}`);
  console.log(`\n📚 Available endpoints:`);
  console.log(`  GET  /health                          - Health check`);
  console.log(`  GET  /skills                          - List all skills`);
  console.log(`  POST /farmers/:id/chat/session        - Create chat session`);
  console.log(`  POST /farmers/:id/chat/turn           - Send chat message ⭐`);
  console.log(`  GET  /farmers/:id                     - Get farmer data`);
  console.log(`  GET  /farmers/:id/animals             - Get animals`);
  console.log(`  GET  /farmers/:id/appointments        - Get appointments`);
  console.log(`\n✅ FIXES APPLIED:`);
  console.log(`  ✓ Better intent detection with context awareness`);
  console.log(`  ✓ Bare reply handling (1-2 word answers)`);
  console.log(`  ✓ Confirmation signal classification (no keyword misfires)`);
  console.log(`  ✓ Parameter extraction with pending questions`);
  console.log(`  ✓ Session continuation after submit`);
  console.log(`  ✓ Location extraction fixed (no "is the" bug)`);
  console.log('\n' + '='.repeat(70));
});
