/**
 * Core type definitions for the React Loop Skill System
 * Built with Google ADK patterns
 */

// ============================================================================
// Tool Definitions
// ============================================================================

export interface ToolParameter {
  type: string;
  description?: string;
  enum?: string[];
  default?: unknown;
  properties?: Record<string, ToolParameter>;
  required?: string[];
  items?: ToolParameter;
}

export interface ToolSchema {
  name: string;
  description: string;
  parameters: ToolParameter;
  returns?: ToolParameter;
}

export interface ToolExecutionResult {
  success: boolean;
  data?: unknown;
  error?: string;
  execution_time_ms?: number;
}

export type ToolHandler = (params: Record<string, unknown>) => Promise<ToolExecutionResult>;

export interface ToolImplementation {
  schema: ToolSchema;
  handler: ToolHandler;
}

// ============================================================================
// Skill Definitions
// ============================================================================

export interface SkillActivation {
  intents: string[];
  confidence_threshold: number;
  keywords?: string[];
}

export interface SkillConfig {
  api_key_required?: boolean;
  rate_limit?: number;
  timeout_ms?: number;
  [key: string]: unknown;
}

export interface SkillMetadata {
  id: string;
  name: string;
  version: string;
  description: string;
  category: string;
  tags: string[];
  author?: string;
  icon?: string;
}

export interface SkillDefinition {
  metadata: SkillMetadata;
  activation: SkillActivation;
  tools: string[];
  dependencies: string[];
  config: SkillConfig;
}

export interface LoadedSkill extends SkillDefinition {
  toolImplementations: Map<string, ToolImplementation>;
  isLoaded: boolean;
}

// ============================================================================
// Intent Definitions
// ============================================================================

export interface IntentMatch {
  skill: string;
  confidence: number;
  matched_intent: string;
  suggested_tools: string[];
  context?: Record<string, unknown>;
}

export interface IntentDetectionResult {
  matches: IntentMatch[];
  primary_match?: IntentMatch;
  raw_input: string;
}

// ============================================================================
// Session Definitions
// ============================================================================

export interface SessionContext {
  user_id?: string;
  location?: string;
  language?: string;
  farmer_id?: string;
  previous_skills?: string[];
  [key: string]: unknown;
}

export interface SessionMessage {
  id: string;
  role: 'user' | 'assistant' | 'tool';
  content: string;
  timestamp: Date;
  skill_id?: string;
  tool_calls?: ToolCall[];
}

export interface ToolCall {
  id: string;
  tool_name: string;
  parameters: Record<string, unknown>;
  result?: ToolExecutionResult;
}

export interface Session {
  id: string;
  context: SessionContext;
  messages: SessionMessage[];
  loaded_skills: string[];
  created_at: Date;
  updated_at: Date;
}

// ============================================================================
// ADK Integration Types
// ============================================================================

export interface ADKTool {
  name: string;
  description: string;
  parameters: ToolParameter;
}

export interface ADKEvent {
  type: 'tool_call' | 'tool_response' | 'thinking' | 'response' | 'error';
  content: unknown;
  timestamp: Date;
}

export interface ADKConfig {
  model: string;
  temperature?: number;
  max_tokens?: number;
  system_prompt?: string;
}

// ============================================================================
// Registry Types
// ============================================================================

export interface SkillRegistryConfig {
  skills_directory: string;
  auto_load?: boolean;
  cache_enabled?: boolean;
}

export interface ToolRegistry {
  register(tool: ToolImplementation): void;
  unregister(toolName: string): void;
  get(toolName: string): ToolImplementation | undefined;
  getAll(): ToolImplementation[];
  getBySkill(skillId: string): ToolImplementation[];
}

export interface SkillRegistry {
  load(skillId: string): Promise<LoadedSkill>;
  unload(skillId: string): void;
  get(skillId: string): SkillDefinition | undefined;
  getLoaded(skillId: string): LoadedSkill | undefined;
  getAll(): SkillDefinition[];
  getLoadedAll(): LoadedSkill[];
  findByIntent(intent: string): SkillDefinition[];
}
