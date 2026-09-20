import express, { Request, Response, NextFunction } from 'express';
import cors from 'cors';
import path from 'path';
import { v4 as uuidv4 } from 'uuid';
import { createDatabase, getDatabase } from './database';
import { createSkillRegistry, getSkillRegistry } from '../core/SkillRegistry';
import { createToolRegistry, getToolRegistry } from '../core/ToolRegistry';
import { createSessionManager, getSessionManager } from '../adk/SessionManager';
import { createIntentMatcher, getIntentMatcher } from '../core/IntentMatcher';
import { createEnhancedAgentLoop } from '../adk/EnhancedAgentLoop';
import { createIntentPersistenceManager } from '../adk/IntentPersistence';

// Import skills
import * as WeatherSkill from '../skills/weather';
import * as AppointmentsSkill from '../skills/appointments';
import * as MarketPricesSkill from '../skills/market-prices';
import * as FarmQASkill from '../skills/farm-qa';

const app = express();
const PORT = process.env.PORT || 3001;

// Middleware
app.use(cors());
app.use(express.json());

// Initialize database and skills
async function initialize() {
  console.log('🚀 Starting React Loop Skills Local Server...\n');

  // Initialize database
  const db = createDatabase('./data/local.db');
  await db.initialize();
  await db.seedData();

  // Initialize registries
  const skillRegistry = createSkillRegistry({ skills_directory: './src/skills' });
  const toolRegistry = createToolRegistry();
  const intentMatcher = createIntentMatcher();
  const sessionManager = createSessionManager();
  const persistenceManager = createIntentPersistenceManager();

  // Register skills
  const skills = [
    {
      metadata: {
        id: 'weather',
        name: 'Weather Service',
        version: '1.0.0',
        description: 'Get weather information',
        category: 'information',
        tags: ['weather', 'forecast', 'rain', 'temperature', 'climate'],
      },
      activation: {
        intents: ['weather', 'forecast', 'rain', 'temperature', 'will it rain', 'how hot', 'how cold', 'weather report', 'climate'],
        confidence_threshold: 0.6,
        keywords: ['weather', 'rain', 'sunny', 'cloudy', 'storm', 'temperature', 'humidity', 'forecast'],
      },
      tools: ['get_current_weather', 'get_forecast', 'check_weather_alerts'],
      dependencies: [],
      config: {},
    },
    {
      metadata: {
        id: 'appointments',
        name: 'Appointment Manager',
        version: '1.0.0',
        description: 'Manage appointments',
        category: 'management',
        tags: ['appointment', 'vet', 'veterinary', 'doctor', 'schedule', 'booking'],
      },
      activation: {
        intents: ['appointment', 'schedule', 'book', 'vet', 'veterinary', 'doctor', 'visit', 'checkup'],
        confidence_threshold: 0.6,
        keywords: ['appointment', 'schedule', 'book', 'vet', 'doctor', 'visit', 'time', 'slot'],
      },
      tools: ['get_appointments', 'book_appointment', 'cancel_appointment', 'check_availability'],
      dependencies: [],
      config: {},
    },
    {
      metadata: {
        id: 'market-prices',
        name: 'Market Prices',
        version: '1.0.0',
        description: 'Get market prices',
        category: 'information',
        tags: ['market', 'price', 'mandi', 'commodity', 'crop', 'sell', 'buy'],
      },
      activation: {
        intents: ['price', 'market', 'mandi', 'rate', 'cost', 'sell', 'buy', 'commodity'],
        confidence_threshold: 0.6,
        keywords: ['price', 'market', 'mandi', 'rate', 'cost', 'sell', 'buy', 'rupees', 'rs', 'quintal', 'kg'],
      },
      tools: ['get_market_prices', 'get_price_history', 'compare_prices'],
      dependencies: [],
      config: {},
    },
    {
      metadata: {
        id: 'farm-qa',
        name: 'Farm Q&A',
        version: '1.0.0',
        description: 'Answer farm questions',
        category: 'information',
        tags: ['farm', 'animal', 'crop', 'qna', 'query', 'database'],
      },
      activation: {
        intents: ['farm', 'animal', 'crop', 'cow', 'buffalo', 'goat', 'sheep', 'field', 'land', 'farmer', 'my farm', 'my animals', 'my crops', 'show me', 'tell me about', 'what is', 'how many', 'when did', 'where is'],
        confidence_threshold: 0.5,
        keywords: ['farm', 'animal', 'crop', 'cow', 'buffalo', 'goat', 'sheep', 'field', 'land', 'farmer', 'health', 'vaccination', 'milk', 'production', 'area', 'size', 'count', 'total', 'my'],
      },
      tools: ['query_farmer_profile', 'query_animals', 'query_animal_details', 'query_crops', 'query_farm_land', 'query_health_records', 'query_production_data', 'query_vaccination_schedule', 'ask_database', 'get_summary'],
      dependencies: [],
      config: {},
    },
  ];

  skills.forEach(skill => skillRegistry.register(skill));

  // Register tools
  Object.values(WeatherSkill).forEach((tool: any) => {
    if (tool?.schema) toolRegistry.register(tool, 'weather');
  });
  Object.values(AppointmentsSkill).forEach((tool: any) => {
    if (tool?.schema) toolRegistry.register(tool, 'appointments');
  });
  Object.values(MarketPricesSkill).forEach((tool: any) => {
    if (tool?.schema) toolRegistry.register(tool, 'market-prices');
  });
  Object.values(FarmQASkill).forEach((tool: any) => {
    if (tool?.schema) toolRegistry.register(tool, 'farm-qa');
  });

  console.log(`✅ Loaded ${skills.length} skills`);
  console.log(`✅ Registered ${toolRegistry.getAll().length} tools`);
  console.log(`✅ Server ready on http://localhost:${PORT}\n`);
}

// Health check
app.get('/health', (req: Request, res: Response) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

// Get all skills
app.get('/skills', (req: Request, res: Response) => {
  try {
    const registry = getSkillRegistry();
    const skills = registry.getAll();
    res.json({ skills });
  } catch (error) {
    res.status(500).json({ error: 'Failed to get skills' });
  }
});

// Get skill by ID
app.get('/skills/:skillId', (req: Request, res: Response) => {
  try {
    const registry = getSkillRegistry();
    const skill = registry.get(req.params.skillId);
    if (!skill) {
      return res.status(404).json({ error: 'Skill not found' });
    }
    res.json({ skill });
  } catch (error) {
    res.status(500).json({ error: 'Failed to get skill' });
  }
});

// Create chat session
app.post('/farmers/:farmerId/chat/session', (req: Request, res: Response) => {
  try {
    const sessionManager = getSessionManager();
    const session = sessionManager.create({
      farmer_id: req.params.farmerId,
      ...req.body.context,
    });
    res.json({ session });
  } catch (error) {
    res.status(500).json({ error: 'Failed to create session' });
  }
});

// Chat turn - MAIN ENDPOINT
app.post('/farmers/:farmerId/chat/turn', async (req: Request, res: Response) => {
  try {
    const { farmerId } = req.params;
    const { session_id, text, language = 'en-IN', include_audio = false } = req.body;

    if (!text) {
      return res.status(400).json({ error: 'text is required' });
    }

    console.log(`\n[Chat Turn] Farmer: ${farmerId}, Session: ${session_id}`);
    console.log(`[Chat Turn] User: "${text}"`);

    // Get or create session
    const sessionManager = getSessionManager();
    let session = sessionManager.get(session_id);
    if (!session) {
      session = sessionManager.create({
        farmer_id: farmerId,
        language: language.split('-')[0],
      });
    }

    // Create agent with intent persistence
    const agent = createEnhancedAgentLoop(session, {
      max_context_turns: 10,
      enable_disambiguation: true,
      enable_followups: true,
      log_level: 'info',
    });

    // Run the turn and collect events
    const events: any[] = [];
    let responseText = '';
    let detectedSkill: string | null = null;
    let detectedIntent: string | null = null;
    let requiredFollowUp = false;

    for await (const event of agent.run(text)) {
      events.push(event);

      if (event.type === 'skill_loaded') {
        detectedSkill = event.data?.metadata?.id || null;
      }

      if (event.type === 'intent_detected') {
        detectedIntent = event.data?.primary_match?.skill || null;
      }

      if (event.type === 'follow_up' || event.type === 'clarification_needed') {
        requiredFollowUp = true;
        responseText = event.data?.message || event.data?.content || '';
      }

      if (event.type === 'response') {
        responseText = event.data?.content || event.data || '';
      }
    }

    // Get timing
    const timing = { total_ms: Date.now() - new Date(session.created_at).getTime() };

    console.log(`[Chat Turn] Response: "${responseText.substring(0, 100)}${responseText.length > 100 ? '...' : ''}"`);
    console.log(`[Chat Turn] Skill: ${detectedSkill}, Follow-up: ${requiredFollowUp}\n`);

    // Build response in flokiquser format
    const response: any = {
      agent: detectedSkill as any || 'query_agent',
      intent: detectedIntent,
      result: {
        answer: responseText,
        sql: null,
        data: null,
      },
      reply_text: responseText,
      timing,
      _meta: {
        events: events.map(e => ({ type: e.type, timestamp: e.timestamp })),
        required_follow_up: requiredFollowUp,
      },
    };

    // Add skill-specific result shaping
    if (detectedSkill === 'weather') {
      response.agent = 'weather_alert';
      response.result = {
        message: responseText,
        weather: { summary: responseText },
      };
    } else if (detectedSkill === 'appointments') {
      response.agent = 'appointment_supervisor';
      response.result = {
        response_text: responseText,
        session_id: session.id,
        state: requiredFollowUp ? 'collecting' : 'completed',
      };
    }

    res.json(response);
  } catch (error) {
    console.error('[Chat Turn Error]', error);
    res.status(500).json({ 
      error: error instanceof Error ? error.message : 'Failed to process chat turn',
      message: 'Sorry, something went wrong. Please try again.',
    });
  }
});

// Get session messages
app.get('/farmers/:farmerId/chat/session/:sessionId/messages', (req: Request, res: Response) => {
  try {
    const sessionManager = getSessionManager();
    const session = sessionManager.get(req.params.sessionId);
    if (!session) {
      return res.status(404).json({ error: 'Session not found' });
    }
    res.json({ messages: session.messages });
  } catch (error) {
    res.status(500).json({ error: 'Failed to get messages' });
  }
});

// Get farmer data (for testing)
app.get('/farmers/:farmerId', async (req: Request, res: Response) => {
  try {
    const db = getDatabase();
    const result = await db.getDb()?.get('SELECT * FROM farmers WHERE id = ?', req.params.farmerId);
    if (!result) {
      return res.status(404).json({ error: 'Farmer not found' });
    }
    res.json({ farmer: result });
  } catch (error) {
    res.status(500).json({ error: 'Failed to get farmer' });
  }
});

// Get farmer animals
app.get('/farmers/:farmerId/animals', async (req: Request, res: Response) => {
  try {
    const db = getDatabase();
    const results = await db.getDb()?.all('SELECT * FROM animals WHERE farmer_id = ?', req.params.farmerId);
    res.json({ animals: results || [] });
  } catch (error) {
    res.status(500).json({ error: 'Failed to get animals' });
  }
});

// Get farmer appointments
app.get('/farmers/:farmerId/appointments', async (req: Request, res: Response) => {
  try {
    const db = getDatabase();
    const results = await db.getDb()?.all('SELECT * FROM appointments WHERE farmer_id = ?', req.params.farmerId);
    res.json({ appointments: results || [] });
  } catch (error) {
    res.status(500).json({ error: 'Failed to get appointments' });
  }
});

// Static files (for testing UI)
app.use('/static', express.static(path.join(__dirname, '../../public')));

// Error handling
app.use((err: Error, req: Request, res: Response, next: NextFunction) => {
  console.error('Server error:', err);
  res.status(500).json({ error: 'Internal server error' });
});

// Start server
initialize().then(() => {
  app.listen(PORT, () => {
    console.log('='.repeat(60));
    console.log('🎉 React Loop Skills Local Server');
    console.log('='.repeat(60));
    console.log(`\n📍 API Base URL: http://localhost:${PORT}`);
    console.log(`\n📚 Available endpoints:`);
    console.log(`  GET  /health                     - Health check`);
    console.log(`  GET  /skills                     - List all skills`);
    console.log(`  GET  /skills/:skillId            - Get skill details`);
    console.log(`  POST /farmers/:farmerId/chat/session - Create chat session`);
    console.log(`  POST /farmers/:farmerId/chat/turn   - Send chat message`);
    console.log(`  GET  /farmers/:farmerId          - Get farmer data`);
    console.log(`  GET  /farmers/:farmerId/animals  - Get farmer animals`);
    console.log(`  GET  /farmers/:farmerId/appointments - Get farmer appointments`);
    console.log(`\n🧪 Test with:`);
    console.log(`  curl http://localhost:${PORT}/health`);
    console.log(`  curl http://localhost:${PORT}/skills`);
    console.log(`  curl -X POST http://localhost:${PORT}/farmers/farmer_001/chat/session`);
    console.log(`  curl -X POST http://localhost:${PORT}/farmers/farmer_001/chat/turn \\\n    -H "Content-Type: application/json" \\\n    -d '{"session_id": "test-session", "text": "How many animals do I have?"}'`);
    console.log('\n' + '='.repeat(60));
  });
}).catch(console.error);

export default app;
