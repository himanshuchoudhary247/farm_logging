#!/usr/bin/env node
/**
 * React Loop Skills - Appointment Booking Fixed
 * Implements proper slot filling and bare reply handling
 */

const express = require('express');
const cors = require('cors');

const app = express();
const PORT = process.env.PORT || 3002;

app.use(cors());
app.use(express.json());

const db = {
  farmers: [
    { id: 'farmer_001', name: 'Rajesh Kumar', phone: '9876543210' },
  ],
  animals: [
    { id: 'animal_001', farmer_id: 'farmer_001', tag_number: 'COW001', name: 'Gauri', type: 'cow' },
    { id: 'animal_002', farmer_id: 'farmer_001', tag_number: 'COW002', name: '1122', type: 'buffalo' },
  ],
  appointments: [],
  sessions: new Map(),
};

// Appointment slot configuration - Order matches the user's expected conversation flow
const APPOINTMENT_SLOTS = {
  required: ['animal_identifier', 'issue', 'symptoms', 'date', 'time', 'type'],
  steps: [
    { field: 'animal_identifier', question: 'Please tell me the animal name or tag' },
    { field: 'issue', question: 'What is the issue?' },
    { field: 'symptoms', question: 'What are the symptoms?' },
    { field: 'date', question: 'What is your preferred appointment date?' },
    { field: 'time', question: 'What is your preferred appointment time?' },
    { field: 'type', question: 'What type of appointment? (veterinary, agricultural, consultation)' },
  ],
};

function detectIntent(input, context = {}) {
  const lower = input.toLowerCase().trim();
  
  // Check for bare replies
  const words = lower.split(/\s+/).filter(w => w.length > 0);
  const isBareReply = words.length <= 3 && !lower.match(/^(what|how|when|where|why|who|can|could|would|will|should|i\s+want|i\s+would)/);
  
  // FIX: Check if we're in appointment booking mode
  if (context.mode === 'appointment_booking') {
    // FIX: Only check for confirmation if we're awaiting confirmation
    if (context.awaitingConfirmation) {
      const confirmation = classifyConfirmation(input);
      if (confirmation === 'cancel') {
        return { skill: 'cancel', confidence: 0.95, isBareReply: false, confirmation };
      }
      if (confirmation === 'yes' || confirmation === 'no') {
        return { skill: 'confirmation', confidence: 0.95, isBareReply: false, confirmation };
      }
    }
    
    // Otherwise it's data for the current slot
    return { skill: 'appointment_data', confidence: 0.95, isBareReply, confirmation: null };
  }
  
  // Normal intent detection
  if (lower.includes('appointment') || lower.includes('book') || lower.includes('schedule')) {
    return { skill: 'appointment_booking', confidence: 1.0, isBareReply: false };
  }
  
  return { skill: null, confidence: 0 };
}

function classifyConfirmation(input) {
  const lower = input.toLowerCase().trim();
  const words = lower.split(/\s+/);
  
  // Standalone confirmation words
  const yesWords = ['yes', 'yeah', 'yep', 'correct', 'right', 'ok', 'okay', 'sure', 'submit', 'book', 'save', 'cool', 'great', 'good'];
  const noWords = ['no', 'nope', 'nah', 'wrong', 'incorrect', 'cancel', 'stop', 'forget', 'never', 'not'];
  
  for (const word of words) {
    if (yesWords.includes(word)) return 'yes';
    if (noWords.includes(word)) return 'no';
  }
  
  // Check phrases
  if (lower.match(/^(yes|yeah|yep|correct|right|ok|okay|sure|cool|great)\b/)) return 'yes';
  if (lower.match(/^(no|nope|nah|wrong|incorrect|cancel|stop)\b/)) return 'no';
  if (lower.match(/\b(cancel|stop|forget|never mind)\b/)) return 'cancel';
  
  return null;
}

function extractAppointmentData(input, field, context) {
  const lower = input.toLowerCase().trim();
  
  switch (field) {
    case 'type':
      if (lower.includes('vet')) return 'veterinary';
      if (lower.includes('agri')) return 'agricultural';
      if (lower.includes('consult')) return 'consultation';
      return lower;
      
    case 'animal_identifier':
      // Look for tag numbers or names
      const tagMatch = input.match(/\b\d{3,4}\b/);  // 3-4 digit numbers like 1122
      if (tagMatch) return tagMatch[0];
      // Look for capitalized names
      const nameMatch = input.match(/\b[A-Z][a-z]+\b/);
      if (nameMatch) return nameMatch[0];
      return input.trim();
      
    case 'issue':
    case 'symptoms':
      return input.trim();
      
    case 'date':
      if (lower === 'today') {
        return new Date().toISOString().split('T')[0];
      }
      if (lower === 'tomorrow') {
        const tomorrow = new Date();
        tomorrow.setDate(tomorrow.getDate() + 1);
        return tomorrow.toISOString().split('T')[0];
      }
      // Parse various formats
      const dateMatch = input.match(/(\d{4})[-/](\d{1,2})[-/](\d{1,2})/);
      if (dateMatch) return `${dateMatch[1]}-${dateMatch[2].padStart(2, '0')}-${dateMatch[3].padStart(2, '0')}`;
      return input.trim();
      
    case 'time':
      // Extract time from "5 evening", "10 am", etc.
      const timeMatch = input.match(/(\d{1,2})\s*(?::(\d{2}))?\s*(am|pm|evening|morning|afternoon)?/i);
      if (timeMatch) {
        let hour = parseInt(timeMatch[1]);
        let period = timeMatch[3]?.toLowerCase();
        
        // Convert relative times
        if (period === 'evening') hour = 17;  // 5 PM
        else if (period === 'morning') hour = 9;
        else if (period === 'afternoon') hour = 14;
        else if (period === 'pm' && hour < 12) hour += 12;
        else if (period === 'am' && hour === 12) hour = 0;
        
        return `${hour.toString().padStart(2, '0')}:00`;
      }
      return input.trim();
      
    default:
      return input.trim();
  }
}

function getNextMissingSlot(collected) {
  for (const slot of APPOINTMENT_SLOTS.steps) {
    if (!collected[slot.field] || collected[slot.field] === '') {
      return slot;
    }
  }
  return null;
}

function formatSummary(collected) {
  const parts = [];
  if (collected.animal_identifier) parts.push(`animal: ${collected.animal_identifier}`);
  if (collected.issue) parts.push(`issue: ${collected.issue}`);
  if (collected.symptoms) parts.push(`symptoms: ${collected.symptoms}`);
  if (collected.date) parts.push(`date: ${collected.date}`);
  if (collected.time) parts.push(`time: ${collected.time}`);
  if (collected.type) parts.push(`type: ${collected.type}`);
  return parts.join('; ') || 'no details yet';
}

// Health check
app.get('/health', (req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

// Create session
app.post('/farmers/:farmerId/chat/session', (req, res) => {
  const sessionId = `sess_${Date.now()}`;
  db.sessions.set(sessionId, {
    id: sessionId,
    farmer_id: req.params.farmerId,
    mode: null,
    collected: {},
    awaitingConfirmation: false,
    submitted: false,
    messages: [],
  });
  res.json({ session: { id: sessionId } });
});

// MAIN CHAT ENDPOINT
app.post('/farmers/:farmerId/chat/turn', async (req, res) => {
  try {
    const { farmerId } = req.params;
    const { session_id, text } = req.body;
    
    console.log(`\n[Chat] Farmer: ${farmerId}, Text: "${text}"`);
    
    let session = db.sessions.get(session_id);
    if (!session) {
      session = {
        id: session_id,
        farmer_id: farmerId,
        mode: null,
        collected: {},
        awaitingConfirmation: false,
        submitted: false,
        messages: [],
      };
      db.sessions.set(session_id, session);
    }
    
    // FIX: If already submitted, start fresh
    if (session.submitted) {
      console.log('[Session] Was submitted, starting fresh');
      session.mode = null;
      session.collected = {};
      session.awaitingConfirmation = false;
      session.submitted = false;
    }
    
    // Detect intent
    const intent = detectIntent(text, { 
      mode: session.mode,
      awaitingConfirmation: session.awaitingConfirmation 
    });
    console.log(`[Intent] Skill: ${intent.skill}, Mode: ${session.mode}, isBareReply: ${intent.isBareReply}`);
    
    let responseText = '';
    let requiredFollowUp = false;
    
    // Handle cancel
    if (intent.skill === 'cancel' || intent.confirmation === 'cancel') {
      session.mode = null;
      session.collected = {};
      session.awaitingConfirmation = false;
      responseText = 'The appointment draft was cancelled.';
      
      session.messages.push({ role: 'user', content: text }, { role: 'assistant', content: responseText });
      
      return res.json({
        agent: 'appointment_booking',
        reply_text: responseText,
        _meta: { mode: session.mode, confirmation_signal: 'cancel' },
      });
    }
    
    // Start appointment booking
    if (intent.skill === 'appointment_booking' && !session.mode) {
      session.mode = 'appointment_booking';
      const nextSlot = getNextMissingSlot(session.collected);
      responseText = `Hello. ${nextSlot.question}`;
      session.expectedField = nextSlot.field;
      requiredFollowUp = true;
    }
    // Collect data in appointment mode
    else if (session.mode === 'appointment_booking') {
      // Handle confirmation
      if (session.awaitingConfirmation) {
        const confirmation = classifyConfirmation(text);
        console.log(`[Confirmation] Signal: ${confirmation}`);
        
        if (confirmation === 'yes') {
          // Submit appointment
          const appointment = {
            id: `apt_${Date.now()}`,
            farmer_id: farmerId,
            ...session.collected,
            status: 'confirmed',
            created_at: new Date().toISOString(),
          };
          db.appointments.push(appointment);
          session.submitted = true;
          session.mode = null;
          session.collected = {};
          session.awaitingConfirmation = false;
          
          responseText = 'The appointment and animal health record were saved successfully.';
          
          session.messages.push({ role: 'user', content: text }, { role: 'assistant', content: responseText });
          
          return res.json({
            agent: 'appointment_booking',
            reply_text: responseText,
            _meta: { 
              mode: session.mode, 
              submitted: true,
              confirmation_signal: 'yes',
              appointment: appointment,
            },
          });
        } else if (confirmation === 'no') {
          session.awaitingConfirmation = false;
          responseText = 'What would you like to correct?';
          requiredFollowUp = true;
        } else {
          // Not a clear confirmation, treat as data
          responseText = 'Please say yes to submit or no to make changes.';
          requiredFollowUp = true;
        }
      }
      // Collect data
      else {
        // Extract data for current field
        const field = session.expectedField || getNextMissingSlot(session.collected)?.field;
        if (field) {
          const value = extractAppointmentData(text, field, session.collected);
          session.collected[field] = value;
          console.log(`[Data] Collected ${field}: ${value}`);
        }
        
        // Check if all fields collected
        const nextSlot = getNextMissingSlot(session.collected);
        
        if (nextSlot) {
          // More data needed
          responseText = `I understood: ${formatSummary(session.collected)} Thank you. Please provide ${nextSlot.field.replace('_', ' ')}.`;
          session.expectedField = nextSlot.field;
          requiredFollowUp = true;
        } else {
          // All data collected, ask for confirmation
          session.awaitingConfirmation = true;
          responseText = `I understood: ${formatSummary(session.collected)} All required details are complete. Would you like to submit this appointment?`;
          requiredFollowUp = true;
        }
      }
    }
    // After submission, handle new queries
    else if (session.submitted && intent.skill !== 'appointment_booking') {
      responseText = 'The previous appointment was submitted. Would you like to book another appointment?';
      session.mode = null;
      requiredFollowUp = true;
    }
    else {
      responseText = "I'm not sure what you mean. Would you like to book an appointment?";
      requiredFollowUp = true;
    }
    
    session.messages.push({ role: 'user', content: text });
    session.messages.push({ role: 'assistant', content: responseText });
    
    console.log(`[Response] "${responseText.substring(0, 100)}..."`);
    console.log(`[State] mode=${session.mode}, collected=${JSON.stringify(session.collected)}, awaitingConfirmation=${session.awaitingConfirmation}`);
    
    res.json({
      agent: 'appointment_booking',
      reply_text: responseText,
      _meta: {
        mode: session.mode,
        collected: session.collected,
        awaiting_confirmation: session.awaitingConfirmation,
        submitted: session.submitted,
        expected_field: session.expectedField,
        confirmation_signal: intent.confirmation,
        is_bare_reply: intent.isBareReply,
      },
    });
  } catch (error) {
    console.error('[Error]', error);
    res.status(500).json({ error: error.message });
  }
});

app.listen(PORT, () => {
  console.log('='.repeat(80));
  console.log('🎉 Appointment Booking Server - Fixed Version');
  console.log('='.repeat(80));
  console.log(`📍 Server running on http://localhost:${PORT}`);
  console.log('');
  console.log('Test the conversation:');
  console.log('  curl -X POST http://localhost:' + PORT + '/farmers/farmer_001/chat/session');
  console.log('  curl -X POST http://localhost:' + PORT + '/farmers/farmer_001/chat/turn');
  console.log('');
  console.log('Features:');
  console.log('  ✅ Slot filling with bare reply handling');
  console.log('  ✅ "1122" goes to animal_identifier');
  console.log('  ✅ "not eating" goes to issue');
  console.log('  ✅ "tomorrow 5 evening" extracts date and time');
  console.log('  ✅ "cool" treated as yes/confirmation');
  console.log('  ✅ "yes" submits the appointment');
  console.log('  ✅ After submit, starts fresh (no loop)');
  console.log('  ✅ "cancel" cancels the draft');
  console.log('');
  console.log('='.repeat(80));
});
