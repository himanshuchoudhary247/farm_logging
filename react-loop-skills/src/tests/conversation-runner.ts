/**
 * Conversation Test Runner
 * Runs realistic conversations with fillers, incomplete info, and follow-ups
 */

import { createSessionManager } from '../adk/SessionManager';
import { createSkillRegistry } from '../core/SkillRegistry';
import { createToolRegistry } from '../core/ToolRegistry';
import { createIntentMatcher } from '../core/IntentMatcher';
import { createEnhancedAgentLoop, EnhancedAgentLoop } from '../adk/EnhancedAgentLoop';
import type { Session } from '../core/types';

// Import skills
import * as WeatherSkill from '../skills/weather';
import * as AppointmentsSkill from '../skills/appointments';
import * as MarketPricesSkill from '../skills/market-prices';
import * as FarmQASkill from '../skills/farm-qa';

// Test conversation scenarios
interface TestTurn {
  user: string;
  description: string;
  expectedSkill?: string;
  expectedFollowUp?: boolean;
  expectedDisambiguation?: boolean;
}

interface TestConversation {
  name: string;
  description: string;
  farmerId: string;
  context: {
    location?: string;
    language?: string;
    farmer_id?: string;
  };
  turns: TestTurn[];
}

const testConversations: TestConversation[] = [
  // Scenario 1: Weather with location follow-up
  {
    name: 'Weather with Location Follow-up',
    description: 'User asks about weather without specifying location',
    farmerId: 'farmer_001',
    context: { location: 'Delhi', language: 'en' },
    turns: [
      {
        user: 'What\'s the weather like?',
        description: 'Incomplete query - no location specified',
        expectedSkill: 'weather',
        expectedFollowUp: true,
      },
      {
        user: 'In Mumbai',
        description: 'Provides location as follow-up',
        expectedSkill: 'weather',
      },
      {
        user: 'And tomorrow?',
        description: 'Follow-up referring to previous context',
        expectedSkill: 'weather',
      },
      {
        user: 'Umm... actually wait, I meant Delhi',
        description: 'Changes mind with filler',
        expectedSkill: 'weather',
      },
    ],
  },

  // Scenario 2: Farm QA with multiple queries
  {
    name: 'Farm Information Queries',
    description: 'Farmer asking about their farm animals and production',
    farmerId: 'farmer_001',
    context: { location: 'Muzaffarnagar', language: 'en' },
    turns: [
      {
        user: 'How many animals do I have?',
        description: 'Direct query about animal count',
        expectedSkill: 'farm-qa',
      },
      {
        user: 'Show me my cows',
        description: 'Specific animal type query',
        expectedSkill: 'farm-qa',
      },
      {
        user: 'What about their milk production?',
        description: 'Referencing previous context (cows)',
        expectedSkill: 'farm-qa',
      },
      {
        user: 'And buffalo?',
        description: 'Short follow-up with context switch',
        expectedSkill: 'farm-qa',
      },
      {
        user: 'Wait, tell me about... umm... vaccination schedule',
        description: 'With fillers and hesitation',
        expectedSkill: 'farm-qa',
      },
    ],
  },

  // Scenario 3: Disambiguation required
  {
    name: 'Disambiguation Scenario',
    description: 'Ambiguous queries requiring clarification',
    farmerId: 'farmer_001',
    context: { location: 'Delhi', language: 'en' },
    turns: [
      {
        user: 'What is the price?',
        description: 'Incomplete - no commodity specified',
        expectedSkill: 'market-prices',
        expectedFollowUp: true,
      },
      {
        user: 'Wheat',
        description: 'Provides commodity',
        expectedSkill: 'market-prices',
      },
      {
        user: 'Tell me about my appointments',
        description: 'Switch to appointments',
        expectedSkill: 'appointments',
      },
      {
        user: 'Book one',
        description: 'Vague reference to previous topic',
        expectedSkill: 'appointments',
        expectedFollowUp: true,
      },
      {
        user: 'Vet visit for tomorrow at 10 AM',
        description: 'Provides details in one message',
        expectedSkill: 'appointments',
      },
    ],
  },

  // Scenario 4: Complex conversation with context switching
  {
    name: 'Complex Multi-Topic Conversation',
    description: 'Mix of weather, farm info, and appointments',
    farmerId: 'farmer_001',
    context: { location: 'Delhi', language: 'en' },
    turns: [
      {
        user: 'Will it rain this week?',
        description: 'Weather forecast intent',
        expectedSkill: 'weather',
      },
      {
        user: 'Okay, but what about my crops?',
        description: 'Context switch to farm with filler',
        expectedSkill: 'farm-qa',
      },
      {
        user: 'Specifically the wheat field',
        description: 'Specific crop query',
        expectedSkill: 'farm-qa',
      },
      {
        user: 'Actually, let me check... do I have any appointments this week?',
        description: 'Hesitation and filler, switching topics',
        expectedSkill: 'appointments',
      },
      {
        user: 'No wait, forget that. Show me my animal health records.',
        description: 'Correction with explicit cancellation',
        expectedSkill: 'farm-qa',
      },
      {
        user: 'The cow named Gauri',
        description: 'Specific animal follow-up',
        expectedSkill: 'farm-qa',
      },
      {
        user: 'Is she due for vaccination?',
        description: 'Referring to specific animal by context',
        expectedSkill: 'farm-qa',
      },
    ],
  },

  // Scenario 5: Incomplete and vague queries
  {
    name: 'Vague and Incomplete Queries',
    description: 'Testing robustness with minimal information',
    farmerId: 'farmer_001',
    context: { location: 'Delhi', language: 'en' },
    turns: [
      {
        user: 'Hmm...',
        description: 'Just a filler - no content',
        expectedSkill: undefined,
        expectedDisambiguation: true,
      },
      {
        user: 'I need help with something',
        description: 'Vague request',
        expectedSkill: undefined,
        expectedDisambiguation: true,
      },
      {
        user: 'The thing... with my farm',
        description: 'Vague with fillers',
        expectedSkill: 'farm-qa',
      },
      {
        user: 'My animals',
        description: 'Clarification',
        expectedSkill: 'farm-qa',
      },
      {
        user: 'How many',
        description: 'Incomplete question with context from previous turn',
        expectedSkill: 'farm-qa',
      },
    ],
  },

  // Scenario 6: Natural language database queries
  {
    name: 'Natural Language Farm Queries',
    description: 'Complex NL queries that need parsing',
    farmerId: 'farmer_001',
    context: { location: 'Delhi', language: 'en' },
    turns: [
      {
        user: 'Which cow gives the most milk?',
        description: 'Complex comparative query',
        expectedSkill: 'farm-qa',
      },
      {
        user: 'Compare that with last month',
        description: 'Temporal comparison with context',
        expectedSkill: 'farm-qa',
      },
      {
        user: 'Show me any animals that need vaccination soon',
        description: 'Filtered query with condition',
        expectedSkill: 'farm-qa',
      },
      {
        user: 'Actually, just show me all my buffalo',
        description: 'Correction with specific filter',
        expectedSkill: 'farm-qa',
      },
      {
        user: 'And tell me their vaccination status',
        description: 'Follow-up on same animals',
        expectedSkill: 'farm-qa',
      },
    ],
  },

  // Scenario 7: Appointment booking with missing details
  {
    name: 'Appointment Booking Flow',
    description: 'Step-by-step appointment booking',
    farmerId: 'farmer_001',
    context: { location: 'Delhi', language: 'en' },
    turns: [
      {
        user: 'I need to book an appointment',
        description: 'Intent without details',
        expectedSkill: 'appointments',
        expectedFollowUp: true,
      },
      {
        user: 'Vet check',
        description: 'Provides type',
        expectedSkill: 'appointments',
        expectedFollowUp: true,
      },
      {
        user: 'Tomorrow',
        description: 'Provides date',
        expectedSkill: 'appointments',
        expectedFollowUp: true,
      },
      {
        user: 'In the morning, maybe 9?',
        description: 'Time with uncertainty',
        expectedSkill: 'appointments',
      },
      {
        user: 'Wait, 10 would be better',
        description: 'Correction',
        expectedSkill: 'appointments',
      },
    ],
  },

  // Scenario 8: Context persistence over many turns
  {
    name: 'Long Context Conversation',
    description: 'Testing context window over 10+ turns',
    farmerId: 'farmer_001',
    context: { location: 'Delhi', language: 'en' },
    turns: [
      { user: 'What\'s the weather?', description: 'Turn 1', expectedSkill: 'weather' },
      { user: 'In Bangalore', description: 'Turn 2', expectedSkill: 'weather' },
      { user: 'How about my cows?', description: 'Turn 3', expectedSkill: 'farm-qa' },
      { user: 'Show me the brown one', description: 'Turn 4', expectedSkill: 'farm-qa' },
      { user: 'Her milk production', description: 'Turn 5', expectedSkill: 'farm-qa' },
      { user: 'Compared to buffalo', description: 'Turn 6', expectedSkill: 'farm-qa' },
      { user: 'What\'s the price of milk these days?', description: 'Turn 7', expectedSkill: 'market-prices' },
      { user: 'In Delhi market', description: 'Turn 8', expectedSkill: 'market-prices' },
      { user: 'Book a vet appointment', description: 'Turn 9', expectedSkill: 'appointments' },
      { user: 'For next week', description: 'Turn 10', expectedSkill: 'appointments' },
      { user: 'Actually, go back to the weather - will it rain?', description: 'Turn 11 - referring to turn 1-2', expectedSkill: 'weather' },
      { user: 'In Bangalore, like I asked before', description: 'Turn 12 - context from turn 2', expectedSkill: 'weather' },
    ],
  },
];

// Test runner
class ConversationTestRunner {
  private results: Array<{
    conversation: string;
    turn: number;
    user: string;
    expectedSkill?: string;
    actualSkill?: string;
    expectedFollowUp: boolean;
    actualFollowUp: boolean;
    success: boolean;
    errors: string[];
  }> = [];

  async initializeSystem() {
    console.log('🚀 Initializing skill system...\n');

    // Create registries
    const skillRegistry = createSkillRegistry({ skills_directory: './src/skills' });
    const toolRegistry = createToolRegistry();
    const intentMatcher = createIntentMatcher();
    const sessionManager = createSessionManager();

    // Register skills manually (simulating registry load)
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
          keywords: ['price', 'market', 'mandi', 'rate', 'cost', 'sell', 'buy', 'rupees', 'rs', '₹', 'quintal', 'kg'],
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
    Object.values(WeatherSkill).forEach((tool: unknown) => {
      if (typeof tool === 'object' && tool && 'schema' in tool) {
        toolRegistry.register(tool as any, 'weather');
      }
    });

    Object.values(AppointmentsSkill).forEach((tool: unknown) => {
      if (typeof tool === 'object' && tool && 'schema' in tool) {
        toolRegistry.register(tool as any, 'appointments');
      }
    });

    Object.values(MarketPricesSkill).forEach((tool: unknown) => {
      if (typeof tool === 'object' && tool && 'schema' in tool) {
        toolRegistry.register(tool as any, 'market-prices');
      }
    });

    Object.values(FarmQASkill).forEach((tool: unknown) => {
      if (typeof tool === 'object' && tool && 'schema' in tool) {
        toolRegistry.register(tool as any, 'farm-qa');
      }
    });

    console.log(`✅ Loaded ${skills.length} skills`);
    console.log(`✅ Registered ${toolRegistry.getAll().length} tools\n`);
  }

  async runConversation(conv: TestConversation, convIndex: number): Promise<void> {
    console.log(`\n${'='.repeat(80)}`);
    console.log(`📝 TEST ${convIndex + 1}: ${conv.name}`);
    console.log(`📄 ${conv.description}`);
    console.log(`👤 Farmer ID: ${conv.farmerId}`);
    console.log(`${'='.repeat(80)}\n`);

    // Create session
    const sessionManager = createSessionManager();
    const session = sessionManager.create({
      farmer_id: conv.farmerId,
      ...conv.context,
    });

    // Create enhanced agent loop
    const agent = createEnhancedAgentLoop(session, {
      max_context_turns: 10,
      enable_disambiguation: true,
      enable_followups: true,
      log_level: 'info',
    });

    let turnNumber = 0;

    for (const turn of conv.turns) {
      turnNumber++;
      console.log(`\n--- Turn ${turnNumber} ---`);
      console.log(`🗣️  User: "${turn.user}"`);
      console.log(`💭 Description: ${turn.description}`);

      const errors: string[] = [];
      let actualSkill: string | undefined;
      let actualFollowUp = false;

      try {
        // Run the turn
        const events: any[] = [];
        for await (const event of agent.run(turn.user)) {
          events.push(event);

          // Track skill loading
          if (event.type === 'skill_loaded') {
            actualSkill = event.data?.metadata?.id;
          }

          // Track follow-up requests
          if (event.type === 'follow_up' || event.type === 'clarification_needed') {
            actualFollowUp = true;
            console.log(`🔄 Assistant: "${event.data?.message || event.data?.content}"`);
            if (event.data?.options) {
              console.log(`   Options: ${event.data.options.join(', ')}`);
            }
          }

          // Track responses
          if (event.type === 'response') {
            const content = event.data?.content || event.data;
            if (typeof content === 'string') {
              console.log(`🤖 Assistant: "${content.substring(0, 150)}${content.length > 150 ? '...' : ''}"`);
            }
          }
        }

        // Validate expectations
        if (turn.expectedSkill && actualSkill !== turn.expectedSkill) {
          errors.push(`Expected skill '${turn.expectedSkill}' but got '${actualSkill}'`);
        }

        if (turn.expectedFollowUp && !actualFollowUp) {
          errors.push('Expected follow-up but none was requested');
        }

        if (!turn.expectedFollowUp && actualFollowUp) {
          errors.push('Unexpected follow-up requested');
        }

      } catch (error) {
        errors.push(`Error: ${error instanceof Error ? error.message : String(error)}`);
      }

      // Record result
      this.results.push({
        conversation: conv.name,
        turn: turnNumber,
        user: turn.user,
        expectedSkill: turn.expectedSkill,
        actualSkill,
        expectedFollowUp: turn.expectedFollowUp || false,
        actualFollowUp,
        success: errors.length === 0,
        errors,
      });

      if (errors.length > 0) {
        console.log(`❌ Errors: ${errors.join(', ')}`);
      } else {
        console.log(`✅ Turn completed successfully`);
      }
    }

    // Export conversation logs
    const logs = agent.exportLogs();
    console.log(`\n📊 Conversation logs exported (${logs.length} bytes)`);
  }

  generateReport(): void {
    console.log(`\n${'='.repeat(80)}`);
    console.log('📊 TEST RESULTS SUMMARY');
    console.log(`${'='.repeat(80)}\n`);

    const totalTurns = this.results.length;
    const successfulTurns = this.results.filter(r => r.success).length;
    const failedTurns = totalTurns - successfulTurns;

    console.log(`Total Conversations: ${testConversations.length}`);
    console.log(`Total Turns: ${totalTurns}`);
    console.log(`✅ Successful: ${successfulTurns} (${((successfulTurns / totalTurns) * 100).toFixed(1)}%)`);
    console.log(`❌ Failed: ${failedTurns} (${((failedTurns / totalTurns) * 100).toFixed(1)}%)`);

    // By conversation
    console.log('\n📈 By Conversation:');
    const byConversation = new Map<string, { total: number; success: number }>();
    this.results.forEach(r => {
      const curr = byConversation.get(r.conversation) || { total: 0, success: 0 };
      curr.total++;
      if (r.success) curr.success++;
      byConversation.set(r.conversation, curr);
    });

    byConversation.forEach((stats, name) => {
      const pct = ((stats.success / stats.total) * 100).toFixed(1);
      const icon = stats.success === stats.total ? '✅' : stats.success > stats.total / 2 ? '⚠️' : '❌';
      console.log(`  ${icon} ${name}: ${stats.success}/${stats.total} (${pct}%)`);
    });

    // Failed turns
    if (failedTurns > 0) {
      console.log('\n❌ Failed Turns:');
      this.results.filter(r => !r.success).forEach(r => {
        console.log(`  • ${r.conversation} - Turn ${r.turn}: "${r.user.substring(0, 40)}..."`);
        r.errors.forEach(e => console.log(`    - ${e}`));
      });
    }

    // Skills used
    console.log('\n🎯 Skills Detected:');
    const skillCounts = new Map<string, number>();
    this.results.forEach(r => {
      if (r.actualSkill) {
        skillCounts.set(r.actualSkill, (skillCounts.get(r.actualSkill) || 0) + 1);
      }
    });
    skillCounts.forEach((count, skill) => {
      console.log(`  • ${skill}: ${count} turns`);
    });

    // Follow-ups
    const followUpCount = this.results.filter(r => r.actualFollowUp).length;
    console.log(`\n🔄 Follow-ups Requested: ${followUpCount}/${totalTurns} (${((followUpCount / totalTurns) * 100).toFixed(1)}%)`);

    console.log(`\n${'='.repeat(80)}`);
  }

  async runAll(): Promise<void> {
    await this.initializeSystem();

    for (let i = 0; i < testConversations.length; i++) {
      await this.runConversation(testConversations[i], i);
    }

    this.generateReport();
  }
}

// Run tests
async function main() {
  const runner = new ConversationTestRunner();
  await runner.runAll();
}

// Export for use as module
export { ConversationTestRunner, testConversations };

// Run if executed directly
if (require.main === module) {
  main().catch(console.error);
}
