/**
 * SkillChat - Main chat component with skill system integration
 */

import React, { useState, useRef, useEffect } from 'react';
import { useSkillContext } from '../providers/SkillProvider';
import { useAgent } from '../hooks/useAgent';
import type { AgentEvent } from '../../adk/AgentLoop';

interface SkillChatProps {
  sessionId?: string;
  userName?: string;
  avatarUrl?: string;
  placeholder?: string;
  onSkillLoaded?: (skillId: string) => void;
}

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  skillId?: string;
  isLoading?: boolean;
}

export function SkillChat({
  userName = 'Farmer',
  avatarUrl,
  placeholder = 'Ask me about weather, appointments, market prices...',
  onSkillLoaded,
}: SkillChatProps) {
  const {
    isInitialized,
    isLoading: systemLoading,
    error: systemError,
    currentSession,
    skills,
    loadedSkills,
    createSession,
  } = useSkillContext();

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Initialize session if needed
  const session = currentSession || createSession();

  const { 
    isRunning, 
    isThinking, 
    currentResponse,
    events,
    error: agentError,
    sendMessage,
  } = useAgent({ session, config: { max_iterations: 5 } });

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, currentResponse]);

  // Process events
  useEffect(() => {
    events.forEach((event) => {
      if (event.type === 'user_input') {
        const data = event.data as { content?: string };
        if (data.content) {
          setMessages((prev) => [
            ...prev,
            {
              id: Date.now().toString(),
              role: 'user',
              content: data.content!,
              timestamp: new Date(),
            },
          ]);
        }
      } else if (event.type === 'skill_loaded') {
        const data = event.data as { metadata?: { id: string } };
        if (data.metadata?.id) {
          onSkillLoaded?.(data.metadata.id);
        }
      }
    });
  }, [events, onSkillLoaded]);

  // Add assistant response when complete
  useEffect(() => {
    if (!isRunning && currentResponse) {
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now().toString(),
          role: 'assistant',
          content: currentResponse,
          timestamp: new Date(),
        },
      ]);
    }
  }, [isRunning, currentResponse]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isRunning) return;

    const userInput = input.trim();
    setInput('');
    await sendMessage(userInput);
  };

  // Loading state
  if (!isInitialized || systemLoading) {
    return (
      <div className="skill-chat-loading">
        <div className="loading-spinner">Loading skill system...</div>
      </div>
    );
  }

  // Error state
  if (systemError) {
    return (
      <div className="skill-chat-error">
        <div className="error-message">Error: {systemError}</div>
        <button onClick={() => window.location.reload()}>Retry</button>
      </div>
    );
  }

  return (
    <div className="skill-chat-container">
      {/* Header */}
      <div className="skill-chat-header">
        <h3>Farming Assistant</h3>
        <div className="loaded-skills">
          {loadedSkills.length > 0 && (
            <span className="skill-badges">
              Active: {loadedSkills.map((s) => s.metadata.name).join(', ')}
            </span>
          )}
        </div>
      </div>

      {/* Messages */}
      <div className="skill-chat-messages">
        {messages.length === 0 && (
          <div className="welcome-message">
            <p>Hello! {userName} How can I help you today?</p>
            <p className="hint">
              Try asking about:
              {skills.slice(0, 3).map((s) => ` ${s.metadata.name.toLowerCase()},`)}
              or other farming topics.
            </p>
          </div>
        )}

        {messages.map((message) => (
          <div
            key={message.id}
            className={`message ${message.role === 'user' ? 'user-message' : 'assistant-message'}`}
          >
            <div className="message-avatar">
              {message.role === 'user' ? (
                avatarUrl ? (
                  <img src={avatarUrl} alt={userName} />
                ) : (
                  <span className="avatar-initial">{userName[0]}</span>
                )
              ) : (
                <span className="avatar-bot">🤖</span>
              )}
            </div>
            <div className="message-content">
              <p>{message.content}</p>
              <span className="message-time">
                {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </span>
            </div>
          </div>
        ))}

        {/* Streaming response */}
        {isThinking && currentResponse && (
          <div className="message assistant-message thinking">
            <div className="message-avatar">
              <span className="avatar-bot">🤖</span>
            </div>
            <div className="message-content">
              <p>{currentResponse}</p>
              <span className="thinking-indicator">Thinking...</span>
            </div>
          </div>
        )}

        {/* Loading indicator */}
        {isRunning && !currentResponse && (
          <div className="message assistant-message loading">
            <div className="message-avatar">
              <span className="avatar-bot">🤖</span>
            </div>
            <div className="message-content">
              <span className="typing-indicator">
                <span></span>
                <span></span>
                <span></span>
              </span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Error display */}
      {agentError && (
        <div className="chat-error-banner">
          <span>{agentError}</span>
          <button onClick={() => window.location.reload()}>Retry</button>
        </div>
      )}

      {/* Input */}
      <form className="skill-chat-input" onSubmit={handleSubmit}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={placeholder}
          disabled={isRunning}
        />
        <button type="submit" disabled={!input.trim() || isRunning}>
          {isRunning ? '...' : 'Send'}
        </button>
      </form>

      {/* Available skills hint */}
      {skills.length > 0 && (
        <div className="available-skills">
          <small>Available skills: {skills.map((s) => s.metadata.name).join(', ')}</small>
        </div>
      )}
    </div>
  );
}
