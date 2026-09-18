/**
 * Tool Registry - Manages tool registration and execution
 */

import type {
  ToolImplementation,
  ToolExecutionResult,
  ToolHandler,
} from './types';

export class ToolRegistryImpl {
  private tools: Map<string, ToolImplementation> = new Map();
  private skillTools: Map<string, Set<string>> = new Map(); // skillId -> set of tool names

  /**
   * Register a tool
   */
  register(tool: ToolImplementation, skillId?: string): void {
    this.tools.set(tool.schema.name, tool);
    
    if (skillId) {
      const skillSet = this.skillTools.get(skillId) || new Set();
      skillSet.add(tool.schema.name);
      this.skillTools.set(skillId, skillSet);
    }
    
    console.log(`[ToolRegistry] Registered tool: ${tool.schema.name}`);
  }

  /**
   * Unregister a tool
   */
  unregister(toolName: string): void {
    this.tools.delete(toolName);
    
    // Remove from skill mappings
    for (const [skillId, tools] of this.skillTools.entries()) {
      tools.delete(toolName);
      if (tools.size === 0) {
        this.skillTools.delete(skillId);
      }
    }
    
    console.log(`[ToolRegistry] Unregistered tool: ${toolName}`);
  }

  /**
   * Get a tool by name
   */
  get(toolName: string): ToolImplementation | undefined {
    return this.tools.get(toolName);
  }

  /**
   * Get all registered tools
   */
  getAll(): ToolImplementation[] {
    return Array.from(this.tools.values());
  }

  /**
   * Get tools by skill
   */
  getBySkill(skillId: string): ToolImplementation[] {
    const toolNames = this.skillTools.get(skillId);
    if (!toolNames) return [];
    
    return Array.from(toolNames)
      .map(name => this.tools.get(name))
      .filter((tool): tool is ToolImplementation => tool !== undefined);
  }

  /**
   * Execute a tool
   */
  async execute(
    toolName: string,
    params: Record<string, unknown>
  ): Promise<ToolExecutionResult> {
    const tool = this.tools.get(toolName);
    
    if (!tool) {
      return {
        success: false,
        error: `Tool not found: ${toolName}`,
      };
    }

    const startTime = Date.now();
    
    try {
      // Validate parameters against schema
      this.validateParams(params, tool.schema.parameters);
      
      // Execute the tool
      const result = await tool.handler(params);
      
      return {
        ...result,
        execution_time_ms: Date.now() - startTime,
      };
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : String(error),
        execution_time_ms: Date.now() - startTime,
      };
    }
  }

  /**
   * Execute multiple tools in parallel
   */
  async executeParallel(
    calls: Array<{ toolName: string; params: Record<string, unknown> }>
  ): Promise<ToolExecutionResult[]> {
    const promises = calls.map(({ toolName, params }) =>
      this.execute(toolName, params)
    );
    
    return Promise.all(promises);
  }

  /**
   * Execute tools sequentially
   */
  async executeSequential(
    calls: Array<{ toolName: string; params: Record<string, unknown> }>
  ): Promise<ToolExecutionResult[]> {
    const results: ToolExecutionResult[] = [];
    
    for (const { toolName, params } of calls) {
      const result = await this.execute(toolName, params);
      results.push(result);
      
      // Stop on first failure if configured
      if (!result.success) {
        break;
      }
    }
    
    return results;
  }

  /**
   * Validate parameters against schema
   */
  private validateParams(
    params: Record<string, unknown>,
    schema: unknown
  ): void {
    // Basic validation - can be enhanced with JSON Schema validation
    const paramSchema = schema as { required?: string[] };
    
    if (paramSchema.required) {
      for (const required of paramSchema.required) {
        if (!(required in params)) {
          throw new Error(`Missing required parameter: ${required}`);
        }
      }
    }
  }

  /**
   * Get tool names for a skill
   */
  getToolNamesForSkill(skillId: string): string[] {
    const toolNames = this.skillTools.get(skillId);
    return toolNames ? Array.from(toolNames) : [];
  }

  /**
   * Clear all registrations
   */
  clear(): void {
    this.tools.clear();
    this.skillTools.clear();
    console.log('[ToolRegistry] Cleared all registrations');
  }
}

// Singleton instance
let globalRegistry: ToolRegistryImpl | null = null;

export function createToolRegistry(): ToolRegistryImpl {
  globalRegistry = new ToolRegistryImpl();
  return globalRegistry;
}

export function getToolRegistry(): ToolRegistryImpl {
  if (!globalRegistry) {
    throw new Error('Tool registry not initialized. Call createToolRegistry first.');
  }
  return globalRegistry;
}
