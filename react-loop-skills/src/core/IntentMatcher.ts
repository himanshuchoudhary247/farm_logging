/**
 * Intent Matcher - Detects user intent and matches to skills
 * Uses keyword matching and confidence scoring
 */

import type {
  IntentDetectionResult,
  IntentMatch,
  SkillDefinition,
  SessionContext,
} from './types';

import { getSkillRegistry } from './SkillRegistry';

export interface IntentMatcherConfig {
  confidence_threshold?: number;
  max_matches?: number;
  use_nlp?: boolean;
}

export class IntentMatcher {
  private config: IntentMatcherConfig;

  constructor(config: IntentMatcherConfig = {}) {
    this.config = {
      confidence_threshold: 0.5,
      max_matches: 3,
      use_nlp: false,
      ...config,
    };
  }

  /**
   * Match user input to skills
   */
  async match(
    input: string,
    context?: SessionContext
  ): Promise<IntentDetectionResult> {
    const normalizedInput = input.toLowerCase().trim();
    const words = normalizedInput.split(/\s+/);
    
    const registry = getSkillRegistry();
    const allSkills = registry.getAll();
    
    const matches: IntentMatch[] = [];

    for (const skill of allSkills) {
      const match = this.calculateMatch(skill, normalizedInput, words, context);
      
      if (match.confidence >= (skill.activation.confidence_threshold || this.config.confidence_threshold!)) {
        matches.push(match);
      }
    }

    // Sort by confidence descending
    matches.sort((a, b) => b.confidence - a.confidence);
    
    // Take top N matches
    const topMatches = matches.slice(0, this.config.max_matches);

    return {
      matches: topMatches,
      primary_match: topMatches[0],
      raw_input: input,
    };
  }

  /**
   * Calculate match score for a skill
   */
  private calculateMatch(
    skill: SkillDefinition,
    input: string,
    words: string[],
    context?: SessionContext
  ): IntentMatch {
    let confidence = 0;
    let matchedIntent = '';

    // Check exact intent matches
    for (const intent of skill.activation.intents) {
      const intentLower = intent.toLowerCase();
      
      // Exact phrase match
      if (input.includes(intentLower)) {
        confidence = Math.max(confidence, 1.0);
        matchedIntent = intent;
        break;
      }
      
      // Partial word match
      const intentWords = intentLower.split(/\s+/);
      const matchingWords = intentWords.filter(w => words.includes(w));
      const wordMatchScore = matchingWords.length / intentWords.length;
      
      if (wordMatchScore > 0) {
        confidence = Math.max(confidence, wordMatchScore * 0.8);
        matchedIntent = intent;
      }
    }

    // Check keyword matches (tags and keywords)
    const allKeywords = [
      ...skill.metadata.tags,
      ...(skill.activation.keywords || []),
    ].map(k => k.toLowerCase());

    const matchingKeywords = allKeywords.filter(kw => 
      words.some(w => kw.includes(w) || w.includes(kw))
    );

    if (matchingKeywords.length > 0) {
      const keywordScore = Math.min(matchingKeywords.length / 3, 1.0) * 0.6;
      confidence = Math.max(confidence, keywordScore);
    }

    // Boost confidence if skill was used recently
    if (context?.previous_skills?.includes(skill.metadata.id)) {
      confidence = Math.min(confidence + 0.1, 1.0);
    }

    // Context boost for farmer-specific queries
    if (context?.farmer_id) {
      // Boost farming-related skills
      const farmingKeywords = ['farm', 'crop', 'animal', 'weather', 'market'];
      if (farmingKeywords.some(kw => allKeywords.includes(kw))) {
        confidence = Math.min(confidence + 0.05, 1.0);
      }
    }

    return {
      skill: skill.metadata.id,
      confidence: Math.round(confidence * 100) / 100,
      matched_intent: matchedIntent,
      suggested_tools: skill.tools,
      context: {
        keywords_matched: matchingKeywords,
      },
    };
  }

  /**
   * Quick check if input matches a specific intent
   */
  matchesIntent(input: string, intent: string): boolean {
    const normalizedInput = input.toLowerCase();
    const normalizedIntent = intent.toLowerCase();
    
    return normalizedInput.includes(normalizedIntent) ||
           normalizedIntent.split(/\s+/).some(word => normalizedInput.includes(word));
  }

  /**
   * Extract entities from input (basic implementation)
   */
  extractEntities(input: string): Record<string, string> {
    const entities: Record<string, string> = {};
    
    // Date patterns
    const datePattern = /\b(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})\b/g;
    const dates = input.match(datePattern);
    if (dates) {
      entities['dates'] = dates.join(', ');
    }

    // Time patterns
    const timePattern = /\b(\d{1,2}:\d{2}(?:\s*[AaPp][Mm])?)\b/g;
    const times = input.match(timePattern);
    if (times) {
      entities['times'] = times.join(', ');
    }

    // Number patterns (for prices, quantities)
    const numberPattern = /\b(\d+(?:\.\d+)?)\s*(kg|liters?|rs|₹|pieces?|units?)?\b/gi;
    const numbers = input.match(numberPattern);
    if (numbers) {
      entities['numbers'] = numbers.join(', ');
    }

    return entities;
  }
}

// Singleton instance
let globalMatcher: IntentMatcher | null = null;

export function createIntentMatcher(config?: IntentMatcherConfig): IntentMatcher {
  globalMatcher = new IntentMatcher(config);
  return globalMatcher;
}

export function getIntentMatcher(): IntentMatcher {
  if (!globalMatcher) {
    globalMatcher = new IntentMatcher();
  }
  return globalMatcher;
}
