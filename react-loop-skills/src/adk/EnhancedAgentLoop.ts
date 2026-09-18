/**
 * Enhanced Agent Loop with Context Management, Follow-ups, and Disambiguation
 * Implements Google ADK best practices for conversational agents
 */

import type {
  Session,
  SessionMessage,
  ToolCall,
  ToolExecutionResult,
  AgentEvent,
  IntentMatch,
  LoadedSkill,
  SessionContext,
} from '../core/types';

import { getSkillRegistry } from '../core/SkillRegistry';
import { getToolRegistry } from '../core/ToolRegistry';
import { getIntentMatcher } from '../core/IntentMatcher';
import { createSessionManager, getSessionManager } from './SessionManager';

// Logger utility
interface LogEntry {
  timestamp: string;
  level: 'debug' | 'info' | 'warn' | 'error';
  component: string;
  message: string;
  data?: unknown;
}

class ConversationLogger {
  private logs: LogEntry[] = [];
  private sessionId: string;

  constructor(sessionId: string) {
    this.sessionId = sessionId;
  }

  log(level: LogEntry['level'], component: string, message: string, data?: unknown) {
    const entry: LogEntry = {
      timestamp: new Date().toISOString(),
      level,
      component,
      message,
      data,
    };
    this.logs.push(entry);
    
    const prefix = `[${entry.timestamp}] [${level.toUpperCase()}] [${component}]`;
    if (data) {
      console.log(prefix, message, JSON.stringify(data, null, 2));
    } else {
      console.log(prefix, message);
    }
  }

  debug(component: string, message: string, data?: unknown) {
    this.log('debug', component, message, data);
  }

  info(component: string, message: string, data?: unknown) {
    this.log('info', component, message, data);
  }

  warn(component: string, message: string, data?: unknown) {
    this.log('warn', component, message, data);
  }

  error(component: string, message: string, data?: unknown) {
    this.log('error', component, message, data);
  }

  getLogs(): LogEntry[] {
    return [...this.logs];
  }

  export(): string {
    return JSON.stringify(this.logs, null, 2);
  }
}

// Context window manager - keeps last N turns
class ContextWindow {
  private maxTurns: number;
  private turns: Array<{
    role: 'user' | 'assistant';
    content: string;
    timestamp: Date;
    skillId?: string;
    toolCalls?: ToolCall[];
    intent?: IntentMatch;
  }> = [];

  constructor(maxTurns: number = 10) {
    this.maxTurns = maxTurns;
  }

  addUserTurn(content: string) {
    this.turns.push({
      role: 'user',
      content,
      timestamp: new Date(),
    });
    this.trim();
  }

  addAssistantTurn(content: string, skillId?: string, toolCalls?: ToolCall[], intent?: IntentMatch) {
    this.turns.push({
      role: 'assistant',
      content,
      timestamp: new Date(),
      skillId,
      toolCalls,
      intent,
    });
    this.trim();
  }

  private trim() {
    if (this.turns.length > this.maxTurns * 2) {
      this.turns = this.turns.slice(-this.maxTurns * 2);
    }
  }

  getRecentTurns(count: number = this.maxTurns): typeof this.turns {
    return this.turns.slice(-count * 2);
  }

  getLastUserQuery(): string | undefined {
    for (let i = this.turns.length - 1; i >= 0; i--) {
      if (this.turns[i].role === 'user') {
        return this.turns[i].content;
      }
    }
    return undefined;
  }

  getToolHistory(): Array<{ skillId: string; toolName: string; timestamp: Date }> {
    const history: Array<{ skillId: string; toolName: string; timestamp: Date }> = [];
    this.turns.forEach(turn => {
      if (turn.toolCalls) {
        turn.toolCalls.forEach(tc => {
          history.push({
            skillId: turn.skillId || 'unknown',
            toolName: tc.tool_name,
            timestamp: turn.timestamp,
          });
        });
      }
    });
    return history;
  }

  getContextString(): string {
    return this.turns.map(t => `${t.role}: ${t.content}`).join('\n');
  }

  clear() {
    this.turns = [];
  }
}

// Disambiguation and follow-up manager
interface ClarificationRequest {
  type: 'disambiguation' | 'missing_parameter' | 'confirmation';
  message: string;
  options?: string[];
  requiredParam?: string;
  suggestedValues?: string[];
}

class DisambiguationManager {
  private pendingClarification: ClarificationRequest | null = null;
  private clarificationContext: {
    originalQuery: string;
    skillId?: string;
    partialParams?: Record<string, unknown>;
  } | null = null;

  setClarification(request: ClarificationRequest, context: typeof this.clarificationContext) {
    this.pendingClarification = request;
    this.clarificationContext = context;
  }

  getClarification(): ClarificationRequest | null {
    return this.pendingClarification;
  }

  isWaitingForClarification(): boolean {
    return this.pendingClarification !== null;
  }

  resolveClarification(response: string): {
    resolved: boolean;
    params?: Record<string, unknown>;
    shouldCancel?: boolean;
  } {
    if (!this.pendingClarification) {
      return { resolved: false };
    }

    const lowerResponse = response.toLowerCase().trim();

    // Handle cancellation
    if (['cancel', 'never mind', 'forget it', 'stop'].includes(lowerResponse)) {
      this.pendingClarification = null;
      this.clarificationContext = null;
      return { resolved: true, shouldCancel: true };
    }

    // Handle option selection
    if (this.pendingClarification.options) {
      const selectedIndex = this.parseOptionSelection(response, this.pendingClarification.options);
      if (selectedIndex !== null) {
        const resolved = {
          resolved: true,
          params: { selected_option: this.pendingClarification.options[selectedIndex] },
        };
        this.pendingClarification = null;
        return resolved;
      }
    }

    // Handle missing parameter
    if (this.pendingClarification.requiredParam) {
      if (this.isValidParamValue(response, this.pendingClarification.requiredParam)) {
        const params: Record<string, unknown> = {};
        params[this.pendingClarification.requiredParam] = response;
        
        // Add any partial params
        if (this.clarificationContext?.partialParams) {
          Object.assign(params, this.clarificationContext.partialParams);
        }
        
        this.pendingClarification = null;
        return { resolved: true, params };
      }
    }

    return { resolved: false };
  }

  private parseOptionSelection(response: string, options: string[]): number | null {
    // Try to parse number (1, 2, 3...)
    const numMatch = response.match(/^(\d+)$/);
    if (numMatch) {
      const index = parseInt(numMatch[1]) - 1;
      if (index >= 0 && index < options.length) {
        return index;
      }
    }

    // Try to match option text
    const lowerResponse = response.toLowerCase();
    for (let i = 0; i < options.length; i++) {
      if (lowerResponse.includes(options[i].toLowerCase())) {
        return i;
      }
    }

    return null;
  }

  private isValidParamValue(value: string, paramName: string): boolean {
    // Basic validation based on parameter name
    switch (paramName) {
      case 'location':
        return value.length >= 2;
      case 'date':
        return /^\d{4}-\d{2}-\d{2}$/.test(value) || 
               ['today', 'tomorrow', 'yesterday', 'next week'].includes(value.toLowerCase());
      case 'animal_type':
        return ['cow', 'buffalo', 'goat', 'sheep', 'chicken', 'bull'].includes(value.toLowerCase());
      case 'commodity':
        return value.length >= 2;
      default:
        return value.length > 0;
    }
  }

  clear() {
    this.pendingClarification = null;
    this.clarificationContext = null;
  }
}

// Slot filling for incomplete queries
class SlotFiller {
  private requiredSlots: Record<string, string[]> = {
    'weather.get_current_weather': ['location'],
    'weather.get_forecast': ['location'],
    'appointments.book_appointment': ['farmer_id', 'type', 'date', 'time'],
    'market-prices.get_market_prices': ['commodity'],
    'farm-qa.query_animals': ['farmer_id'],
    'farm-qa.query_production_data': ['farmer_id', 'from_date', 'to_date'],
  };

  private extractableSlots: Record<string, (input: string, context: SessionContext) => Record<string, unknown>> = {
    location: (input, context) => {
      // Try to extract from input
      const patterns = [
        /(?:in|at|for|near)\s+([A-Za-z\s]+)/i,
        /(?:delhi|mumbai|bangalore|chennai|kolkata|hyderabad|pune|ahmedabad|jaipur|lucknow)/i,
      ];
      
      for (const pattern of patterns) {
        const match = input.match(pattern);
        if (match) {
          return { location: match[1] || match[0] };
        }
      }
      
      // Fall back to context
      if (context.location) {
        return { location: context.location };
      }
      
      return {};
    },
    
    date: (input) => {
      const today = new Date();
      const lower = input.toLowerCase();
      
      if (lower.includes('today')) {
        return { date: today.toISOString().split('T')[0] };
      }
      if (lower.includes('tomorrow')) {
        const tomorrow = new Date(today);
        tomorrow.setDate(tomorrow.getDate() + 1);
        return { date: tomorrow.toISOString().split('T')[0] };
      }
      if (lower.includes('next week')) {
        const nextWeek = new Date(today);
        nextWeek.setDate(nextWeek.getDate() + 7);
        return { date: nextWeek.toISOString().split('T')[0] };
      }
      
      // Try to parse date pattern
      const dateMatch = input.match(/(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{2,4})/);
      if (dateMatch) {
        const [, day, month, year] = dateMatch;
        const fullYear = year.length === 2 ? `20${year}` : year;
        return { date: `${fullYear}-${month.padStart(2, '0')}-${day.padStart(2, '0')}` };
      }
      
      return {};
    },
    
    animal_type: (input) => {
      const types = ['cow', 'buffalo', 'goat', 'sheep', 'chicken', 'bull'];
      const lower = input.toLowerCase();
      for (const type of types) {
        if (lower.includes(type)) {
          return { animal_type: type };
        }
      }
      return {};
    },
    
    commodity: (input) => {
      const commodities = ['wheat', 'rice', 'cotton', 'corn', 'maize', 'sugarcane', 'pulses'];
      const lower = input.toLowerCase();
      for (const comm of commodities) {
        if (lower.includes(comm)) {
          return { commodity: comm };
        }
      }
      return {};
    },
  };

  getRequiredSlots(skillId: string, toolName: string): string[] {
    const key = `${skillId}.${toolName}`;
    return this.requiredSlots[key] || [];
  }

  extractSlots(input: string, context: SessionContext, skillId: string, toolName: string): Record<string, unknown> {
    const required = this.getRequiredSlots(skillId, toolName);
    const extracted: Record<string, unknown> = {};
    
    for (const slot of required) {
      if (this.extractableSlots[slot]) {
        const values = this.extractableSlots[slot](input, context);
        Object.assign(extracted, values);
      }
    }
    
    return extracted;
  }

  getMissingSlots(params: Record<string, unknown>, skillId: string, toolName: string): string[] {
    const required = this.getRequiredSlots(skillId, toolName);
    return required.filter(slot => !(slot in params) || params[slot] === undefined || params[slot] === null);
  }

  getClarificationPrompt(slot: string): string {
    const prompts: Record<string, string> = {
      location: 'Which location would you like to know about? (e.g., Delhi, Mumbai, or your village name)',
      date: 'Which date are you asking about? (e.g., today, tomorrow, or YYYY-MM-DD)',
      animal_type: 'Which type of animals? (cow, buffalo, goat, sheep, etc.)',
      commodity: 'Which commodity are you asking about? (wheat, rice, cotton, etc.)',
      farmer_id: 'Please provide your farmer ID or registered phone number.',
    };
    return prompts[slot] || `Please provide the ${slot}.`;
  }
}

// Main enhanced agent loop
export interface EnhancedAgentLoopConfig {
  model?: string;
  temperature?: number;
  max_iterations?: number;
  system_prompt?: string;
  max_context_turns?: number;
  enable_disambiguation?: boolean;
  enable_followups?: boolean;
  log_level?: 'debug' | 'info' | 'warn' | 'error';
}

export interface EnhancedAgentEvent {
  type: 
    | 'user_input' 
    | 'intent_detected' 
    | 'skill_loaded' 
    | 'tool_selected' 
    | 'tool_call' 
    | 'tool_response' 
    | 'thinking' 
    | 'response' 
    | 'error' 
    | 'complete'
    | 'clarification_needed'
    | 'follow_up';
  data: unknown;
  timestamp: Date;
  context?: {
    recent_turns?: number;
    tool_history_count?: number;
    session_id?: string;
  };
}

export type EnhancedAgentEventHandler = (event: EnhancedAgentEvent) => void | Promise<void>;

export class EnhancedAgentLoop {
  private config: EnhancedAgentLoopConfig;
  private session: Session;
  private contextWindow: ContextWindow;
  private disambiguationManager: DisambiguationManager;
  private slotFiller: SlotFiller;
  private logger: ConversationLogger;
  private eventHandlers: EnhancedAgentEventHandler[] = [];
  private currentSkill?: LoadedSkill;
  private iterationCount = 0;

  constructor(session: Session, config: EnhancedAgentLoopConfig = {}) {
    this.session = session;
    this.config = {
      model: 'gemini-2.0-flash',
      temperature: 0.7,
      max_iterations: 10,
      max_context_turns: 10,
      enable_disambiguation: true,
      enable_followups: true,
      log_level: 'info',
      system_prompt: `You are a helpful farming assistant. Use the available tools to help farmers with their queries.

Context Management:
- You have access to the last 10 conversation turns
- Remember what tools were called previously
- Track user preferences and context

Follow-up Guidelines:
- If information is missing, ask follow-up questions
- Provide disambiguation options when intent is unclear
- Confirm before taking irreversible actions

Tone: Friendly, helpful, professional but approachable.`,
      ...config,
    };
    
    this.contextWindow = new ContextWindow(this.config.max_context_turns);
    this.disambiguationManager = new DisambiguationManager();
    this.slotFiller = new SlotFiller();
    this.logger = new ConversationLogger(session.id);
    
    this.logger.info('EnhancedAgentLoop', 'Agent loop initialized', {
      session_id: session.id,
      config: this.config,
    });
  }

  onEvent(handler: EnhancedAgentEventHandler): () => void {
    this.eventHandlers.push(handler);
    return () => {
      const index = this.eventHandlers.indexOf(handler);
      if (index > -1) this.eventHandlers.splice(index, 1);
    };
  }

  private async emitEvent(event: EnhancedAgentEvent): Promise<void> {
    for (const handler of this.eventHandlers) {
      try {
        await handler(event);
      } catch (error) {
        this.logger.error('EventHandler', 'Handler failed', error);
      }
    }
  }

  async *run(userInput: string): AsyncGenerator<EnhancedAgentEvent, void, unknown> {
    this.iterationCount = 0;
    this.logger.info('Run', 'Starting new turn', { user_input: userInput });

    // Step 1: Check if we're waiting for clarification
    if (this.disambiguationManager.isWaitingForClarification()) {
      this.logger.debug('Run', 'Resolving clarification', { input: userInput });
      
      const resolution = this.disambiguationManager.resolveClarification(userInput);
      
      if (resolution.shouldCancel) {
        yield { type: 'response', data: { content: 'No problem! Let me know if you need anything else.' }, timestamp: new Date() };
        await this.emitEvent({ type: 'response', data: { content: 'No problem! Let me know if you need anything else.' }, timestamp: new Date() });
        this.disambiguationManager.clear();
        return;
      }
      
      if (resolution.resolved && resolution.params) {
        // Continue with resolved parameters
        this.logger.info('Run', 'Clarification resolved', resolution.params);
        yield { type: 'thinking', data: { message: 'Thank you! Processing your request...' }, timestamp: new Date() };
        
        // Re-run with resolved params
        const result = await this.executeWithParams(resolution.params);
        yield* this.handleExecutionResult(result, userInput);
        return;
      }
    }

    // Step 2: Record user input
    this.contextWindow.addUserTurn(userInput);
    const userMessage: SessionMessage = {
      id: this.generateId(),
      role: 'user',
      content: userInput,
      timestamp: new Date(),
    };
    this.session.messages.push(userMessage);
    this.session.updated_at = new Date();

    yield { 
      type: 'user_input', 
      data: userMessage, 
      timestamp: new Date(),
      context: { recent_turns: this.contextWindow.getRecentTurns().length / 2 },
    };

    // Step 3: Detect intent with context
    const intentResult = await this.detectIntent(userInput);
    this.logger.info('IntentDetection', 'Intent detected', intentResult);

    if (!intentResult.primary_match) {
      yield { type: 'clarification_needed', data: { message: 'I\'m not sure what you\'re asking about. Could you clarify? I can help with weather, appointments, market prices, or farm information.' }, timestamp: new Date() };
      await this.emitEvent({ type: 'clarification_needed', data: { message: 'I\'m not sure what you\'re asking about.' }, timestamp: new Date() });
      
      // Set up disambiguation
      this.disambiguationManager.setClarification(
        {
          type: 'disambiguation',
          message: 'What would you like to know about?',
          options: ['Weather', 'Appointments', 'Market Prices', 'Farm Information'],
        },
        { originalQuery: userInput }
      );
      
      return;
    }

    yield { type: 'intent_detected', data: intentResult, timestamp: new Date() };

    // Check for low confidence
    if (intentResult.primary_match.confidence < 0.7 && this.config.enable_disambiguation) {
      this.logger.warn('IntentDetection', 'Low confidence, asking for clarification', {
        confidence: intentResult.primary_match.confidence,
      });
      
      // Show top matches
      const options = intentResult.matches.slice(0, 3).map(m => {
        const skill = getSkillRegistry().get(m.skill);
        return skill?.metadata.name || m.skill;
      });
      
      yield { 
        type: 'clarification_needed', 
        data: { 
          message: `I'm not entirely sure. Did you mean:`,
          options,
        }, 
        timestamp: new Date(),
      };
      
      this.disambiguationManager.setClarification(
        {
          type: 'disambiguation',
          message: 'Which did you mean?',
          options,
        },
        { originalQuery: userInput }
      );
      
      return;
    }

    // Step 4: Load skill
    const skillMatch = intentResult.primary_match;
    const skill = await this.loadSkill(skillMatch.skill);
    
    if (!skill) {
      this.logger.error('SkillLoading', 'Failed to load skill', { skill_id: skillMatch.skill });
      yield { type: 'error', data: { message: 'Failed to load skill' }, timestamp: new Date() };
      return;
    }

    this.currentSkill = skill;
    yield { type: 'skill_loaded', data: skill, timestamp: new Date() };

    // Step 5: Extract parameters and check for missing slots
    const extractedParams = this.extractParameters(userInput, skill, skillMatch);
    const missingSlots = this.getMissingSlots(extractedParams, skill, skillMatch);

    if (missingSlots.length > 0 && this.config.enable_followups) {
      this.logger.info('SlotFilling', 'Missing slots detected', { missing: missingSlots });
      
      const firstMissing = missingSlots[0];
      const prompt = this.slotFiller.getClarificationPrompt(firstMissing);
      
      yield { 
        type: 'follow_up', 
        data: { 
          message: prompt,
          missing_param: firstMissing,
        }, 
        timestamp: new Date(),
      };
      
      this.disambiguationManager.setClarification(
        {
          type: 'missing_parameter',
          message: prompt,
          requiredParam: firstMissing,
        },
        { 
          originalQuery: userInput, 
          skillId: skill.metadata.id,
          partialParams: extractedParams,
        }
      );
      
      return;
    }

    // Step 6: Select and execute tools
    const selectedTools = this.selectTools(skill, userInput, skillMatch, extractedParams);
    yield { type: 'tool_selected', data: selectedTools, timestamp: new Date() };

    const toolResults: ToolExecutionResult[] = [];
    for (const toolCall of selectedTools) {
      yield { type: 'tool_call', data: toolCall, timestamp: new Date() };
      
      const result = await this.executeTool(toolCall);
      toolResults.push(result);
      
      yield { type: 'tool_response', data: result, timestamp: new Date() };
    }

    // Step 7: Generate response with context
    yield* this.handleExecutionResult({ success: true, toolResults }, userInput, skill);
  }

  private async executeWithParams(params: Record<string, unknown>): Promise<{ success: boolean; toolResults?: ToolExecutionResult[]; error?: string }> {
    // Execute with resolved parameters
    const toolResults: ToolExecutionResult[] = [];
    
    // Find appropriate tool based on params
    const registry = getSkillRegistry();
    const skill = this.currentSkill;
    
    if (!skill) {
      return { success: false, error: 'No skill loaded' };
    }

    // Select and execute tools
    for (const toolName of skill.tools) {
      const tool = getToolRegistry().get(toolName);
      if (tool && this.canExecuteTool(toolName, params)) {
        const result = await getToolRegistry().execute(toolName, params);
        toolResults.push(result);
      }
    }

    return { success: true, toolResults };
  }

  private canExecuteTool(toolName: string, params: Record<string, unknown>): boolean {
    const tool = getToolRegistry().get(toolName);
    if (!tool) return false;
    
    // Check if all required params are present
    const required = tool.schema.parameters.required || [];
    return required.every(r => r in params && params[r] !== undefined && params[r] !== null);
  }

  private async *handleExecutionResult(
    result: { success: boolean; toolResults?: ToolExecutionResult[]; error?: string },
    userInput: string,
    skill?: LoadedSkill
  ): AsyncGenerator<EnhancedAgentEvent, void, unknown> {
    if (!result.success) {
      yield { type: 'error', data: { message: result.error }, timestamp: new Date() };
      await this.emitEvent({ type: 'error', data: { message: result.error }, timestamp: new Date() });
      return;
    }

    const toolResults = result.toolResults || [];
    
    // Generate contextual response
    const response = this.generateContextualResponse(userInput, skill, toolResults);
    
    yield { type: 'thinking', data: { reasoning: response.reasoning }, timestamp: new Date() };
    
    // Add to context
    this.contextWindow.addAssistantTurn(
      response.content,
      skill?.metadata.id,
      toolResults.length > 0 ? toolResults.map((_, i) => ({ id: `tc_${i}`, tool_name: 'tool', parameters: {} })) : undefined,
      undefined
    );
    
    // Add to session
    const assistantMessage: SessionMessage = {
      id: this.generateId(),
      role: 'assistant',
      content: response.content,
      timestamp: new Date(),
      skill_id: skill?.metadata.id,
    };
    this.session.messages.push(assistantMessage);
    this.session.updated_at = new Date();

    yield { 
      type: 'response', 
      data: response, 
      timestamp: new Date(),
      context: {
        recent_turns: this.contextWindow.getRecentTurns().length / 2,
        tool_history_count: this.contextWindow.getToolHistory().length,
      },
    };
    await this.emitEvent({ 
      type: 'response', 
      data: response, 
      timestamp: new Date(),
    });

    yield { type: 'complete', data: { success: true, toolResults }, timestamp: new Date() };
  }

  private async detectIntent(input: string) {
    const matcher = getIntentMatcher();
    
    // Add context to detection
    const recentContext = this.contextWindow.getRecentTurns(3);
    const enrichedContext: SessionContext = {
      ...this.session.context,
      previous_skills: this.session.loaded_skills,
      recent_queries: recentContext.filter(t => t.role === 'user').map(t => t.content),
    };
    
    return await matcher.match(input, enrichedContext);
  }

  private async loadSkill(skillId: string): Promise<LoadedSkill | null> {
    try {
      const registry = getSkillRegistry();
      return await registry.load(skillId);
    } catch (error) {
      this.logger.error('SkillLoading', 'Failed to load skill', error);
      return null;
    }
  }

  private extractParameters(input: string, skill: LoadedSkill, match: IntentMatch): Record<string, unknown> {
    const params: Record<string, unknown> = {
      farmer_id: this.session.context.farmer_id,
    };

    // Use slot filler
    for (const toolName of match.suggested_tools) {
      const extracted = this.slotFiller.extractSlots(input, this.session.context, skill.metadata.id, toolName);
      Object.assign(params, extracted);
    }

    this.logger.debug('ParameterExtraction', 'Extracted parameters', params);
    return params;
  }

  private getMissingSlots(params: Record<string, unknown>, skill: LoadedSkill, match: IntentMatch): string[] {
    const allMissing: string[] = [];
    
    for (const toolName of match.suggested_tools) {
      const missing = this.slotFiller.getMissingSlots(params, skill.metadata.id, toolName);
      allMissing.push(...missing);
    }
    
    return [...new Set(allMissing)];
  }

  private selectTools(skill: LoadedSkill, input: string, match: IntentMatch, params: Record<string, unknown>): ToolCall[] {
    const toolCalls: ToolCall[] = [];
    
    for (const toolName of match.suggested_tools) {
      toolCalls.push({
        id: this.generateId(),
        tool_name: toolName,
        parameters: params,
      });
    }
    
    return toolCalls;
  }

  private async executeTool(toolCall: ToolCall): Promise<ToolExecutionResult> {
    const result = await getToolRegistry().execute(toolCall.tool_name, toolCall.parameters);
    toolCall.result = result;
    return result;
  }

  private generateContextualResponse(
    input: string,
    skill: LoadedSkill | undefined,
    results: ToolExecutionResult[]
  ): { content: string; reasoning: string } {
    // Check for failures
    const failedResults = results.filter(r => !r.success);
    if (failedResults.length > 0) {
      return {
        content: `I'm sorry, I encountered an issue: ${failedResults[0].error}. Could you try again or provide more details?`,
        reasoning: 'Tool execution failed',
      };
    }

    // Generate contextual response based on skill
    const skillId = skill?.metadata.id;
    
    if (!skillId) {
      return {
        content: 'I\'m not sure how to help with that. Could you rephrase your question?',
        reasoning: 'No skill matched',
      };
    }

    // Get recent context for continuity
    const recentTurns = this.contextWindow.getRecentTurns(3);
    const hasPreviousContext = recentTurns.length > 2;

    let content = '';
    
    switch (skillId) {
      case 'weather':
        content = this.formatWeatherResponse(results, hasPreviousContext);
        break;
      case 'appointments':
        content = this.formatAppointmentResponse(results, hasPreviousContext);
        break;
      case 'market-prices':
        content = this.formatMarketPriceResponse(results, hasPreviousContext);
        break;
      case 'farm-qa':
        content = this.formatFarmQAResponse(results, input, hasPreviousContext);
        break;
      default:
        content = `Here's what I found: ${JSON.stringify(results[0]?.data)}`;
    }

    // Add follow-up suggestion if appropriate
    if (skillId === 'farm-qa' && results.length > 0) {
      content += '\n\nIs there anything specific about your farm you\'d like to know more about?';
    }

    return {
      content,
      reasoning: `Generated response for ${skillId} skill with ${results.length} tool results`,
    };
  }

  private formatWeatherResponse(results: ToolExecutionResult[], hasContext: boolean): string {
    const data = results[0]?.data as Record<string, unknown> | undefined;
    if (!data) return 'I couldn\'t retrieve weather information at this time.';
    
    const location = data.location || 'your location';
    const temp = data.temperature;
    const conditions = data.conditions;
    const humidity = data.humidity;
    
    let intro = hasContext ? 'As for the weather now,' : 'Here\'s the weather update:';
    
    return `${intro} It's currently ${conditions.toLowerCase()} in ${location} with a temperature of ${temp}°C and ${humidity}% humidity.`;
  }

  private formatAppointmentResponse(results: ToolExecutionResult[], hasContext: boolean): string {
    const data = results[0]?.data as Record<string, unknown> | undefined;
    if (!data) return 'I couldn\'t retrieve appointment information.';
    
    const count = data.count as number;
    const message = data.message as string;
    
    if (message) return message;
    
    return hasContext 
      ? `You have ${count} upcoming appointments scheduled.`
      : `I found ${count} appointments in your schedule.`;
  }

  private formatMarketPriceResponse(results: ToolExecutionResult[], hasContext: boolean): string {
    const data = results[0]?.data as Record<string, unknown> | undefined;
    if (!data) return 'I couldn\'t retrieve market price information.';
    
    const commodity = data.commodity;
    const modalPrice = data.modal_price;
    const market = data.market;
    const unit = data.unit;
    
    return hasContext
      ? `Current ${commodity} prices at ${market}: ₹${modalPrice} ${unit}.`
      : `Here are the current market prices for ${commodity}: ₹${modalPrice} ${unit} at ${market}.`;
  }

  private formatFarmQAResponse(results: ToolExecutionResult[], query: string, hasContext: boolean): string {
    const data = results[0]?.data as Record<string, unknown> | undefined;
    if (!data) return 'I couldn\'t find that information.';
    
    // Handle different types of responses
    if ('count' in data) {
      const count = data.count as number;
      const byType = data.by_type as Record<string, number>;
      
      if (byType) {
        const breakdown = Object.entries(byType)
          .map(([type, num]) => `${num} ${type}${num > 1 ? 's' : ''}`)
          .join(', ');
        return hasContext
          ? `You have ${count} animals total: ${breakdown}.`
          : `I found ${count} animals on your farm: ${breakdown}.`;
      }
      
      return `You have ${count} total.`;
    }
    
    if ('answer' in data) {
      return data.answer as string;
    }
    
    if ('summary' in data) {
      const summary = data.summary as Record<string, unknown>;
      const sections = ['animals', 'crops', 'production', 'health', 'vaccinations']
        .filter(s => summary[s] !== undefined)
        .map(s => `${s}: ${summary[s]}`)
        .join(', ');
      return `Here's your farm summary: ${sections}.`;
    }
    
    return `Here's what I found: ${JSON.stringify(data)}`;
  }

  private generateId(): string {
    return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }

  getSession(): Session {
    return this.session;
  }

  getCurrentSkill(): LoadedSkill | undefined {
    return this.currentSkill;
  }

  getContextWindow() {
    return this.contextWindow;
  }

  getLogger() {
    return this.logger;
  }

  exportLogs(): string {
    return this.logger.export();
  }
}

export function createEnhancedAgentLoop(session: Session, config?: EnhancedAgentLoopConfig): EnhancedAgentLoop {
  return new EnhancedAgentLoop(session, config);
}
