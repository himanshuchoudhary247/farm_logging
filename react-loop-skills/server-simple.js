#!/usr/bin/env node
/**
 * React Loop Skills - Simple Local Server
 * Standalone server with mock data (no build required)
 */

const express = require('express');
const cors = require('cors');
const path = require('path');
const fs = require('fs');

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

// Simple intent detection
function detectIntent(input) {
  const lower = input.toLowerCase();
  const words = lower.split(/\s+/);
  
  let bestSkill = null;
  let bestScore = 0;
  
  const skills = {
    weather: {
      intents: ['weather', 'forecast', 'rain', 'temperature', 'will it rain'],
      keywords: ['weather', 'rain', 'sunny', 'cloudy', 'temperature'],
    },
    appointments: {
      intents: ['appointment', 'schedule', 'book', 'vet', 'doctor'],
      keywords: ['appointment', 'schedule', 'book', 'vet', 'time'],
    },
    'farm-qa': {
      intents: ['farm', 'animal', 'cow', 'buffalo', 'how many', 'my animals'],
      keywords: ['farm', 'animal', 'cow', 'buffalo', 'count', 'my'],
    },
    'market-prices': {
      intents: ['price', 'market', 'rate', 'cost', 'sell', 'buy'],
      keywords: ['price', 'market', 'rate', 'cost', 'sell'],
    },
  };
  
  for (const [skillId, skill] of Object.entries(skills)) {
    let score = 0;
    
    for (const intent of skill.intents) {
      if (lower.includes(intent)) score += 1.0;
    }
    
    for (const keyword of skill.keywords) {
      if (words.includes(keyword)) score += 0.5;
    }
    
    if (score > bestScore) {
      bestScore = score;
      bestSkill = skillId;
    }
  }
  
  return {
    skill: bestSkill,
    confidence: Math.min(bestScore / 2, 1.0),
  };
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

// Active flow tracking
let activeFlow = null;

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
    created_at: new Date().toISOString(),
  });
  res.json({ session: { id: sessionId } });
});

// MAIN CHAT ENDPOINT
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
      };
      db.sessions.set(session.id, session);
    }
    
    // Add user message
    session.messages.push({
      role: 'user',
      content: text,
      timestamp: new Date().toISOString(),
    });
    
    // Check for active flow (intent persistence)
    const isShortFragment = text.trim().split(/\s+/).length <= 3;
    const switchKeywords = ['switch', 'change', 'instead', 'different', 'cancel', 'stop'];
    const hasSwitchKeyword = switchKeywords.some(k => text.toLowerCase().includes(k));
    
    let intent;
    let shouldUseActiveFlow = false;
    
    if (activeFlow && isShortFragment && !hasSwitchKeyword) {
      // Continue with active flow
      shouldUseActiveFlow = true;
      intent = { skill: activeFlow.skillId, confidence: 0.9 };
      console.log(`[Intent] Continuing flow: ${activeFlow.skillId}`);
    } else {
      // Detect new intent
      intent = detectIntent(text);
      console.log(`[Intent] Detected: ${intent.skill} (${(intent.confidence * 100).toFixed(0)}%)`);
      
      // Start new flow
      if (intent.skill && intent.confidence > 0.5) {
        activeFlow = {
          skillId: intent.skill,
          startedAt: Date.now(),
          params: { farmer_id: farmerId },
        };
      }
    }
    
    // Build response
    let responseText = '';
    let detectedSkill = intent.skill;
    let requiredFollowUp = false;
    
    // Execute appropriate tool
    if (intent.skill === 'farm-qa') {
      if (text.toLowerCase().includes('how many') || text.toLowerCase().includes('count')) {
        const animalType = text.toLowerCase().includes('cow') ? 'cow' : 
                          text.toLowerCase().includes('buffalo') ? 'buffalo' : 'all';
        
        const result = tools.query_animals({ farmer_id: farmerId, animal_type: animalType });
        if (result.success) {
          const breakdown = Object.entries(result.data.by_type)
            .map(([type, count]) => `${count} ${type}${count > 1 ? 's' : ''}`)
            .join(', ');
          responseText = `You have ${result.data.count} animals total: ${breakdown}.`;
        }
      } else {
        responseText = "I can help you with information about your farm. You can ask about your animals, crops, or farm details.";
        requiredFollowUp = true;
      }
    } else if (intent.skill === 'weather') {
      const locationMatch = text.match(/(?:in|at|for)\s+([A-Za-z\s]+)/i);
      let location = locationMatch ? locationMatch[1].trim() : null;
      
      // Check if fragment referring to previous location
      if (!location && shouldUseActiveFlow && activeFlow?.params?.location) {
        location = activeFlow.params.location;
      }
      
      if (!location && isShortFragment) {
        responseText = "Which location would you like the weather for?";
        requiredFollowUp = true;
      } else {
        const result = tools.get_current_weather({ location: location || 'Delhi' });
        if (result.success) {
          responseText = `Currently in ${result.data.location}: ${result.data.conditions}, ${result.data.temperature}°C, humidity ${result.data.humidity}%.`;
          if (activeFlow) activeFlow.params.location = result.data.location;
        }
      }
    } else if (intent.skill === 'appointments') {
      if (text.toLowerCase().includes('book')) {
        responseText = "I can help you book an appointment. What type of appointment do you need? (veterinary, agricultural, or consultation)";
        requiredFollowUp = true;
      } else {
        const result = tools.get_appointments({ farmer_id: farmerId });
        if (result.success) {
          responseText = `You have ${result.data.count} appointment(s).`;
        }
      }
    } else if (intent.skill === 'market-prices') {
      const commodityMatch = text.toLowerCase().match(/(wheat|rice|cotton|corn)/);
      const commodity = commodityMatch ? commodityMatch[1] : 'wheat';
      
      const result = tools.get_market_prices({ commodity, farmer_id: farmerId });
      if (result.success) {
        responseText = `Current ${result.data.commodity} prices at ${result.data.market}: ₹${result.data.min_price}-${result.data.max_price} ${result.data.unit} (modal: ₹${result.data.modal_price}).`;
      }
    } else {
      responseText = "I'm not sure what you're asking about. I can help with weather, appointments, market prices, or farm information.";
      requiredFollowUp = true;
      detectedSkill = null;
    }
    
    // Add assistant message
    session.messages.push({
      role: 'assistant',
      content: responseText,
      skill_id: detectedSkill,
      timestamp: new Date().toISOString(),
    });
    
    // Update flow
    if (activeFlow && !requiredFollowUp && !shouldUseActiveFlow) {
      console.log('[Flow] Completed: ' + activeFlow.skillId);
      activeFlow = null;
    }
    
    console.log(`[Response] "${responseText.substring(0, 100)}${responseText.length > 100 ? '...' : ''}"`);
    console.log(`[Follow-up] ${requiredFollowUp ? 'Required' : 'Not needed'}`);
    
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
        is_flow_continuation: shouldUseActiveFlow,
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
  console.log('🎉 React Loop Skills - Local Server (Simple Mode)');
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
  console.log(`\n🧪 Test commands:`);
  console.log(`  curl http://localhost:${PORT}/health`);
  console.log(`  curl http://localhost:${PORT}/skills`);
  console.log(`  curl http://localhost:${PORT}/farmers/farmer_001`);
  console.log('\n  # Create session and chat');
  console.log('  curl -X POST http://localhost:' + PORT + '/farmers/farmer_001/chat/session');
  console.log('  curl -X POST http://localhost:' + PORT + '/farmers/farmer_001/chat/turn');
  console.log('\n  # Test intent persistence (fragments):');
  console.log('  curl -X POST http://localhost:' + PORT + '/farmers/farmer_001/chat/turn');
  console.log('  curl -X POST http://localhost:' + PORT + '/farmers/farmer_001/chat/turn');
  console.log('\n' + '='.repeat(70));
});
