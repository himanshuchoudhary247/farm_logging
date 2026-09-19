# flokiquser UI Integration Analysis

## Executive Summary

The flokiquser React/Ionic app provides an excellent foundation for integrating with the React Loop Skills system. This document identifies what can be leveraged and what needs to be adapted.

---

## 🎯 Current Architecture Overview

### flokiquser Stack
- **Framework:** React 18 + Ionic + Capacitor (mobile)
- **Language:** TypeScript
- **Routing:** React Router
- **State:** Context API (UserContext, LanguageContext, CartContext)
- **HTTP:** Axios with interceptors
- **i18n:** Custom language context with 6 languages
- **Styling:** CSS Modules + Ionic components

### AI Assistant Structure (Already Exists!)
```
src/components/AIAssistant/
├── AIAssistant.tsx      # Main assistant modal
├── AIAssistant.module.css # Styles
├── FlowChatView.tsx     # Chat thread view

src/lib/
├── assistantApi.ts      # API layer for farmer_chat backend
├── apis.ts              # Main API client (1200 lines!)
├── axiosInstance.ts     # HTTP client with auth
```

---

## ✅ What Can Be Leveraged

### 1. **AIAssistant Component** ⭐⭐⭐
**Status:** Already exists and working
**Location:** `src/components/AIAssistant/AIAssistant.tsx`

**Features:**
- ✅ Modal-based chat interface
- ✅ Session management (sessionId)
- ✅ Message threading
- ✅ Retry logic for failed turns
- ✅ Loading states
- ✅ Error handling with toast
- ✅ Language switching
- ✅ Pills/quick actions
- ✅ Voice input (mic button)
- ✅ Auto-scroll to bottom

**Integration Points:**
```typescript
// Current API call
const { data, error } = await sendChatTurn(farmerId, sessionId, text, language);

// Can be replaced with React Loop Skills
import { useAgent } from 'react-loop-skills';
const { sendMessage, isRunning } = useAgent({ session, config });
```

### 2. **Assistant API Layer** ⭐⭐⭐
**Status:** Production-ready API client
**Location:** `src/lib/assistantApi.ts`

**What It Does:**
- ✅ Separate axios instance for farmer_chat backend
- ✅ CORS handling
- ✅ API key support (X-Api-Key header)
- ✅ Language mapping (en → en-IN, hi → hi-IN, etc.)
- ✅ Response parsing per agent type:
  - appointment_supervisor
  - query_agent  
  - weather_alert
- ✅ Pill configuration (env-driven)
- ✅ Bubble text formatting
- ✅ TypeScript types for all responses

**Leverage:**
- The existing `assistantAxios` can call React Loop Skills endpoints
- Keep the pill system - map pills to skills
- Keep language mapping
- Keep bubble text formatter

### 3. **Language/i18n System** ⭐⭐⭐
**Location:** `src/i18n/`, `src/context/LanguageContext.tsx`

**Supported Languages:**
- English (en)
- Hindi (hi)
- Kannada (kn)
- Telugu (te)
- Tamil (ta)
- Malayalam (ml)

**Assistant-Specific:**
```typescript
// Assistant only supports 5 (no Malayalam)
const SUPPORTED_ASSISTANT_LANGS = ['en', 'hi', 'kn', 'te', 'ta'];
const ASSISTANT_LANG_KEY = 'assistantLanguage';
```

**Leverage:**
- ✅ Language switching UI already built
- ✅ Translation keys already exist
- ✅ Can extend for skill-specific translations

### 4. **User Authentication** ⭐⭐
**Location:** `src/context/UserContext.tsx`, `src/lib/auth/`

**What It Provides:**
- ✅ JWT token management
- ✅ Farmer profile in context
- ✅ Phone-based OTP login
- ✅ Role-based access

**Leverage:**
- farmer_id already available in UserContext
- Can pass to React Loop Skills for authorization

### 5. **Error Boundaries & Loading** ⭐⭐
**Location:** `src/components/ErrorBoundary/ErrorBoundary.tsx`

**What It Provides:**
- ✅ Global error catching
- ✅ Fallback UI
- ✅ Can wrap SkillChat

### 6. **Navigation & Routing** ⭐⭐
**Location:** `src/routes/`, `src/lib/navigation.ts`

**What It Provides:**
- ✅ PrivateRoute for authenticated users
- ✅ Navigation utilities
- ✅ Deep linking support
- ✅ History management

---

## 🔧 What Needs Adaptation

### 1. **Replace Backend API with React Loop Skills**

**Current Flow:**
```
UI → assistantApi.ts → farmer_chat backend → Multiple agents
                ↓
        appointment_supervisor
        query_agent
        weather_alert
```

**New Flow with React Loop Skills:**
```
UI → React Loop Skills hooks → Local agent loop → Tools → farmer_chat DB
                ↓
        Intent Detection (Rule-based or LLM)
        Skill Loading (Dynamic)
        Tool Execution
        Context Management
```

**Implementation:**
```typescript
// Option A: Replace assistantApi calls
// In AIAssistant.tsx
import { useSkillSystem, useAgent } from 'react-loop-skills';

const AIAssistant: React.FC = () => {
  const { user } = useUser();
  const { isInitialized, detectIntent, loadSkill } = useSkillSystem({
    initialContext: {
      farmer_id: user?.farmer?.id,
      language: getAssistantLanguage(language),
    },
  });
  
  const { currentSession } = useSkillSystem();
  const { sendMessage, isRunning, currentResponse } = useAgent({
    session: currentSession!,
    config: { max_context_turns: 10 },
  });

  // Replace sendChatTurn with sendMessage
  const runTurn = async (text: string) => {
    await sendMessage(text);
  };
};
```

### 2. **Adapt Message Format**

**Current Message Structure:**
```typescript
interface Message {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  pending?: boolean;
  error?: boolean;
}
```

**React Loop Skills Message:**
```typescript
interface SessionMessage {
  id: string;
  role: 'user' | 'assistant' | 'tool';
  content: string;
  timestamp: Date;
  skill_id?: string;
  tool_calls?: ToolCall[];
}
```

**Adaptation Needed:**
- Map `content` → `text`
- Add `skill_id` for showing which skill answered
- Handle 'tool' role (can be collapsed into assistant)

### 3. **Pills → Skills Mapping**

**Current Pills:**
```typescript
const DEFAULT_PILLS: AssistantPillConfig[] = [
  { key: 'weather', starterText: "What's the weather forecast..." },
  { key: 'appointment', starterText: "I'd like to book an appointment" },
  { key: 'healthReport', starterText: "One of my animals is sick..." },
  { key: 'query', starterText: null },
];
```

**Map to Skills:**
| Pill Key | Skill | Reason |
|----------|-------|--------|
| weather | weather | Direct match |
| appointment | appointments | Direct match |
| healthReport | farm-qa | Animal health queries |
| query | farm-qa | General farm queries |

### 4. **Response Handling**

**Current Response Structure:**
```typescript
interface ChatTurnResponse {
  agent: 'appointment_supervisor' | 'query_agent' | 'weather_alert';
  intent: string | null;
  result: AppointmentSupervisorResult | QueryAgentResult | WeatherAlertResult;
  reply_text?: string;  // Unified text field
}
```

**New Response Structure:**
```typescript
interface AgentResponse {
  content: string;
  skill_id?: string;
  tool_calls?: ToolCall[];
  reasoning?: string;
}
```

**Adaptation:**
- Keep `bubbleTextFor()` function
- Modify to handle React Loop Skills format
- Preserve multi-language support

---

## 🎨 UI Components That Can Be Reused

### From flokiquser:

1. **AIAssistant Modal** (`AIAssistant.tsx`)
   - Replace API calls only
   - Keep UI intact

2. **FlowChatView** (`FlowChatView.tsx`)
   - Shows chat thread
   - Can be reused as-is

3. **Pills/Quick Actions**
   - Map to skills
   - Pre-fill input with starterText

4. **Language Switcher**
   - Already integrated
   - Pass language to React Loop Skills

5. **BottomButton** (`BottomButton.tsx`)
   - Submit/cancel buttons
   - Can style SkillChat submit

6. **ErrorBoundary**
   - Wrap SkillChat

### From React Loop Skills:

1. **SkillChat Component**
   - Can replace AIAssistant
   - Or wrap inside AIAssistant

2. **React Hooks**
   - `useSkillSystem()`
   - `useAgent()`
   - `useSkillContext()`

3. **SkillProvider**
   - Wrap app or just AIAssistant

---

## 📊 Integration Options

### Option 1: **Replace Backend (Minimal UI Changes)**
**Effort:** Low  
**Risk:** Low  
**Approach:**
- Keep AIAssistant component
- Replace `sendChatTurn()` calls with React Loop Skills hooks
- Keep all existing UI
- Map responses to current format

```typescript
// Minimal change in AIAssistant.tsx
const runTurn = async (text: string) => {
  // OLD:
  // const { data, error } = await sendChatTurn(farmerId, sessionId, text, language);
  
  // NEW:
  await sendMessage(text);  // From useAgent()
  const responseText = currentResponse;
  
  setMessages((prev) =>
    prev.map((m) => (m.id === pendingId ? { ...m, pending: false, text: responseText } : m))
  );
};
```

### Option 2: **Use SkillChat Component**
**Effort:** Medium  
**Risk:** Low  
**Approach:**
- Replace AIAssistant with SkillChat
- Customize SkillChat styles to match flokiquser
- Add pills back
- Add language switching

```typescript
// AIAssistant.tsx becomes:
import { SkillChat } from 'react-loop-skills';

const AIAssistant: React.FC = () => {
  return (
    <IonModal isOpen={isOpen}>
      <SkillProvider initialContext={{ farmer_id: user?.farmer?.id }}>
        <SkillChat 
          userName={user?.farmer?.name}
          placeholder="Ask me about your farm..."
        />
      </SkillProvider>
    </IonModal>
  );
};
```

### Option 3: **Hybrid (Recommended)**
**Effort:** Medium  
**Risk:** Medium  
**Approach:**
- Use React Loop Skills as the brain
- Keep flokiquser UI components
- Mix and match best of both

**Implementation:**
```typescript
// Create wrapper component
const EnhancedAIAssistant: React.FC = () => {
  // Use React Loop Skills hooks
  const { skills, loadedSkills, detectIntent } = useSkillContext();
  const { sendMessage, events } = useAgent({ ... });
  
  // But render with flokiquser components
  return (
    <IonModal isOpen={isOpen}>
      <FlowChatView messages={adaptedMessages} />
      <Pills onPillTap={handlePillTap} />
      <InputWithVoice onSubmit={sendMessage} />
    </IonModal>
  );
};
```

---

## 🔑 Key Integration Points

### 1. **Session Management**
**Current:** Uses sessionId string  
**React Loop Skills:** Uses Session object  
**Solution:**
```typescript
const sessionManager = createSessionManager();
const session = sessionManager.create({
  farmer_id: user?.farmer?.id,
  language: assistantLanguage,
});
```

### 2. **Authentication**
**Current:** JWT in axios headers  
**React Loop Skills:** No built-in auth  
**Solution:** Add auth middleware to tool handlers

### 3. **Language Handling**
**Current:** `ASSISTANT_LANG_MAP`  
**React Loop Skills:** Simple language string  
**Solution:** Keep mapping, pass to context

### 4. **Error Handling**
**Current:** Per-request error catching  
**React Loop Skills:** Event-based errors  
**Solution:**
```typescript
useEffect(() => {
  events.forEach(event => {
    if (event.type === 'error') {
      showToast(event.data.message);
    }
  });
}, [events]);
```

---

## 🚀 Recommended Integration Strategy

### Phase 1: Backend Bridge (Week 1)
1. Create adapter between React Loop Skills and farmer_chat DB
2. Expose REST API matching current assistantApi expectations
3. Test with existing AIAssistant component

### Phase 2: Client Integration (Week 2)
1. Add React Loop Skills npm package to flokiquser
2. Create wrapper component
3. Replace API calls with hooks
4. Test end-to-end

### Phase 3: Enhanced Features (Week 3)
1. Add skill pills
2. Show tool execution in UI
3. Add context display
4. Multi-language support for skills

### Phase 4: Migration (Week 4)
1. Migrate existing agents to skills
2. Test with real farmers
3. A/B test old vs new
4. Deprecate old endpoints

---

## 📋 Files to Modify

### High Priority:
1. `src/lib/assistantApi.ts` - Replace API calls
2. `src/components/AIAssistant/AIAssistant.tsx` - Integrate hooks
3. `src/App.tsx` - Add SkillProvider wrapper

### Medium Priority:
4. `src/components/AIAssistant/FlowChatView.tsx` - Add tool display
5. `src/i18n/*.ts` - Add skill translations
6. `package.json` - Add react-loop-skills dependency

### Low Priority:
7. `src/pages/assistant-settings/` - Add skill preferences
8. `src/context/UserContext.tsx` - Add skill permissions

---

## ✅ Checklist

- [ ] Add react-loop-skills to package.json
- [ ] Create SkillProvider wrapper
- [ ] Adapt assistantApi.ts to use skills
- [ ] Modify AIAssistant to use hooks
- [ ] Map existing pills to skills
- [ ] Test with all supported languages
- [ ] Add error boundaries
- [ ] Add loading states
- [ ] Test on mobile (Capacitor)
- [ ] Performance testing

---

## 💡 Key Insights

1. **flokiquser already HAS an AI Assistant** - Don't rebuild, enhance!
2. **Language support is excellent** - 5 languages already supported
3. **Mobile-first** - Ionic/Capacitor means it works on iOS/Android
4. **Session management exists** - Can leverage existing patterns
5. **Pills system is perfect** - Natural mapping to skills

**Bottom Line:** The UI is 80% ready. Focus on integrating the React Loop Skills "brain" with the existing UI "body".
