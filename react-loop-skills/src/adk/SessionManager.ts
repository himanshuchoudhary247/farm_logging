/**
 * Session Manager - Manages conversation sessions and state
 */

import type { Session, SessionContext, SessionMessage } from '../core/types';

export interface SessionManagerConfig {
  default_context?: Partial<SessionContext>;
  max_messages?: number;
  persist_sessions?: boolean;
}

export class SessionManager {
  private sessions: Map<string, Session> = new Map();
  private config: SessionManagerConfig;

  constructor(config: SessionManagerConfig = {}) {
    this.config = {
      max_messages: 100,
      persist_sessions: false,
      ...config,
    };
  }

  /**
   * Create a new session
   */
  create(context?: Partial<SessionContext>): Session {
    const session: Session = {
      id: this.generateSessionId(),
      context: {
        language: 'en',
        ...this.config.default_context,
        ...context,
      },
      messages: [],
      loaded_skills: [],
      created_at: new Date(),
      updated_at: new Date(),
    };

    this.sessions.set(session.id, session);
    console.log(`[SessionManager] Created session: ${session.id}`);
    
    return session;
  }

  /**
   * Get a session by ID
   */
  get(sessionId: string): Session | undefined {
    return this.sessions.get(sessionId);
  }

  /**
   * Update a session
   */
  update(sessionId: string, updates: Partial<Session>): Session | undefined {
    const session = this.sessions.get(sessionId);
    if (!session) return undefined;

    Object.assign(session, updates, { updated_at: new Date() });
    
    // Trim messages if exceeding max
    if (this.config.max_messages && session.messages.length > this.config.max_messages) {
      session.messages = session.messages.slice(-this.config.max_messages);
    }

    return session;
  }

  /**
   * Add a message to a session
   */
  addMessage(sessionId: string, message: Omit<SessionMessage, 'id' | 'timestamp'>): SessionMessage | undefined {
    const session = this.sessions.get(sessionId);
    if (!session) return undefined;

    const fullMessage: SessionMessage = {
      ...message,
      id: this.generateMessageId(),
      timestamp: new Date(),
    };

    session.messages.push(fullMessage);
    session.updated_at = new Date();

    // Trim messages if needed
    if (this.config.max_messages && session.messages.length > this.config.max_messages) {
      session.messages = session.messages.slice(-this.config.max_messages);
    }

    return fullMessage;
  }

  /**
   * Update session context
   */
  updateContext(sessionId: string, contextUpdates: Partial<SessionContext>): Session | undefined {
    const session = this.sessions.get(sessionId);
    if (!session) return undefined;

    Object.assign(session.context, contextUpdates);
    session.updated_at = new Date();

    return session;
  }

  /**
   * Add loaded skill to session
   */
  addLoadedSkill(sessionId: string, skillId: string): boolean {
    const session = this.sessions.get(sessionId);
    if (!session) return false;

    if (!session.loaded_skills.includes(skillId)) {
      session.loaded_skills.push(skillId);
      session.context.previous_skills = session.loaded_skills;
      session.updated_at = new Date();
    }

    return true;
  }

  /**
   * Get recent messages from a session
   */
  getRecentMessages(sessionId: string, count: number = 10): SessionMessage[] {
    const session = this.sessions.get(sessionId);
    if (!session) return [];

    return session.messages.slice(-count);
  }

  /**
   * Delete a session
   */
  delete(sessionId: string): boolean {
    const deleted = this.sessions.delete(sessionId);
    if (deleted) {
      console.log(`[SessionManager] Deleted session: ${sessionId}`);
    }
    return deleted;
  }

  /**
   * Get all sessions
   */
  getAll(): Session[] {
    return Array.from(this.sessions.values());
  }

  /**
   * Clear all sessions
   */
  clear(): void {
    this.sessions.clear();
    console.log('[SessionManager] Cleared all sessions');
  }

  /**
   * Get session count
   */
  count(): number {
    return this.sessions.size;
  }

  /**
   * Export session data (for persistence)
   */
  exportSession(sessionId: string): string | undefined {
    const session = this.sessions.get(sessionId);
    if (!session) return undefined;

    return JSON.stringify(session, null, 2);
  }

  /**
   * Import session data
   */
  importSession(data: string): Session {
    const session = JSON.parse(data) as Session;
    session.created_at = new Date(session.created_at);
    session.updated_at = new Date(session.updated_at);
    session.messages = session.messages.map(m => ({
      ...m,
      timestamp: new Date(m.timestamp),
    }));

    this.sessions.set(session.id, session);
    console.log(`[SessionManager] Imported session: ${session.id}`);
    
    return session;
  }

  /**
   * Generate unique session ID
   */
  private generateSessionId(): string {
    return `sess_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  /**
   * Generate unique message ID
   */
  private generateMessageId(): string {
    return `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }
}

// Singleton instance
let globalManager: SessionManager | null = null;

export function createSessionManager(config?: SessionManagerConfig): SessionManager {
  globalManager = new SessionManager(config);
  return globalManager;
}

export function getSessionManager(): SessionManager {
  if (!globalManager) {
    globalManager = new SessionManager();
  }
  return globalManager;
}
