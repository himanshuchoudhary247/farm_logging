# React Loop Skills System

A React-based intent-driven skill system where each functionality is exposed as a set of tools, organized into skills. Built with Google ADK (Agent Development Kit) patterns for agent loops, tool execution, and state management.

## Quick Start

### Installation

```bash
npm install react-loop-skills
# or
yarn add react-loop-skills
```

### Basic Usage

```tsx
import { SkillProvider, SkillChat } from 'react-loop-skills';

function App() {
  return (
    <SkillProvider
      skillsDirectory="./skills"
      initialContext={{
        language: 'en',
        location: 'Delhi',
      }}
    >
      <SkillChat
        userName="Farmer Rajesh"
        placeholder="Ask about weather, prices, or appointments..."
      />
    </SkillProvider>
  );
}
```

### Using Hooks

```tsx
import { useSkillContext, useAgent } from 'react-loop-skills';

function MyComponent() {
  const { 
    isInitialized, 
    skills, 
    loadedSkills, 
    detectIntent, 
    loadSkill 
  } = useSkillContext();

  const { currentSession } = useSkillContext();
  const { sendMessage, isRunning, currentResponse } = useAgent({ 
    session: currentSession! 
  });

  const handleUserInput = async (input: string) => {
    // Detect intent
    const intent = await detectIntent(input);
    
    if (intent.primary_match) {
      // Load the matching skill
      await loadSkill(intent.primary_match.skill);
      
      // Send message through agent
      await sendMessage(input);
    }
  };

  return (
    <div>
      {/* Your UI */}
    </div>
  );
}
```

## Architecture

### Skills

A **Skill** is a domain-specific capability bundle containing:
- **Name**: Unique identifier
- **Description**: What the skill does (used for intent matching)
- **Tools**: Array of tools that implement the skill's functionality
- **Metadata**: Tags, category, version, etc.

### Tools

A **Tool** is an executable function with:
- **Name**: Unique identifier within the skill
- **Description**: What the tool does (used by agent to select tools)
- **Parameters**: JSON Schema defining expected inputs
- **Returns**: JSON Schema defining expected outputs
- **Handler**: The actual implementation

### React Loop Flow

```
User Input → Intent Detection → Skill Loading → Tool Selection → Tool Execution → Response
     ↑                                                                              ↓
     └─────────────────────────← State Update ←───────────────────────────────────┘
```

## Skill Definition

Each skill consists of three files:

### 1. skill.json - Metadata

```json
{
  "metadata": {
    "id": "weather",
    "name": "Weather Service",
    "version": "1.0.0",
    "description": "Get weather information",
    "category": "information",
    "tags": ["weather", "forecast"]
  },
  "activation": {
    "intents": ["weather", "forecast", "rain"],
    "confidence_threshold": 0.6,
    "keywords": ["weather", "rain", "sunny"]
  },
  "tools": ["get_current_weather", "get_forecast"]
}
```

### 2. tools.json - Schemas

```json
{
  "tools": [
    {
      "name": "get_current_weather",
      "description": "Get current weather",
      "parameters": {
        "type": "object",
        "properties": {
          "location": { "type": "string" }
        },
        "required": ["location"]
      },
      "returns": {
        "type": "object",
        "properties": {
          "temperature": { "type": "number" },
          "conditions": { "type": "string" }
        }
      }
    }
  ]
}
```

### 3. index.ts - Implementation

```typescript
import type { ToolImplementation, ToolExecutionResult } from 'react-loop-skills';

export const get_current_weather: ToolImplementation = {
  schema: {
    name: 'get_current_weather',
    description: 'Get current weather',
    parameters: {
      type: 'object',
      properties: {
        location: { type: 'string' }
      },
      required: ['location']
    },
    returns: {
      type: 'object',
      properties: {
        temperature: { type: 'number' },
        conditions: { type: 'string' }
      }
    }
  },
  handler: async (params): Promise<ToolExecutionResult> => {
    const { location } = params;
    
    // Your implementation here
    const data = await fetchWeather(location);
    
    return {
      success: true,
      data: {
        temperature: data.temp,
        conditions: data.conditions
      }
    };
  }
};
```

## Google ADK Integration

This system leverages Google ADK patterns:

- **Agent Loop**: Manages the conversation flow
- **Session Management**: Tracks conversation state
- **Tool Execution**: Runs tools with proper error handling
- **Event Streaming**: Async events for UI updates

## Included Skills

- **Weather**: Get current weather, forecasts, and alerts
- **Appointments**: Book, cancel, and check veterinary appointments
- **Market Prices**: Get commodity prices and historical data

## API Reference

### Hooks

- `useSkillSystem()` - Main system hook
- `useAgent(options)` - Agent loop hook
- `useSkillContext()` - Context access

### Providers

- `SkillProvider` - Wraps your app with skill system

### Components

- `SkillChat` - Ready-to-use chat interface

## License

MIT
