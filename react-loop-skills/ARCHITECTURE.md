# React Loop Skill System Architecture

## Overview

A React-based intent-driven skill system where each functionality is exposed as a set of tools, organized into skills. Built with Google ADK (Agent Development Kit) patterns for agent loops, tool execution, and state management.

## Core Concepts

### 1. Skills
A **Skill** is a domain-specific capability bundle containing:
- **Name**: Unique identifier
- **Description**: What the skill does (used for intent matching)
- **Tools**: Array of tools that implement the skill's functionality
- **Metadata**: Tags, category, version, etc.

### 2. Tools
A **Tool** is an executable function with:
- **Name**: Unique identifier within the skill
- **Description**: What the tool does (used by LLM/Agent to select tools)
- **Parameters**: JSON Schema defining expected inputs
- **Returns**: JSON Schema defining expected outputs
- **Handler**: The actual implementation (TypeScript function)

### 3. React Loop
The **React Loop** is an agentic loop built on React patterns:
```
User Input → Intent Detection → Skill Loading → Tool Selection → Tool Execution → Response
     ↑                                                                              ↓
     └─────────────────────────← State Update ←───────────────────────────────────┘
```

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        React Frontend                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    │
│  │  Chat Input  │───→│ Intent       │───→│ Skill        │    │
│  │  Component   │    │ Detector     │    │ Loader       │    │
│  └──────────────┘    └──────────────┘    └──────────────┘    │
│         │                     │                   │            │
│         │              ┌──────┴──────┐           │            │
│         │              │             │           │            │
│         │         ┌────┴────┐   ┌────┴────┐     │            │
│         │         │ Intent  │   │ Skill   │     │            │
│         │         │ Match   │   │ Registry│     │            │
│         │         └─────────┘   └─────────┘     │            │
│         │                                        ↓            │
│         │                              ┌──────────────┐       │
│         │                              │ Loaded Skill │       │
│         │                              │ (Tools)      │       │
│         │                              └──────────────┘       │
│         │                                     │               │
│         │                                     ↓               │
│         │                              ┌──────────────┐       │
│         └─────────────────────────────│ Tool Selector│       │
│                                       │ (ADK-based)  │       │
│                                       └──────────────┘       │
│                                              │                │
│                                              ↓                │
│                                       ┌──────────────┐       │
│                                       │ Tool Executor│       │
│                                       │ (ADK Runner) │       │
│                                       └──────────────┘       │
│                                              │                │
│                                              ↓                │
│                                       ┌──────────────┐       │
│                                       │   Response   │       │
│                                       │   Renderer   │       │
│                                       └──────────────┘       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ JSON Skill Registry
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                     Skill Registry (JSON)                        │
├─────────────────────────────────────────────────────────────────┤
│ skills/                                                         │
│ ├── weather/                                                    │
│ │   ├── skill.json         # Skill metadata & description        │
│ │   ├── tools.json         # Tool schemas (params/returns)       │
│ │   └── index.ts           # Tool implementations                │
│ ├── appointments/                                               │
│ │   ├── skill.json                                              │
│ │   ├── tools.json                                              │
│ │   └── index.ts                                                │
│ └── ...                                                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ ADK Agent Loop
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    Google ADK Integration                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐     │
│  │   Session    │───→│   Agent      │───→│   Tool       │     │
│  │   Manager    │    │   Loop       │    │   Registry   │     │
│  └──────────────┘    └──────────────┘    └──────────────┘     │
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐     │
│  │   Event      │───→│   State      │───→│   Runner     │     │
│  │   Stream     │    │   Manager    │    │   (Async)    │     │
│  └──────────────┘    └──────────────┘    └──────────────┘     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
react-loop-skills/
├── ARCHITECTURE.md                 # This file
├── README.md                       # Quick start guide
│
├── src/                            # Core system implementation
│   ├── core/                       # Core skill system
│   │   ├── SkillRegistry.ts        # JSON skill loader
│   │   ├── ToolRegistry.ts         # Tool registration
│   │   ├── IntentMatcher.ts        # Intent detection
│   │   └── types.ts                # Core type definitions
│   │
│   ├── adk/                        # Google ADK integration
│   │   ├── AgentLoop.ts            # ADK-based agent loop
│   │   ├── SessionManager.ts       # Conversation state
│   │   ├── ToolAdapter.ts          # Bridge skills → ADK tools
│   │   └── EventStream.ts          # Event handling
│   │
│   ├── react/                      # React integration
│   │   ├── hooks/                  # React hooks
│   │   │   ├── useSkillSystem.ts   # Main hook
│   │   │   ├── useIntent.ts        # Intent detection hook
│   │   │   ├── useTool.ts          # Tool execution hook
│   │   │   └── useSession.ts       # Session management hook
│   │   │
│   │   ├── components/             # React components
│   │   │   ├── SkillChat.tsx       # Main chat interface
│   │   │   ├── ToolExecutor.tsx    # Tool execution UI
│   │   │   ├── IntentDisplay.tsx   # Intent visualization
│   │   │   └── SkillPicker.tsx     # Skill selection
│   │   │
│   │   └── providers/              # Context providers
│   │       ├── SkillProvider.tsx   # Skill system context
│   │       └── ADKProvider.tsx     # ADK context
│   │
│   └── utils/                      # Utilities
│       ├── logger.ts               # Logging utilities
│       └── validators.ts           # Schema validation
│
├── skills/                         # Skill definitions (JSON + TS)
│   ├── weather/                    # Weather skill
│   │   ├── skill.json              # Skill metadata
│   │   ├── tools.json              # Tool schemas
│   │   └── index.ts                # Tool implementations
│   │
│   ├── appointments/               # Appointment skill
│   │   ├── skill.json
│   │   ├── tools.json
│   │   └── index.ts
│   │
│   ├── market-prices/              # Market prices skill
│   │   ├── skill.json
│   │   ├── tools.json
│   │   └── index.ts
│   │
│   └── ...                         # More skills
│
├── registry/                       # Generated/compiled registry
│   ├── skills.json                 # Combined skill registry
│   └── tool-manifest.json          # Tool manifest for ADK
│
└── tests/                          # Test suite
    ├── unit/
    ├── integration/
    └── e2e/
```

## JSON Skill Definition Format

### skill.json
```json
{
  "id": "weather",
  "name": "Weather Service",
  "version": "1.0.0",
  "description": "Get weather information and alerts for your location",
  "category": "information",
  "tags": ["weather", "forecast", "alerts"],
  "activation": {
    "intents": ["weather", "forecast", "rain", "temperature"],
    "confidence_threshold": 0.7
  },
  "tools": ["get_current_weather", "get_forecast", "check_alerts"],
  "dependencies": [],
  "config": {
    "api_key_required": true,
    "rate_limit": 100
  }
}
```

### tools.json
```json
{
  "tools": [
    {
      "name": "get_current_weather",
      "description": "Get the current weather conditions for a location",
      "parameters": {
        "type": "object",
        "properties": {
          "location": {
            "type": "string",
            "description": "City name or coordinates"
          },
          "units": {
            "type": "string",
            "enum": ["celsius", "fahrenheit"],
            "default": "celsius"
          }
        },
        "required": ["location"]
      },
      "returns": {
        "type": "object",
        "properties": {
          "temperature": {"type": "number"},
          "conditions": {"type": "string"},
          "humidity": {"type": "number"}
        }
      }
    }
  ]
}
```

## React Loop Flow

### 1. Initialization
```typescript
// Load skill registry
const registry = await SkillRegistry.load('./skills');

// Initialize ADK session
const session = await SessionManager.create({
  skillRegistry: registry,
  systemPrompt: "You are a helpful farming assistant..."
});
```

### 2. Intent Detection
```typescript
// Match user input to skills
const intent = await IntentMatcher.match(userInput, {
  availableSkills: registry.getAll(),
  context: session.context
});

// Result: { skill: "weather", confidence: 0.92, tools: [...] }
```

### 3. Skill Loading
```typescript
// Dynamically load skill tools
const skill = await registry.loadSkill(intent.skill);
const tools = skill.getTools();
```

### 4. ADK Agent Loop
```typescript
// Run ADK agent with loaded tools
const runner = new AgentLoop({
  session,
  tools,
  model: "gemini-2.0-flash"
});

for await (const event of runner.run(userInput)) {
  // Handle events: tool_call, tool_response, thinking, response
  renderEvent(event);
}
```

### 5. Tool Execution
```typescript
// Tool handler (in skill implementation)
export const getCurrentWeather: ToolHandler = async (params) => {
  const { location, units } = params;
  const data = await weatherAPI.get(location, { units });
  return {
    temperature: data.temp,
    conditions: data.conditions,
    humidity: data.humidity
  };
};
```

## Key Design Principles

1. **Intent-Based Loading**: Skills are loaded on-demand based on detected intent
2. **Declarative Tools**: Tool schemas in JSON, implementations in TypeScript
3. **ADK Integration**: Uses Google ADK for agent loops, state management, and tool execution
4. **React Native**: Built with React hooks and context for seamless integration
5. **Extensible**: Easy to add new skills by adding JSON + TS files
6. **Type-Safe**: Full TypeScript support with generated types from JSON schemas

## Integration Points

- **Google ADK**: Core agent loop, event streaming, session management
- **React**: UI components, hooks, context providers
- **Existing Services**: Weather, Appointments, Market Prices, Emergency Alerts
- **LLM**: Gemini models via ADK for intent detection and responses
