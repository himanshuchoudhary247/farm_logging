/**
 * Skill Registry - JSON-based skill loader
 * Loads skills from JSON definitions and TypeScript implementations
 */

import type {
  SkillDefinition,
  LoadedSkill,
  SkillRegistryConfig,
  ToolImplementation,
} from './types';

export class SkillRegistryImpl {
  private skills: Map<string, SkillDefinition> = new Map();
  private loadedSkills: Map<string, LoadedSkill> = new Map();
  private config: SkillRegistryConfig;

  constructor(config: SkillRegistryConfig) {
    this.config = config;
  }

  /**
   * Initialize the registry by scanning the skills directory
   */
  async initialize(): Promise<void> {
    // In a real implementation, this would scan the directory
    // For now, skills are registered manually or loaded dynamically
    console.log(`[SkillRegistry] Initialized with directory: ${this.config.skills_directory}`);
  }

  /**
   * Register a skill definition
   */
  register(skill: SkillDefinition): void {
    this.skills.set(skill.metadata.id, skill);
    console.log(`[SkillRegistry] Registered skill: ${skill.metadata.id}`);
  }

  /**
   * Load a skill and its tool implementations
   */
  async load(skillId: string): Promise<LoadedSkill> {
    const skill = this.skills.get(skillId);
    if (!skill) {
      throw new Error(`Skill not found: ${skillId}`);
    }

    // Check if already loaded
    const existing = this.loadedSkills.get(skillId);
    if (existing) {
      return existing;
    }

    // Load tool implementations dynamically
    const toolImplementations = new Map<string, ToolImplementation>();
    
    try {
      // Dynamic import of skill implementation
      const skillModule = await import(`${this.config.skills_directory}/${skillId}`);
      
      // Register all exported tools
      for (const toolName of skill.tools) {
        if (skillModule[toolName]) {
          toolImplementations.set(toolName, skillModule[toolName]);
        }
      }
    } catch (error) {
      console.warn(`[SkillRegistry] Could not load implementation for ${skillId}:`, error);
    }

    const loadedSkill: LoadedSkill = {
      ...skill,
      toolImplementations,
      isLoaded: true,
    };

    this.loadedSkills.set(skillId, loadedSkill);
    console.log(`[SkillRegistry] Loaded skill: ${skillId} with ${toolImplementations.size} tools`);

    return loadedSkill;
  }

  /**
   * Unload a skill and free resources
   */
  unload(skillId: string): void {
    const skill = this.loadedSkills.get(skillId);
    if (skill) {
      skill.toolImplementations.clear();
      this.loadedSkills.delete(skillId);
      console.log(`[SkillRegistry] Unloaded skill: ${skillId}`);
    }
  }

  /**
   * Get a skill definition
   */
  get(skillId: string): SkillDefinition | undefined {
    return this.skills.get(skillId);
  }

  /**
   * Get a loaded skill with implementations
   */
  getLoaded(skillId: string): LoadedSkill | undefined {
    return this.loadedSkills.get(skillId);
  }

  /**
   * Get all registered skills
   */
  getAll(): SkillDefinition[] {
    return Array.from(this.skills.values());
  }

  /**
   * Get all loaded skills
   */
  getLoadedAll(): LoadedSkill[] {
    return Array.from(this.loadedSkills.values());
  }

  /**
   * Find skills that match an intent
   */
  findByIntent(intent: string): SkillDefinition[] {
    return this.getAll().filter(skill => 
      skill.activation.intents.includes(intent.toLowerCase())
    );
  }

  /**
   * Find skills by keyword matching
   */
  findByKeywords(keywords: string[]): SkillDefinition[] {
    return this.getAll().filter(skill => {
      const skillKeywords = [
        ...skill.metadata.tags,
        ...(skill.activation.keywords || []),
      ].map(k => k.toLowerCase());
      
      return keywords.some(kw => 
        skillKeywords.includes(kw.toLowerCase()) ||
        skill.activation.intents.some(i => i.includes(kw.toLowerCase()))
      );
    });
  }
}

// Singleton instance
let globalRegistry: SkillRegistryImpl | null = null;

export function createSkillRegistry(config: SkillRegistryConfig): SkillRegistryImpl {
  globalRegistry = new SkillRegistryImpl(config);
  return globalRegistry;
}

export function getSkillRegistry(): SkillRegistryImpl {
  if (!globalRegistry) {
    throw new Error('Skill registry not initialized. Call createSkillRegistry first.');
  }
  return globalRegistry;
}
