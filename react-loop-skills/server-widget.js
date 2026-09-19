#!/usr/bin/env node
/**
 * Widget-Based Appointment Booking Server
 * Demonstrates button-based selection and progressive verification
 */

const express = require('express');
const cors = require('cors');

const app = express();
const PORT = process.env.PORT || 3003;

app.use(cors());
app.use(express.json());

// Mock database with animals
const db = {
  farmers: [{ id: 'farmer_001', name: 'Rajesh Kumar' }],
  animals: [
    { id: 'animal_001', farmer_id: 'farmer_001', tag: 'COW001', name: 'Gauri', type: 'cow', emoji: '🐄' },
    { id: 'animal_002', farmer_id: 'farmer_001', tag: 'BUF001', name: 'Lakshmi', type: 'buffalo', emoji: '🐃' },
    { id: 'animal_003', farmer_id: 'farmer_001', tag: 'GOAT001', name: 'Moti', type: 'goat', emoji: '🐐' },
  ],
  commonIssues: [
    { id: 'not_eating', label: 'Not Eating', emoji: '🍽️' },
    { id: 'fever', label: 'Fever', emoji: '🌡️' },
    { id: 'cough', label: 'Cough', emoji: '😷' },
    { id: 'limping', label: 'Limping', emoji: '🦵' },
    { id: 'injury', label: 'Injury', emoji: '🩹' },
  ],
  symptoms: [
    { id: 'loss_appetite', label: 'Loss of appetite' },
    { id: 'lethargy', label: 'Lethargy (low energy)' },
    { id: 'fever', label: 'Fever' },
    { id: 'diarrhea', label: 'Diarrhea' },
    { id: 'vomiting', label: 'Vomiting' },
  ],
  sessions: new Map(),
};

// Health check
app.get('/health', (req, res) => {
  res.json({ status: 'ok', service: 'widget-appointment-server', timestamp: new Date().toISOString() });
});

// Get animals for widget
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

// Create session
app.post('/farmers/:farmerId/chat/session', (req, res) => {
  const sessionId = `sess_${Date.now()}`;
  db.sessions.set(sessionId, {
    id: sessionId,
    farmer_id: req.params.farmerId,
    step: 'animal', // animal, verify_animal, issue, symptoms, date, time, confirm
    collected: {},
    tempInput: null,
  });
  res.json({ session: { id: sessionId } });
});

// Fuzzy search animals
function searchAnimals(query, farmerId) {
  const animals = db.animals.filter(a => a.farmer_id === farmerId);
  const lower = query.toLowerCase();
  
  // Exact matches
  const exact = animals.filter(a => 
    a.tag.toLowerCase() === lower || 
    a.name.toLowerCase() === lower
  );
  
  // Partial matches
  const partial = animals.filter(a => 
    a.tag.toLowerCase().includes(lower) || 
    a.name.toLowerCase().includes(lower)
  ).filter(a => !exact.includes(a));
  
  // Return top 3
  return [...exact, ...partial].slice(0, 3);
}

// MAIN WIDGET CHAT ENDPOINT
app.post('/farmers/:farmerId/chat/turn', async (req, res) => {
  try {
    const { farmerId } = req.params;
    const { session_id, text, widget_action } = req.body;
    
    let session = db.sessions.get(session_id);
    if (!session) {
      session = { id: session_id, farmer_id: farmerId, step: 'animal', collected: {} };
      db.sessions.set(session_id, session);
    }
    
    let response = {};
    
    // Step 1: Animal Selection
    if (session.step === 'animal') {
      // Show animal widget
      const animals = db.animals.filter(a => a.farmer_id === farmerId);
      
      response = {
        agent: 'appointment_booking',
        reply_type: 'widget',
        reply_text: 'Select your animal:',
        widget: {
          type: 'single_select',
          title: 'Select Animal',
          subtitle: 'Choose from your animals or search',
          options: [
            ...animals.map(a => ({
              id: a.id,
              label: `${a.emoji} ${a.name}`,
              sublabel: `Tag: ${a.tag}`,
              value: a.id,
              type: 'button',
              action: 'select_animal'
            })),
            {
              id: 'search',
              label: '🔍 Search by tag',
              value: 'search',
              type: 'action',
              action: 'show_search'
            },
            {
              id: 'other',
              label: '✏️ Other (type tag)',
              value: 'other',
              type: 'text_input',
              placeholder: 'Type animal tag (e.g., COW001, 1122)',
              action: 'type_other'
            }
          ]
        },
        _meta: {
          step: 'animal',
          collected: session.collected
        }
      };
      
      // If user selected from widget
      if (widget_action === 'select_animal' && text) {
        const animal = db.animals.find(a => a.id === text);
        if (animal) {
          session.collected.animal = animal;
          session.step = 'verify_animal';
          
          response = {
            agent: 'appointment_booking',
            reply_type: 'widget',
            reply_text: `✓ Selected: ${animal.emoji} ${animal.name} (${animal.tag})`,
            widget: {
              type: 'confirmation',
              title: 'Confirm Animal',
              message: `Is ${animal.name} the correct animal?`,
              options: [
                { id: 'yes', label: '✓ Yes, correct', value: 'yes', type: 'button', action: 'confirm' },
                { id: 'no', label: '✗ No, change', value: 'no', type: 'button', action: 'change' }
              ]
            },
            _meta: {
              step: 'verify_animal',
              collected: session.collected
            }
          };
        }
      }
      
      // If user typed in "Other"
      if (widget_action === 'type_other' && text) {
        session.tempInput = text;
        const matches = searchAnimals(text, farmerId);
        
        if (matches.length > 0) {
          response = {
            agent: 'appointment_booking',
            reply_type: 'widget',
            reply_text: `Did you mean one of these animals matching "${text}"?`,
            widget: {
              type: 'single_select',
              title: 'Select Matching Animal',
              options: [
                ...matches.map(a => ({
                  id: a.id,
                  label: `${a.emoji} ${a.name}`,
                  sublabel: `Tag: ${a.tag}`,
                  value: a.id,
                  type: 'button',
                  action: 'select_animal'
                })),
                {
                  id: 'retry',
                  label: '✏️ None of these, try again',
                  value: 'retry',
                  type: 'text_input',
                  placeholder: 'Type different tag',
                  action: 'type_other'
                }
              ]
            },
            _meta: {
              step: 'animal',
              collected: session.collected
            }
          };
        } else {
          // No matches, ask to confirm anyway
          response = {
            agent: 'appointment_booking',
            reply_type: 'widget',
            reply_text: `No animals found matching "${text}". Create new?`,
            widget: {
              type: 'confirmation',
              options: [
                { id: 'create', label: '✓ Create new animal', value: text, type: 'button' },
                { id: 'retry', label: '✏️ Try different tag', value: 'retry', type: 'text_input' }
              ]
            },
            _meta: {
              step: 'animal',
              collected: session.collected
            }
          };
        }
      }
    }
    
    // Step 2: Verify Animal
    else if (session.step === 'verify_animal') {
      if (widget_action === 'confirm' || text === 'yes') {
        session.step = 'issue';
        
        response = {
          agent: 'appointment_booking',
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
                placeholder: 'Describe the issue',
                action: 'type_issue'
              }
            ]
          },
          _meta: {
            step: 'issue',
            collected: session.collected
          }
        };
      } else if (widget_action === 'change' || text === 'no') {
        // Go back to animal selection
        session.step = 'animal';
        response = {
          agent: 'appointment_booking',
          reply_type: 'widget',
          reply_text: 'Let\'s select the animal again.',
          widget: {
            type: 'info',
            auto_redirect: 'animal'
          },
          _meta: {
            step: 'animal',
            collected: session.collected
          }
        };
      }
    }
    
    // Step 3: Issue Selection
    else if (session.step === 'issue') {
      if (widget_action === 'select_issue' && text) {
        const issue = db.commonIssues.find(i => i.id === text);
        if (issue) {
          session.collected.issue = issue;
          session.step = 'verify_issue';
          
          response = {
            agent: 'appointment_booking',
            reply_type: 'widget',
            reply_text: `✓ Issue: ${issue.emoji} ${issue.label}`,
            widget: {
              type: 'confirmation',
              title: 'Confirm Issue',
              message: `Is "${issue.label}" the correct issue?`,
              options: [
                { id: 'yes', label: '✓ Yes, correct', value: 'yes', type: 'button' },
                { id: 'no', label: '✗ No, change', value: 'no', type: 'button' }
              ]
            },
            _meta: {
              step: 'verify_issue',
              collected: session.collected
            }
          };
        }
      } else if (widget_action === 'type_issue' && text) {
        session.collected.issue = { id: 'custom', label: text, emoji: '📝' };
        session.step = 'verify_issue';
        
        response = {
          agent: 'appointment_booking',
          reply_type: 'widget',
          reply_text: `✓ Issue: ${text}`,
          widget: {
            type: 'confirmation',
            title: 'Confirm Issue',
            message: `Is "${text}" the correct issue?`,
            options: [
              { id: 'yes', label: '✓ Yes, correct', value: 'yes', type: 'button' },
              { id: 'no', label: '✗ No, change', value: 'no', type: 'button' }
            ]
          },
          _meta: {
            step: 'verify_issue',
            collected: session.collected
          }
        };
      }
    }
    
    // Step 4: Verify Issue
    else if (session.step === 'verify_issue') {
      if (widget_action === 'confirm' || text === 'yes') {
        session.step = 'symptoms';
        
        response = {
          agent: 'appointment_booking',
          reply_type: 'widget',
          reply_text: 'What symptoms do you observe?',
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
            },
            other_option: {
              id: 'other_symptom',
              label: '✏️ Other symptom',
              type: 'text_input',
              placeholder: 'Describe other symptom'
            }
          },
          _meta: {
            step: 'symptoms',
            collected: session.collected
          }
        };
      } else {
        // Go back
        session.step = 'issue';
        response = {
          agent: 'appointment_booking',
          reply_type: 'widget',
          reply_text: 'Let\'s select the issue again.',
          widget: {
            type: 'info',
            auto_redirect: 'issue'
          },
          _meta: {
            step: 'issue',
            collected: session.collected
          }
        };
      }
    }
    
    // Step 5: Summary (simplified for demo)
    else if (session.step === 'symptoms') {
      // Collect symptoms and show summary
      if (widget_action === 'confirm_symptoms') {
        session.collected.symptoms = text ? text.split(',') : ['Not specified'];
        session.step = 'summary';
        
        const animal = session.collected.animal;
        const issue = session.collected.issue;
        
        response = {
          agent: 'appointment_booking',
          reply_type: 'widget',
          reply_text: 'Here\'s your appointment summary:',
          widget: {
            type: 'summary',
            title: '📋 Appointment Summary',
            fields: [
              { label: 'Animal', value: `${animal.emoji} ${animal.name} (${animal.tag})`, verified: true },
              { label: 'Issue', value: `${issue.emoji} ${issue.label}`, verified: true },
              { label: 'Symptoms', value: session.collected.symptoms.join(', '), verified: true },
            ],
            actions: [
              { id: 'edit', label: '✏️ Edit Details', value: 'edit', type: 'button' },
              { id: 'submit', label: '✅ Submit Appointment', value: 'submit', type: 'button', primary: true }
            ]
          },
          _meta: {
            step: 'summary',
            collected: session.collected
          }
        };
      }
    }
    
    // Step 6: Submit
    else if (session.step === 'summary') {
      if (widget_action === 'submit' || text === 'submit') {
        session.step = 'complete';
        session.submitted = true;
        
        response = {
          agent: 'appointment_booking',
          reply_type: 'widget',
          reply_text: '✅ Appointment saved successfully!',
          widget: {
            type: 'success',
            title: 'Appointment Confirmed',
            message: 'Your appointment has been scheduled.',
            appointment_id: `apt_${Date.now()}`,
            next_actions: [
              { id: 'new', label: '📝 Book Another', value: 'new', type: 'button' },
              { id: 'done', label: '👋 Done', value: 'done', type: 'button' }
            ]
          },
          _meta: {
            step: 'complete',
            submitted: true,
            appointment: session.collected
          }
        };
      }
    }
    
    // Complete - allow new booking
    else if (session.step === 'complete') {
      if (widget_action === 'new' || text === 'new') {
        // Reset for new booking
        session.step = 'animal';
        session.collected = {};
        session.submitted = false;
        
        response = {
          agent: 'appointment_booking',
          reply_type: 'widget',
          reply_text: 'Let\'s book a new appointment.',
          widget: {
            type: 'info',
            auto_redirect: 'animal'
          },
          _meta: {
            step: 'animal',
            collected: {}
          }
        };
      } else {
        response = {
          agent: 'appointment_booking',
          reply_text: 'Thank you! Type "new" to book another appointment.',
          _meta: {
            step: 'complete',
            submitted: true
          }
        };
      }
    }
    
    res.json(response);
    
  } catch (error) {
    console.error('[Error]', error);
    res.status(500).json({ error: error.message });
  }
});

app.listen(PORT, () => {
  console.log('='.repeat(80));
  console.log('🎉 Widget-Based Appointment Server');
  console.log('='.repeat(80));
  console.log(`📍 Server: http://localhost:${PORT}`);
  console.log();
  console.log('Features:');
  console.log('  ✅ Button-based animal selection');
  console.log('  ✅ Progressive verification after EACH field');
  console.log('  ✅ Fuzzy search with "Other" option');
  console.log('  ✅ Common issues as buttons');
  console.log('  ✅ Multi-select symptoms');
  console.log('  ✅ Summary with Edit/Submit');
  console.log('  ✅ No infinite loop after submit');
  console.log();
  console.log('Test:');
  console.log('  curl http://localhost:' + PORT + '/farmers/farmer_001/animals');
  console.log('='.repeat(80));
});
