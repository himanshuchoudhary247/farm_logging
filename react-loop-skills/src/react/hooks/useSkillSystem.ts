/**
 * useSkillSystem - Main hook for the skill system
 * Provides access to registry, intent matching, and skill loading
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import type {
  SkillDefinition,
  LoadedSkill,
  IntentDetectionResult,
  Session,
  SessionContext,
} from '../core/types';
import { createSkillRegistry, getSkillRegistry } from '../core/SkillRegistry';
import { createToolRegistry, getToolRegistry } from '../core/ToolRegistry';
import { createIntentMatcher, getIntentMatcher } from '../core/IntentMatcher';
import { createSessionManager, getSessionManager } from '../adk/SessionManager';

export interface UseSkillSystemOptions {
  skillsDirectory?: string;
  initialContext?: Partial<SessionContext>;
  autoInitialize?: boolean;
}

export interface UseSkillSystemReturn {
  // State
  isInitialized: boolean;
  isLoading: boolean;
  error: string | null;
  currentSession: Session | null;
  
  // Registry access
  skills: SkillDefinition[];
  loadedSkills: LoadedSkill[];
  
  // Actions
  initialize: () => Promise<void>;
  detectIntent: (input: string) => Promise<IntentDetectionResult>;
  loadSkill: (skillId: string) => Promise<LoadedSkill>;
  unloadSkill: (skillId: string) => void;
  createSession: (context?: Partial<SessionContext>) => Session;
  clearError: () => void;
}

export function useSkillSystem(options: UseSkillSystemOptions = {}): UseSkillSystemReturn {
  const { skillsDirectory = './skills', initialContext, autoInitialize = true } = options;
  
  const [isInitialized, setIsInitialized] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [currentSession, setCurrentSession] = useState<Session | null>(null);
  const [skills, setSkills] = useState<SkillDefinition[]>([]);
  const [loadedSkills, setLoadedSkills] = useState<LoadedSkill[]>([]);
  
  const registryRef = useRef<ReturnType<typeof createSkillRegistry> | null>(null);
  const initializedRef = useRef(false);

  // Initialize the system
  const initialize = useCallback(async () => {
    if (initializedRef.current) return;
    
    setIsLoading(true);
    setError(null);
    
    try {
      // Create registries
      const skillRegistry = createSkillRegistry({ skills_directory: skillsDirectory });
      const toolRegistry = createToolRegistry();
      const intentMatcher = createIntentMatcher();
      const sessionManager = createSessionManager({ default_context: initialContext });
      
      await skillRegistry.initialize();
      
      registryRef.current = skillRegistry;
      initializedRef.current = true;
      
      setSkills(skillRegistry.getAll());
      setIsInitialized(true);
      
      // Create initial session
      const session = sessionManager.create(initialContext);
      setCurrentSession(session);
      
      console.log('[useSkillSystem] Initialized successfully');
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to initialize skill system';
      setError(errorMessage);
      console.error('[useSkillSystem] Initialization error:', err);
    } finally {
      setIsLoading(false);
    }
  }, [skillsDirectory, initialContext]);

  // Auto-initialize
  useEffect(() => {
    if (autoInitialize && !initializedRef.current) {
      initialize();
    }
  }, [autoInitialize, initialize]);

  // Detect intent
  const detectIntent = useCallback(async (input: string): Promise<IntentDetectionResult> => {
    if (!isInitialized) {
      throw new Error('Skill system not initialized');
    }
    
    const matcher = getIntentMatcher();
    const context = currentSession?.context;
    
    return await matcher.match(input, context);
  }, [isInitialized, currentSession]);

  // Load a skill
  const loadSkill = useCallback(async (skillId: string): Promise<LoadedSkill> => {
    if (!isInitialized) {
      throw new Error('Skill system not initialized');
    }
    
    setIsLoading(true);
    setError(null);
    
    try {
      const registry = getSkillRegistry();
      const skill = await registry.load(skillId);
      
      // Register tools
      const toolRegistry = getToolRegistry();
      skill.toolImplementations.forEach((tool) => {
        toolRegistry.register(tool, skillId);
      });
      
      // Update loaded skills
      const updatedLoadedSkills = registry.getLoadedAll();
      setLoadedSkills(updatedLoadedSkills);
      
      // Add to session
      if (currentSession) {
        const sessionManager = getSessionManager();
        sessionManager.addLoadedSkill(currentSession.id, skillId);
        setCurrentSession({ ...currentSession });
      }
      
      return skill;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : `Failed to load skill: ${skillId}`;
      setError(errorMessage);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, [isInitialized, currentSession]);

  // Unload a skill
  const unloadSkill = useCallback((skillId: string) => {
    if (!isInitialized) return;
    
    const registry = getSkillRegistry();
    const toolRegistry = getToolRegistry();
    
    // Get tool names for this skill
    const toolNames = toolRegistry.getToolNamesForSkill(skillId);
    
    // Unregister tools
    toolNames.forEach((name) => {
      toolRegistry.unregister(name);
    });
    
    // Unload skill
    registry.unload(skillId);
    
    // Update loaded skills
    setLoadedSkills(registry.getLoadedAll());
  }, [isInitialized]);

  // Create new session
  const createSession = useCallback((context?: Partial<SessionContext>): Session => {
    const sessionManager = getSessionManager();
    const session = sessionManager.create({ ...initialContext, ...context });
    setCurrentSession(session);
    return session;
  }, [initialContext]);

  // Clear error
  const clearError = useCallback(() => {
    setError(null);
  }, []);

  return {
    isInitialized,
    isLoading,
    error,
    currentSession,
    skills,
    loadedSkills,
    initialize,
    detectIntent,
    loadSkill,
    unloadSkill,
    createSession,
    clearError,
  };
}
