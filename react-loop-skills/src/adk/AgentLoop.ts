/**
 * ADK Agent Loop - Core agent loop using Google ADK patterns
 * Implements the React Loop: Intent → Skill Loading → Tool Selection → Execution → Response
 */

import type {
  Session,
  SessionMessage,
  ToolCall,
  ToolExecutionResult,
  ADKEvent,
  ADKConfig,
  IntentMatch,
  LoadedSkill,
} from '../core/types';

import { getSkillRegistry } from '../core/SkillRegistry';
import { getToolRegistry } from '../core/ToolRegistry';
import { getIntentMatcher } from '../core/IntentMatcher';

export interface AgentLoopConfig {
  model?: string;
  temperature?: number;
  max_iterations?: number;
  system_prompt?: string;
}

export interface AgentEvent {
  type: 'user_input' | 'intent_detected' | 'skill_loaded' | 'tool_selected' | 'tool_call' | 'tool_response' | 'thinking' | 'response' | 'error' | 'complete';
  data: unknown;
  timestamp: Date;
}

export type AgentEventHandler = (event: AgentEvent) => void | Promise<void>;

export class AgentLoop {
  private config: AgentLoopConfig;
  private session: Session;
  private eventHandlers: AgentEventHandler[] = [];
  private currentSkill?: LoadedSkill;
  private iterationCount = 0;

  constructor(session: Session, config: AgentLoopConfig = {}) {
    this.session = session;
    this.config = {
      model: 'gemini-2.0-flash',
      temperature: 0.7,
      max_iterations: 10,
      system_prompt: 'You are a helpful farming assistant. Use the available tools to help farmers with their queries.',
      ...config,
    };
  }

  /**
   * Subscribe to agent events
   */
  onEvent(handler: AgentEventHandler): () => void {
    this.eventHandlers.push(handler);
    return () => {
      const index = this.eventHandlers.indexOf(handler);
      if (index > -1) {
        this.eventHandlers.splice(index, 1);
      }
    };
  }

  /**
   * Emit an event to all handlers
   */
  private async emitEvent(event: AgentEvent): Promise<void> {
    for (const handler of this.eventHandlers) {
      try {
        await handler(event);
      } catch (error) {
        console.error('[AgentLoop] Event handler error:', error);
      }
    }
  }

  /**
   * Run the agent loop with user input
   */
  async *run(userInput: string): AsyncGenerator<AgentEvent, void, unknown> {
    this.iterationCount = 0;

    // Step 1: Record user input
    const userMessage: SessionMessage = {
      id: this.generateId(),
      role: 'user',
      content: userInput,
      timestamp: new Date(),
    };
    this.session.messages.push(userMessage);
    this.session.updated_at = new Date();

    yield { type: 'user_input', data: userMessage, timestamp: new Date() };
    await this.emitEvent({ type: 'user_input', data: userMessage, timestamp: new Date() });

    // Step 2: Detect intent
    const intentResult = await this.detectIntent(userInput);
    
    if (!intentResult.primary_match) {
      // No matching skill found
      const response = this.generateNoMatchResponse(userInput);
      yield { type: 'response', data: response, timestamp: new Date() };
      await this.emitEvent({ type: 'response', data: response, timestamp: new Date() });
      yield { type: 'complete', data: { success: true }, timestamp: new Date() };
      return;
    }

    yield { type: 'intent_detected', data: intentResult, timestamp: new Date() };
    await this.emitEvent({ type: 'intent_detected', data: intentResult, timestamp: new Date() });

    // Step 3: Load skill
    const skillMatch = intentResult.primary_match;
    const skill = await this.loadSkill(skillMatch.skill);
    
    if (!skill) {
      const error = new Error(`Failed to load skill: ${skillMatch.skill}`);
      yield { type: 'error', data: error, timestamp: new Date() };
      await this.emitEvent({ type: 'error', data: error, timestamp: new Date() });
      return;
    }

    this.currentSkill = skill;
    yield { type: 'skill_loaded', data: skill, timestamp: new Date() };
    await this.emitEvent({ type: 'skill_loaded', data: skill, timestamp: new Date() });

    // Step 4: Select and execute tools
    // In a full ADK implementation, this would use an LLM to decide which tools to call
    // For now, we use a simplified approach
    const selectedTools = this.selectTools(skill, userInput, skillMatch);
    
    yield { type: 'tool_selected', data: selectedTools, timestamp: new Date() };
    await this.emitEvent({ type: 'tool_selected', data: selectedTools, timestamp: new Date() });

    // Execute tools
    const toolResults: ToolExecutionResult[] = [];
    
    for (const toolCall of selectedTools) {
      yield { type: 'tool_call', data: toolCall, timestamp: new Date() };
      await this.emitEvent({ type: 'tool_call', data: toolCall, timestamp: new Date() });

      const result = await this.executeTool(toolCall);
      toolResults.push(result);

      yield { type: 'tool_response', data: result, timestamp: new Date() };
      await this.emitEvent({ type: 'tool_response', data: result, timestamp: new Date() });
    }

    // Step 5: Generate response
    const response = this.generateResponse(userInput, skill, toolResults);
    
    yield { type: 'thinking', data: { reasoning: response.reasoning }, timestamp: new Date() };
    await this.emitEvent({ type: 'thinking', data: { reasoning: response.reasoning }, timestamp: new Date() });

    yield { type: 'response', data: response, timestamp: new Date() };
    await this.emitEvent({ type: 'response', data: response, timestamp: new Date() });

    // Step 6: Update session
    const assistantMessage: SessionMessage = {
      id: this.generateId(),
      role: 'assistant',
      content: response.content,
      timestamp: new Date(),
      skill_id: skill.metadata.id,
      tool_calls: selectedTools,
    };
    this.session.messages.push(assistantMessage);
    this.session.updated_at = new Date();
    
    // Track loaded skills
    if (!this.session.loaded_skills.includes(skill.metadata.id)) {
      this.session.loaded_skills.push(skill.metadata.id);
    }

    yield { type: 'complete', data: { success: true, toolResults }, timestamp: new Date() };
    await this.emitEvent({ type: 'complete', data: { success: true, toolResults }, timestamp: new Date() });
  }

  /**
   * Detect intent from user input
   */
  private async detectIntent(input: string) {
    const matcher = getIntentMatcher();
    return await matcher.match(input, this.session.context);
  }

  /**
   * Load a skill by ID
   */
  private async loadSkill(skillId: string): Promise<LoadedSkill | null> {
    try {
      const registry = getSkillRegistry();
      return await registry.load(skillId);
    } catch (error) {
      console.error(`[AgentLoop] Failed to load skill ${skillId}:`, error);
      return null;
    }
  }

  /**
   * Select tools to execute based on user input and skill
   * Simplified version - full ADK would use LLM for this
   */
  private selectTools(skill: LoadedSkill, input: string, match: IntentMatch): ToolCall[] {
    const toolCalls: ToolCall[] = [];
    const toolRegistry = getToolRegistry();

    // For each suggested tool, create a tool call
    for (const toolName of match.suggested_tools) {
      const tool = toolRegistry.get(toolName);
      if (!tool) continue;

      // Extract parameters from input
      const params = this.extractToolParams(tool.schema.parameters, input);

      toolCalls.push({
        id: this.generateId(),
        tool_name: toolName,
        parameters: params,
      });
    }

    return toolCalls;
  }

  /**
   * Extract parameters for a tool from user input
   */
  private extractToolParams(schema: unknown, input: string): Record<string, unknown> {
    const params: Record<string, unknown> = {};
    const paramSchema = schema as { properties?: Record<string, { type: string }>; required?: string[] };
    
    if (!paramSchema.properties) return params;

    for (const [key, prop] of Object.entries(paramSchema.properties)) {
      // Simple parameter extraction based on keywords
      // In production, this would use LLM or more sophisticated NLP
      if (key === 'location') {
        // Look for location patterns
        const locationMatch = input.match(/(?:in|at|for|near)\s+([A-Za-z\s]+)/i);
        if (locationMatch) {
          params[key] = locationMatch[1].trim();
        } else if (this.session.context.location) {
          params[key] = this.session.context.location;
        }
      } else if (key === 'date' || key === 'when') {
        // Look for date patterns
        const dateMatch = input.match(/(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})/);
        if (dateMatch) {
          params[key] = dateMatch[1];
        } else if (input.includes('today')) {
          params[key] = new Date().toISOString().split('T')[0];
        } else if (input.includes('tomorrow')) {
          const tomorrow = new Date();
          tomorrow.setDate(tomorrow.getDate() + 1);
          params[key] = tomorrow.toISOString().split('T')[0];
        }
      } else if (key === 'animal_id' || key === 'animal_type') {
        // Look for animal references
        const animalMatch = input.match(/(?:cow|buffalo|goat|sheep|chicken|bull)\s*(\d+)?/i);
        if (animalMatch) {
          params[key] = animalMatch[0];
          if (animalMatch[1]) {
            params['animal_id'] = animalMatch[1];
          }
        }
      } else if (key === 'crop' || key === 'crop_type') {
        // Look for crop names
        const cropMatch = input.match(/(?:wheat|rice|corn|maize|cotton|sugarcane|tomato|potato)/i);
        if (cropMatch) {
          params[key] = cropMatch[0];
        }
      }

      // Set default if available and not set
      const propDef = prop as { type: string; default?: unknown };
      if (!(key in params) && propDef.default !== undefined) {
        params[key] = propDef.default;
      }
    }

    return params;
  }

  /**
   * Execute a tool call
   */
  private async executeTool(toolCall: ToolCall): Promise<ToolExecutionResult> {
    const toolRegistry = getToolRegistry();
    const result = await toolRegistry.execute(toolCall.tool_name, toolCall.parameters);
    
    // Store result in tool call
    toolCall.result = result;
    
    return result;
  }

  /**
   * Generate a response based on tool results
   */
  private generateResponse(
    input: string,
    skill: LoadedSkill,
    results: ToolExecutionResult[]
  ): { content: string; reasoning: string } {
    // Check if any tool failed
    const failedResults = results.filter(r => !r.success);
    
    if (failedResults.length > 0) {
      return {
        content: `I'm sorry, I encountered an issue while processing your request. ${failedResults[0].error}`,
        reasoning: 'One or more tools failed to execute',
      };
    }

    // Check if we have successful results
    const successfulResults = results.filter(r => r.success);
    
    if (successfulResults.length === 0) {
      return {
        content: `I couldn't find any information for your request. Could you please provide more details?`,
        reasoning: 'No tools were executed successfully',
      };
    }

    // Generate response based on skill type
    const skillName = skill.metadata.name;
    
    // Simple response generation - in production this would use LLM
    let content = '';
    
    if (skill.metadata.id === 'weather') {
      content = this.formatWeatherResponse(successfulResults);
    } else if (skill.metadata.id === 'appointments') {
      content = this.formatAppointmentResponse(successfulResults);
    } else if (skill.metadata.id === 'market-prices') {
      content = this.formatMarketPriceResponse(successfulResults);
    } else if (skill.metadata.id === 'emergency') {
      content = this.formatEmergencyResponse(successfulResults);
    } else {
      content = this.formatGenericResponse(skillName, successfulResults);
    }

    return {
      content,
      reasoning: `Executed ${results.length} tools from ${skillName} skill`,
    };
  }

  /**
   * Format weather-specific response
   */
  private formatWeatherResponse(results: ToolExecutionResult[]): string {
    const data = results[0]?.data as Record<string, unknown> | undefined;
    if (!data) return 'I could not retrieve weather information at this time.';
    
    return `Current weather: ${data.conditions}, Temperature: ${data.temperature}°C, Humidity: ${data.humidity}%`;
  }

  /**
   * Format appointment-specific response
   */
  private formatAppointmentResponse(results: ToolExecutionResult[]): string {
    const data = results[0]?.data as Record<string, unknown> | undefined;
    if (!data) return 'I could not retrieve appointment information.';
    
    return `I found ${data.count || 'some'} appointments. ${data.message || ''}`;
  }

  /**
   * Format market price response
   */
  private formatMarketPriceResponse(results: ToolExecutionResult[]): string {
    const data = results[0]?.data as Record<string, unknown> | undefined;
    if (!data) return 'I could not retrieve market price information.';
    
    return `Current market prices: ${JSON.stringify(data)}`;
  }

  /**
   * Format emergency response
   */
  private formatEmergencyResponse(results: ToolExecutionResult[]): string {
    const data = results[0]?.data as Record<string, unknown> | undefined;
    if (!data) return 'No emergency alerts at this time.';
    
    return `⚠️ Emergency Alert: ${data.message || 'Check notifications for details'}`;
  }

  /**
   * Format generic response
   */
  private formatGenericResponse(skillName: string, results: ToolExecutionResult[]): string {
    return `Here's what I found using ${skillName}: ${JSON.stringify(results[0]?.data)}`;
  }

  /**
   * Generate response when no skill matches
   */
  private generateNoMatchResponse(input: string): { content: string; reasoning: string } {
    return {
      content: `I'm not sure how to help with that. I can assist with weather information, appointment scheduling, market prices, and farm-related queries. What would you like to know?`,
      reasoning: 'No matching skill found for user input',
    };
  }

  /**
   * Generate unique ID
   */
  private generateId(): string {
    return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }

  /**
   * Get current session
   */
  getSession(): Session {
    return this.session;
  }

  /**
   * Get currently loaded skill
   */
  getCurrentSkill(): LoadedSkill | undefined {
    return this.currentSkill;
  }
}

export function createAgentLoop(session: Session, config?: AgentLoopConfig): AgentLoop {
  return new AgentLoop(session, config);
}
