/**
 * SkillProvider - React Context Provider for the skill system
 */

import React, { createContext, useContext, ReactNode } from 'react';
import type { Session, SessionContext, SkillDefinition, LoadedSkill } from '../../core/types';
import { useSkillSystem, UseSkillSystemReturn } from '../hooks/useSkillSystem';

interface SkillContextValue extends UseSkillSystemReturn {
  // Additional context-specific values
}

const SkillContext = createContext<SkillContextValue | undefined>(undefined);

export interface SkillProviderProps {
  children: ReactNode;
  skillsDirectory?: string;
  initialContext?: Partial<SessionContext>;
  autoInitialize?: boolean;
}

export function SkillProvider({
  children,
  skillsDirectory = './skills',
  initialContext,
  autoInitialize = true,
}: SkillProviderProps) {
  const skillSystem = useSkillSystem({
    skillsDirectory,
    initialContext,
    autoInitialize,
  });

  return (
    <SkillContext.Provider value={skillSystem}>
      {children}
    </SkillContext.Provider>
  );
}

export function useSkillContext(): SkillContextValue {
  const context = useContext(SkillContext);
  if (context === undefined) {
    throw new Error('useSkillContext must be used within a SkillProvider');
  }
  return context;
}

// Re-export types
export type { SkillContextValue };
export { SkillContext };
