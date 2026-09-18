/**
 * Intent Persistence Manager
 * Maintains active skill until user explicitly changes topics or completes task
 */

import { createSkillRegistry, getSkillRegistry } from '../core/SkillRegistry';
import { getToolRegistry } from '../core/ToolRegistry';

export interface ActiveFlow {
  skillId: string;
  startedAt: Date;
  lastActivityAt: Date;
  completedTools: string[];
  pendingTools: string[];
  extractedParams: Record<string, unknown>;
  context: {
    originalQuery: string;
    userGoal?: string;
  };
}

export interface PersistenceConfig {
  maxFlowDurationMinutes?: number;
  autoCompleteOnSuccess?: boolean;
  allowSwitchOnExplicitKeywords?: boolean;
  switchKeywords?: string[];
}

export class IntentPersistenceManager {
  private activeFlow: ActiveFlow | null = null;
  private config: PersistenceConfig;

  constructor(config: PersistenceConfig = {}) {
    this.config = {
      maxFlowDurationMinutes: 30,
      autoCompleteOnSuccess: false,
      allowSwitchOnExplicitKeywords: true,
      switchKeywords: ['switch', 'change', 'instead', 'rather', 'different', 'now', 'actually', 'wait', 'forget', 'cancel', 'stop', 'never mind'],
      ...config,
    };
  }

  /**
   * Check if there's an active flow
   */
  hasActiveFlow(): boolean {
    if (!this.activeFlow) return false;
    
    // Check if flow expired
    const now = new Date();
    const minutesSinceLastActivity = (now.getTime() - this.activeFlow.lastActivityAt.getTime()) / (1000 * 60);
    
    if (minutesSinceLastActivity > (this.config.maxFlowDurationMinutes || 30)) {
      console.log(`[IntentPersistence] Flow expired (${minutesSinceLastActivity.toFixed(1)} min)`);
      this.activeFlow = null;
      return false;
    }
    
    return true;
  }

  /**
   * Get active flow info
   */
  getActiveFlow(): ActiveFlow | null {
    return this.hasActiveFlow() ? this.activeFlow : null;
  }

  /**
   * Start a new flow
   */
  startFlow(skillId: string, originalQuery: string, params: Record<string, unknown> = {}): ActiveFlow {
    // End any existing flow first
    if (this.activeFlow) {
      console.log(`[IntentPersistence] Ending previous flow: ${this.activeFlow.skillId}`);
    }

    this.activeFlow = {
      skillId,
      startedAt: new Date(),
      lastActivityAt: new Date(),
      completedTools: [],
      pendingTools: [],
      extractedParams: { ...params },
      context: {
        originalQuery,
      },
    };

    // Get available tools for this skill
    try {
      const skill = getSkillRegistry().get(skillId);
      if (skill) {
        this.activeFlow.pendingTools = [...skill.tools];
      }
    } catch (e) {
      console.warn(`[IntentPersistence] Could not load skill ${skillId}`);
    }

    console.log(`[IntentPersistence] Started flow: ${skillId}`);
    return this.activeFlow;
  }

  /**
   * Update flow activity
   */
  touchFlow(): void {
    if (this.activeFlow) {
      this.activeFlow.lastActivityAt = new Date();
    }
  }

  /**
   * Mark tool as completed
   */
  completeTool(toolName: string): void {
    if (this.activeFlow) {
      if (!this.activeFlow.completedTools.includes(toolName)) {
        this.activeFlow.completedTools.push(toolName);
      }
      this.activeFlow.pendingTools = this.activeFlow.pendingTools.filter(t => t !== toolName);
      this.touchFlow();
      console.log(`[IntentPersistence] Completed tool: ${toolName}`);
    }
  }

  /**
   * Update extracted parameters
   */
  updateParams(params: Record<string, unknown>): void {
    if (this.activeFlow) {
      Object.assign(this.activeFlow.extractedParams, params);
      this.touchFlow();
      console.log(`[IntentPersistence] Updated params:`, Object.keys(params));
    }
  }

  /**
   * Get accumulated parameters
   */
  getAccumulatedParams(): Record<string, unknown> {
    return this.activeFlow?.extractedParams || {};
  }

  /**
   * Check if user wants to switch intent
   */
  shouldSwitchIntent(userInput: string): boolean {
    if (!this.activeFlow) return true; // No active flow, allow any intent
    
    if (!this.config.allowSwitchOnExplicitKeywords) return false;
    
    const lower = userInput.toLowerCase();
    
    // Check for explicit switch keywords
    for (const keyword of (this.config.switchKeywords || [])) {
      if (lower.includes(keyword)) {
        console.log(`[IntentPersistence] Switch keyword detected: "${keyword}"`);
        return true;
      }
    }
    
    return false;
  }

  /**
   * Check if input is a fragment that should continue current flow
   */
  isFlowContinuation(userInput: string): boolean {
    if (!this.hasActiveFlow()) return false;
    
    // Don't continue if switching
    if (this.shouldSwitchIntent(userInput)) return false;
    
    // Check for short fragments
    const wordCount = userInput.trim().split(/\s+/).filter(w => w.length > 0).length;
    
    // Fragments 1-3 words that don't contain switch keywords should continue
    if (wordCount <= 3 && wordCount > 0) {
      console.log(`[IntentPersistence] Short fragment (${wordCount} words) - continuing flow: ${this.activeFlow!.skillId}`);
      return true;
    }
    
    return false;
  }

  /**
   * Get confidence boost for continuing current flow
   */
  getContextualConfidenceBoost(userInput: string, detectedSkillId: string): number {
    if (!this.activeFlow) return 0;
    
    // If detected skill matches active flow, boost confidence
    if (detectedSkillId === this.activeFlow.skillId) {
      return 0.3; // +30% confidence boost
    }
    
    // If fragment and active flow exists, boost to prefer current flow
    const wordCount = userInput.trim().split(/\s+/).filter(w => w.length > 0).length;
    if (wordCount <= 3) {
      return 0.5; // Strong boost for fragments
    }
    
    return 0;
  }

  /**
   * Complete/close current flow
   */
  completeFlow(): void {
    if (this.activeFlow) {
      const duration = (new Date().getTime() - this.activeFlow.startedAt.getTime()) / 1000;
      console.log(`[IntentPersistence] Completed flow: ${this.activeFlow.skillId}`);
      console.log(`  Duration: ${duration.toFixed(1)}s`);
      console.log(`  Tools completed: ${this.activeFlow.completedTools.length}`);
      console.log(`  Params collected:`, Object.keys(this.activeFlow.extractedParams));
      this.activeFlow = null;
    }
  }

  /**
   * Force end flow (e.g., on error or user cancellation)
   */
  endFlow(reason: string): void {
    if (this.activeFlow) {
      console.log(`[IntentPersistence] Ended flow: ${this.activeFlow.skillId} (${reason})`);
      this.activeFlow = null;
    }
  }

  /**
   * Get flow status for debugging
   */
  getFlowStatus(): {
    hasActiveFlow: boolean;
    skillId?: string;
    duration?: number;
    completedToolCount?: number;
    pendingToolCount?: number;
    accumulatedParams?: string[];
  } {
    if (!this.hasActiveFlow()) {
      return { hasActiveFlow: false };
    }

    const now = new Date();
    return {
      hasActiveFlow: true,
      skillId: this.activeFlow!.skillId,
      duration: (now.getTime() - this.activeFlow!.startedAt.getTime()) / 1000,
      completedToolCount: this.activeFlow!.completedTools.length,
      pendingToolCount: this.activeFlow!.pendingTools.length,
      accumulatedParams: Object.keys(this.activeFlow!.extractedParams),
    };
  }
}

// Singleton instance
let globalManager: IntentPersistenceManager | null = null;

export function createIntentPersistenceManager(config?: PersistenceConfig): IntentPersistenceManager {
  globalManager = new IntentPersistenceManager(config);
  return globalManager;
}

export function getIntentPersistenceManager(): IntentPersistenceManager {
  if (!globalManager) {
    globalManager = new IntentPersistenceManager();
  }
  return globalManager;
}
