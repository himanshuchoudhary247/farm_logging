/**
 * Tool Adapter - Bridges skills to ADK tool format
 * Adapts our tool implementations to Google ADK format
 */

import type { 
  ToolImplementation, 
  ToolSchema,
  ADKTool,
} from '../core/types';

export interface ADKToolDefinition {
  name: string;
  description: string;
  parameters: object;
  handler: (params: Record<string, unknown>) => Promise<unknown>;
}

/**
 * Convert our tool schema to ADK format
 */
export function toADKTool(tool: ToolImplementation): ADKTool {
  return {
    name: tool.schema.name,
    description: tool.schema.description,
    parameters: tool.schema.parameters,
  };
}

/**
 * Create ADK-compatible tool handler
 */
export function createADKHandler(tool: ToolImplementation) {
  return async (params: Record<string, unknown>): Promise<unknown> => {
    const result = await tool.handler(params);
    
    if (!result.success) {
      throw new Error(result.error || 'Tool execution failed');
    }
    
    return result.data;
  };
}

/**
 * Convert multiple tools to ADK format
 */
export function convertToolsToADK(tools: ToolImplementation[]): ADKTool[] {
  return tools.map(toADKTool);
}

/**
 * Create tool manifest for ADK
 */
export function createToolManifest(skills: string[]): object {
  return {
    version: '1.0.0',
    skills,
    generated_at: new Date().toISOString(),
  };
}
