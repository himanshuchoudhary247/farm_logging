/**
 * useAgent - Hook for running the agent loop
 * Manages the conversation flow and tool execution
 */

import { useState, useCallback, useRef } from 'react';
import type {
  Session,
  AgentEvent,
  ToolExecutionResult,
} from '../core/types';
import { createAgentLoop, AgentLoop, AgentLoopConfig } from '../../adk/AgentLoop';

export interface UseAgentOptions {
  session: Session;
  config?: AgentLoopConfig;
}

export interface UseAgentReturn {
  // State
  isRunning: boolean;
  isThinking: boolean;
  currentResponse: string;
  events: AgentEvent[];
  error: string | null;
  
  // Actions
  sendMessage: (input: string) => Promise<void>;
  clearEvents: () => void;
  clearError: () => void;
}

export function useAgent(options: UseAgentOptions): UseAgentReturn {
  const { session, config } = options;
  
  const [isRunning, setIsRunning] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const [currentResponse, setCurrentResponse] = useState('');
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  
  const agentLoopRef = useRef<AgentLoop | null>(null);

  // Initialize agent loop if not exists
  if (!agentLoopRef.current) {
    agentLoopRef.current = createAgentLoop(session, config);
  }

  const sendMessage = useCallback(async (input: string): Promise<void> => {
    if (!agentLoopRef.current) return;
    
    setIsRunning(true);
    setIsThinking(true);
    setError(null);
    setCurrentResponse('');
    
    const newEvents: AgentEvent[] = [];
    
    try {
      for await (const event of agentLoopRef.current.run(input)) {
        newEvents.push(event);
        setEvents((prev) => [...prev, event]);
        
        // Update UI based on event type
        switch (event.type) {
          case 'thinking':
            setIsThinking(true);
            break;
          case 'response':
            setIsThinking(false);
            const responseData = event.data as { content?: string };
            if (responseData.content) {
              setCurrentResponse(responseData.content);
            }
            break;
          case 'complete':
            setIsRunning(false);
            setIsThinking(false);
            break;
          case 'error':
            setIsRunning(false);
            setIsThinking(false);
            const errorData = event.data as { message?: string } | Error;
            setError(errorData instanceof Error ? errorData.message : String(errorData));
            break;
        }
      }
    } catch (err) {
      setIsRunning(false);
      setIsThinking(false);
      const errorMessage = err instanceof Error ? err.message : 'Agent execution failed';
      setError(errorMessage);
      console.error('[useAgent] Execution error:', err);
    }
  }, []);

  const clearEvents = useCallback(() => {
    setEvents([]);
  }, []);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  return {
    isRunning,
    isThinking,
    currentResponse,
    events,
    error,
    sendMessage,
    clearEvents,
    clearError,
  };
}
