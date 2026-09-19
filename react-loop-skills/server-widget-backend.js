#!/usr/bin/env node
/**
 * Widget-Enhanced Backend for Chocolate AI Assistant
 * Returns widget responses for progressive verification flow
 */

const express = require('express');
const cors = require('cors');

const app = express();
const PORT = process.env.PORT || 8079;

app.use(cors());
app.use(express.json());

// Mock database
const db = {
  farmers: [{ id: 'demo-farmer', name: 'Ravi Demo' }],
  animals: [
    { id: 'animal_001', farmer_id: 'demo-farmer', tag: 'COW001', name: 'Gauri', type: 'cow', emoji: '🐄' },
    { id: 'animal_002', farmer_id: 'demo-farmer', tag: 'BUF001', name: 'Lakshmi', type: 'buffalo', emoji: '🐃' },
    { id: 'animal_003', farmer_id: 'demo-farmer', tag: 'GOAT001', name: 'Moti', type: 'goat', emoji: '🐐' },
  ],
  commonIssues: [
    { id: 'not_eating', label: 'Not Eating', emoji: '🍽️' },
    { id: 'fever', label: 'Fever', emoji: '🌡️' },
    { id: 'cough', label: 'Cough', emoji: '😷' },
    { id: 'limping', label: 'Limping', emoji: '🦵' },
    { id: 'injury', label: 'Injury', emoji: '🩹' },
    { id: 'breathing', label: 'Breathing Issue', emoji: '🫁' },
    { id: 'skin', label: 'Skin Problem', emoji: '🔴' },
  ],
  symptoms: [
    { id: 'loss_appetite', label: 'Loss of appetite' },
    { id: 'lethargy', label: 'Lethargy (low energy)' },
    { id: 'fever', label: 'Fever' },
    { id: 'diarrhea', label: 'Diarrhea' },
    { id: 'vomiting', label: 'Vomiting' },
    { id: 'nasal_discharge', label: 'Nasal discharge' },
    { id: 'coughing', label: 'Coughing' },
  ],
  sessions: new Map(),
};

// Health check
app.get('/health', (req, res) => {
  res.json({ status: 'ok', service: 'widget-backend', timestamp: new Date().toISOString() });
});

// Get farmer's animals
app.get('/farmers/:farmerId/animals', (req, res) => {
  const animals = db.animals.filter(a => a.farmer_id === req.params.farmerId);
  res.json({ 
    animals: animals.map(a => ({
      id: a.id,
      tag: a.tag,
      name: a.name,
      type: a.type,
      emoji: a.emoji,
      display: `${a.emoji} ${a.name} (${a.tag})`
    }))
  });
});

// Helper: fuzzy search animals
function searchAnimals(query, farmerId) {
  const animals = db.animals.filter(a => a.farmer_id === farmerId);
  const lower = query.toLowerCase();
  
  const exact = animals.filter(a => 
    a.tag.toLowerCase() === lower || 
    a.name.toLowerCase() === lower
  );
  
  const partial = animals.filter(a => 
    a.tag.toLowerCase().includes(lower) || 
    a.name.toLowerCase().includes(lower)
  ).filter(a => !exact.includes(a));
  
  return [...exact, ...partial].slice(0, 3);
}

// Create session
app.post('/farmers/:farmerId/chat/session', (req, res) => {
  const sessionId = `sess_${Date.now()}`;
  db.sessions.set(sessionId, {
    id: sessionId,
    farmer_id: req.params.farmerId,
    step: 'start',
    collected: {},
    intent: null,
  });
  res.json({ session: { id: sessionId } });
});

// WIDGET-ENABLED CHAT TURN
app.post('/farmers/:farmerId/chat/turn', (req, res) => {
  try {
    const { farmerId } = req.params;
    const { session_id, text, language, widget_action, selected_values, text_input } = req.body;
    
    let session = db.sessions.get(session_id);
    if (!session) {
      session = { 
        id: session_id, 
        farmer_id: farmerId, 
        step: 'start', 
        collected: {},
        intent: null 
      };
      db.sessions.set(session_id, session);
    }

    // Handle widget actions
    if (widget_action) {
      console.log('[Widget Action]', widget_action, 'Value:', text_input || selected_values);
      
      // Route based on current step and action
      switch (session.step) {
        case 'verify_animal':
          if (widget_action === 'confirm' || text_input === 'yes') {
            session.step = 'issue';
          } else if (widget_action === 'change' || text_input === 'no') {
            session.step = 'animal';
          }
          break;
          
        case 'verify_issue':
          if (widget_action === 'confirm' || text_input === 'yes') {
            session.step = 'symptoms';
          } else {
            session.step = 'issue';
          }
          break;
          
        case 'symptoms':
          if (widget_action === 'confirm_symptoms') {
            session.collected.symptoms = selected_values || [];
            session.step = 'summary';
          }
          break;
          
        case 'summary':
          if (widget_action === 'submit') {
            session.step = 'complete';
            session.submitted = true;
          }
          break;
          
        default:
          // Handle select actions
          if (widget_action.startsWith('select_')) {
            const field = widget_action.replace('select_', '');
            session.collected[field] = text_input;
            session.step = `verify_${field}`;
          }
      }
    } else {
      // Regular text input - detect intent and set step
      const lowerText = text.toLowerCase();
      
      if (!session.intent) {
        if (lowerText.includes('appointment') || lowerText.includes('book')) {
          session.intent = 'appointment_booking';
          session.step = 'animal';
        } else if (lowerText.includes('weather')) {
          session.intent = 'weather_query';
        } else {
          session.intent = 'farm_query';
        }
      }
      
      // Store the text input for the current step
      if (session.step === 'animal' && !widget_action) {
        // User typed animal directly
        const matches = searchAnimals(text, farmerId);
        if (matches.length > 0) {
          session.collected.animal = matches[0];
          session.step = 'verify_animal';
        } else {
          session.tempAnimalInput = text;
          session.step = 'animal_select';
        }
      }
    }

    // Build response based on current step
    let response = {};

    // STEP: Start / Intent Detection
    if (session.step === 'start') {
      response = {
        agent: 'appointment_supervisor',
        intent: session.intent,
        reply_type: 'text',
        reply_text: "Hello! How can I help you today?",
        result: {
          state: 'start',
          draft: {},
          missing_fields: ['intent'],
        },
        _meta: {
          step: 'start',
          collected: session.collected
        }
      };
    }

    // STEP: Animal Selection with Widget
    else if (session.step === 'animal') {
      const animals = db.animals.filter(a => a.farmer_id === farmerId);
      
      response = {
        agent: 'appointment_supervisor',
        intent: 'appointment_booking',
        reply_type: 'widget',
        reply_text: "Select your animal:",
        widget: {
          type: 'single_select',
          title: 'Select Animal',
          subtitle: 'Choose from your animals or type a tag',
          options: [
            ...animals.map(a => ({
              id: a.id,
              label: `${a.emoji} ${a.name}`,
              sublabel: `Tag: ${a.tag}`,
              value: JSON.stringify(a),  // Send full animal object
              type: 'button',
              action: 'select_animal'
            })),
            {
              id: 'other',
              label: '✏️ Other (type tag)',
              value: 'other',
              type: 'text_input',
              action: 'type_other',
              placeholder: 'Type animal tag (e.g., COW001, 1122)'
            }
          ]
        },
        result: {
          state: 'awaiting_animal',
          draft: session.collected,
          missing_fields: ['animal_identifier', 'issue', 'symptoms', 'date', 'time']
        },
        _meta: {
          step: 'animal',
          collected: session.collected
        }
      };
    }

    // STEP: Verify Animal (Progressive Confirmation)
    else if (session.step === 'verify_animal') {
      const animal = session.collected.animal;
      
      response = {
        agent: 'appointment_supervisor',
        intent: 'appointment_booking',
        reply_type: 'widget',
        reply_text: `✓ Selected: ${animal.emoji} ${animal.name} (${animal.tag})`,
        widget: {
          type: 'confirmation',
          title: 'Confirm Animal',
          subtitle: `Is ${animal.name} the correct animal?`,
          options: [
            { 
              id: 'yes', 
              label: '✓ Yes, correct', 
              value: 'yes', 
              type: 'button', 
              action: 'confirm',
              primary: true
            },
            { 
              id: 'no', 
              label: '✗ No, change', 
              value: 'no', 
              type: 'button', 
              action: 'change' 
            }
          ]
        },
        result: {
          state: 'verify_animal',
          draft: session.collected,
          missing_fields: ['issue', 'symptoms', 'date', 'time']
        },
        _meta: {
          step: 'verify_animal',
          collected: session.collected
        }
      };
    }

    // STEP: Issue Selection with Widget
    else if (session.step === 'issue') {
      response = {
        agent: 'appointment_supervisor',
        intent: 'appointment_booking',
        reply_type: 'widget',
        reply_text: "What's the issue?",
        widget: {
          type: 'single_select',
          title: 'Select Issue',
          subtitle: 'Common issues:',
          options: [
            ...db.commonIssues.map(i => ({
              id: i.id,
              label: `${i.emoji} ${i.label}`,
              value: i.id,
              type: 'button',
              action: 'select_issue'
            })),
            {
              id: 'other',
              label: '✏️ Other issue',
              value: 'other',
              type: 'text_input',
              action: 'type_issue',
              placeholder: 'Describe the issue...'
            }
          ]
        },
        result: {
          state: 'awaiting_issue',
          draft: session.collected,
          missing_fields: ['issue', 'symptoms', 'date', 'time']
        },
        _meta: {
          step: 'issue',
          collected: session.collected
        }
      };
    }

    // STEP: Verify Issue (Progressive Confirmation)
    else if (session.step === 'verify_issue') {
      const issue = session.collected.issue;
      
      response = {
        agent: 'appointment_supervisor',
        intent: 'appointment_booking',
        reply_type: 'widget',
        reply_text: `✓ Issue: ${issue.emoji || '📝'} ${issue.label || issue}`,
        widget: {
          type: 'confirmation',
          title: 'Confirm Issue',
          subtitle: `Is "${issue.label || issue}" the correct issue?`,
          options: [
            { id: 'yes', label: '✓ Yes, correct', value: 'yes', type: 'button', action: 'confirm', primary: true },
            { id: 'no', label: '✗ No, change', value: 'no', type: 'button', action: 'change' }
          ]
        },
        result: {
          state: 'verify_issue',
          draft: session.collected,
          missing_fields: ['symptoms', 'date', 'time']
        },
        _meta: {
          step: 'verify_issue',
          collected: session.collected
        }
      };
    }

    // STEP: Symptoms (Multi-Select Widget)
    else if (session.step === 'symptoms') {
      response = {
        agent: 'appointment_supervisor',
        intent: 'appointment_booking',
        reply_type: 'widget',
        reply_text: "What symptoms do you observe?",
        widget: {
          type: 'multi_select',
          title: 'Select Symptoms',
          subtitle: 'Choose all that apply:',
          min_selections: 1,
          max_selections: 3,
          options: db.symptoms.map(s => ({
            id: s.id,
            label: s.label,
            value: s.id,
            type: 'checkbox'
          })),
          continue_button: {
            label: 'Continue',
            action: 'confirm_symptoms'
          }
        },
        result: {
          state: 'awaiting_symptoms',
          draft: session.collected,
          missing_fields: ['date', 'time']
        },
        _meta: {
          step: 'symptoms',
          collected: session.collected
        }
      };
    }

    // STEP: Summary with Edit/Submit
    else if (session.step === 'summary') {
      const animal = session.collected.animal;
      const issue = session.collected.issue;
      
      response = {
        agent: 'appointment_supervisor',
        intent: 'appointment_booking',
        reply_type: 'widget',
        reply_text: "Here's your appointment summary:",
        widget: {
          type: 'summary',
          title: '📋 Appointment Summary',
          options: [
            { id: 'animal', label: 'Animal', value: `${animal.emoji} ${animal.name} (${animal.tag})`, action: 'edit_animal' },
            { id: 'issue', label: 'Issue', value: `${issue.emoji || '📝'} ${issue.label || issue}`, action: 'edit_issue' },
            { id: 'symptoms', label: 'Symptoms', value: (session.collected.symptoms || []).join(', ') || 'None selected', action: 'edit_symptoms' },
            { id: 'date', label: 'Date', value: 'Tomorrow', action: 'edit_date' },
            { id: 'time', label: 'Time', value: '10:00 AM', action: 'edit_time' },
          ],
          continue_button: {
            label: '✅ Submit Appointment',
            action: 'submit'
          }
        },
        result: {
          state: 'summary',
          draft: session.collected,
          missing_fields: []
        },
        _meta: {
          step: 'summary',
          collected: session.collected
        }
      };
    }

    // STEP: Complete / Success
    else if (session.step === 'complete') {
      response = {
        agent: 'appointment_supervisor',
        intent: 'appointment_booking',
        reply_type: 'widget',
        reply_text: '✅ Appointment saved successfully!',
        widget: {
          type: 'success',
          title: 'Appointment Confirmed',
          subtitle: 'Your appointment has been scheduled.',
          options: [
            { id: 'new', label: '📝 Book Another', value: 'new', type: 'button', action: 'new_booking', primary: true },
            { id: 'done', label: '👋 Done', value: 'done', type: 'button', action: 'finish' }
          ]
        },
        result: {
          status: 'submitted',
          draft: session.collected,
          ai_recommendation: {
            first_aid_advice: "Ensure the animal has access to fresh, clean water. Monitor symptoms closely and contact vet if condition worsens."
          }
        },
        _meta: {
          step: 'complete',
          collected: session.collected,
          submitted: true
        }
      };
    }

    // Weather query (fallback)
    else if (session.intent === 'weather_query') {
      response = {
        agent: 'weather_alert',
        intent: 'weather_forecast',
        reply_type: 'text',
        reply_text: "High weather risk detected. Take protective action for livestock and fodder. Move livestock to covered shelter before evening.",
        result: {
          weather: {
            risk_level: 'high',
            summary: 'High weather risk detected',
            advisories: ['Take protective action', 'Move livestock to covered shelter']
          }
        }
      };
    }

    // Farm query (fallback)
    else {
      const animalCount = db.animals.filter(a => a.farmer_id === farmerId).length;
      response = {
        agent: 'query_agent',
        intent: 'farm_query',
        reply_type: 'text',
        reply_text: `You have ${animalCount} animals registered on your farm.`,
        result: {
          answer: `You have ${animalCount} animals registered on your farm.`,
          sql: null,
          data: null
        }
      };
    }

    // Update session
    db.sessions.set(session_id, session);
    
    res.json(response);
    
  } catch (error) {
    console.error('[Error]', error);
    res.status(500).json({ error: error.message });
  }
});

app.listen(PORT, () => {
  console.log('='.repeat(80));
  console.log('🍫 Widget-Enhanced Chocolate Backend');
  console.log('='.repeat(80));
  console.log(`📍 Server: http://localhost:${PORT}`);
  console.log();
  console.log('Features:');
  console.log('  ✅ Widget-based animal selection (buttons)');
  console.log('  ✅ Progressive verification after EACH field');
  console.log('  ✅ Multi-select symptoms');
  console.log('  ✅ Summary with Edit/Submit');
  console.log('  ✅ Hybrid mode (text + widgets)');
  console.log('  ✅ No infinite loops');
  console.log();
  console.log('Test:');
  console.log(`  curl http://localhost:${PORT}/health`);
  console.log(`  curl http://localhost:${PORT}/farmers/demo-farmer/animals`);
  console.log();
  console.log('To use with flokiquser:');
  console.log('  1. Start this server: node server-widget-backend.js');
  console.log('  2. Update .env: VITE_ASSISTANT_API_BASE=http://localhost:8079');
  console.log('  3. Start flokiquser: npm run dev');
  console.log('  4. Click Chocolate → Book Appointment');
  console.log('='.repeat(80));
});
