/**
 * React Loop Skills System - Main Entry Point
 * 
 * Export all components, hooks, and utilities for the skill-based agent system
 */

// Core types
export type {
  ToolParameter,
  ToolSchema,
  ToolExecutionResult,
  ToolHandler,
  ToolImplementation,
  SkillActivation,
  SkillConfig,
  SkillMetadata,
  SkillDefinition,
  LoadedSkill,
  IntentMatch,
  IntentDetectionResult,
  SessionContext,
  SessionMessage,
  ToolCall,
  Session,
  ADKTool,
  ADKEvent,
  ADKConfig,
  SkillRegistryConfig,
  ToolRegistry,
  SkillRegistry,
} from './core/types';

// Core registry
export {
  SkillRegistryImpl,
  createSkillRegistry,
  getSkillRegistry,
} from './core/SkillRegistry';

export {
  ToolRegistryImpl,
  createToolRegistry,
  getToolRegistry,
} from './core/ToolRegistry';

export {
  IntentMatcher,
  createIntentMatcher,
  getIntentMatcher,
} from './core/IntentMatcher';

// ADK integration
export {
  AgentLoop,
  AgentLoopConfig,
  AgentEvent,
  AgentEventHandler,
  createAgentLoop,
} from './adk/AgentLoop';

export {
  SessionManager,
  SessionManagerConfig,
  createSessionManager,
  getSessionManager,
} from './adk/SessionManager';

export {
  toADKTool,
  createADKHandler,
  convertToolsToADK,
  createToolManifest,
} from './adk/ToolAdapter';

// React hooks
export { useSkillSystem, UseSkillSystemOptions, UseSkillSystemReturn } from './react/hooks/useSkillSystem';
export { useAgent, UseAgentOptions, UseAgentReturn } from './react/hooks/useAgent';

// React providers
export {
  SkillProvider,
  SkillProviderProps,
  useSkillContext,
  SkillContext,
  SkillContextValue,
} from './react/providers/SkillProvider';

// React components
export { SkillChat, SkillChatProps } from './react/components/SkillChat';

// Skills (re-export for convenience)
export * as WeatherSkill from './skills/weather';
export * as AppointmentsSkill from './skills/appointments';
export * as MarketPricesSkill from './skills/market-prices';
export * as FarmQASkill from './skills/farm-qa';

// Enhanced ADK exports
export {
  EnhancedAgentLoop,
  EnhancedAgentLoopConfig,
  EnhancedAgentEvent,
  createEnhancedAgentLoop,
} from './adk/EnhancedAgentLoop';

// Version
export const VERSION = '1.0.0';
