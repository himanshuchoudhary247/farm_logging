/**
 * Appointments Skill - Tool Implementations
 */

import type { ToolImplementation, ToolExecutionResult } from '../../core/types';

// Mock appointment data
interface Appointment {
  id: string;
  farmer_id: string;
  type: 'veterinary' | 'agricultural' | 'consultation';
  date: string;
  time: string;
  status: 'pending' | 'confirmed' | 'completed' | 'cancelled';
  reason?: string;
  animal_id?: string;
}

const mockAppointments: Appointment[] = [
  {
    id: 'apt_001',
    farmer_id: 'farmer_001',
    type: 'veterinary',
    date: '2026-09-20',
    time: '10:00',
    status: 'confirmed',
    reason: 'Cow vaccination',
    animal_id: 'animal_001',
  },
  {
    id: 'apt_002',
    farmer_id: 'farmer_001',
    type: 'agricultural',
    date: '2026-09-22',
    time: '14:00',
    status: 'pending',
    reason: 'Crop consultation',
  },
];

export const get_appointments: ToolImplementation = {
  schema: {
    name: 'get_appointments',
    description: 'Get upcoming appointments for a farmer',
    parameters: {
      type: 'object',
      properties: {
        farmer_id: {
          type: 'string',
          description: 'Farmer ID',
        },
        status: {
          type: 'string',
          enum: ['pending', 'confirmed', 'completed', 'cancelled', 'all'],
          default: 'all',
        },
        limit: {
          type: 'number',
          default: 10,
        },
      },
      required: ['farmer_id'],
    },
    returns: {
      type: 'object',
      properties: {
        appointments: { type: 'array' },
        count: { type: 'number' },
      },
    },
  },
  handler: async (params): Promise<ToolExecutionResult> => {
    const { farmer_id, status = 'all', limit = 10 } = params as { 
      farmer_id: string; 
      status?: string; 
      limit?: number;
    };
    
    try {
      let appointments = mockAppointments.filter(apt => apt.farmer_id === farmer_id);
      
      if (status !== 'all') {
        appointments = appointments.filter(apt => apt.status === status);
      }
      
      // Sort by date
      appointments.sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());
      
      // Apply limit
      appointments = appointments.slice(0, limit);

      return {
        success: true,
        data: {
          appointments: appointments.map(apt => ({
            id: apt.id,
            type: apt.type,
            date: apt.date,
            time: apt.time,
            status: apt.status,
            reason: apt.reason,
            animal_id: apt.animal_id,
          })),
          count: appointments.length,
        },
      };
    } catch (error) {
      return {
        success: false,
        error: `Failed to get appointments: ${error instanceof Error ? error.message : 'Unknown error'}`,
      };
    }
  },
};

export const book_appointment: ToolImplementation = {
  schema: {
    name: 'book_appointment',
    description: 'Book a new appointment',
    parameters: {
      type: 'object',
      properties: {
        farmer_id: { type: 'string' },
        type: { type: 'string', enum: ['veterinary', 'agricultural', 'consultation'] },
        date: { type: 'string', description: 'Date in YYYY-MM-DD format' },
        time: { type: 'string', description: 'Time in HH:MM format' },
        reason: { type: 'string' },
        animal_id: { type: 'string', description: 'Optional: ID of animal' },
      },
      required: ['farmer_id', 'type', 'date', 'time'],
    },
    returns: {
      type: 'object',
      properties: {
        appointment_id: { type: 'string' },
        status: { type: 'string' },
        message: { type: 'string' },
      },
    },
  },
  handler: async (params): Promise<ToolExecutionResult> => {
    const { farmer_id, type, date, time, reason, animal_id } = params as {
      farmer_id: string;
      type: 'veterinary' | 'agricultural' | 'consultation';
      date: string;
      time: string;
      reason?: string;
      animal_id?: string;
    };
    
    try {
      // Check if slot is available (mock logic)
      const existing = mockAppointments.find(
        apt => apt.date === date && apt.time === time && apt.status !== 'cancelled'
      );
      
      if (existing) {
        return {
          success: false,
          error: 'This slot is already booked. Please choose another time.',
        };
      }

      const newAppointment: Appointment = {
        id: `apt_${Date.now()}`,
        farmer_id,
        type,
        date,
        time,
        status: 'confirmed',
        reason,
        animal_id,
      };

      mockAppointments.push(newAppointment);

      return {
        success: true,
        data: {
          appointment_id: newAppointment.id,
          status: 'confirmed',
          message: `Appointment booked successfully for ${date} at ${time}.`,
        },
      };
    } catch (error) {
      return {
        success: false,
        error: `Failed to book appointment: ${error instanceof Error ? error.message : 'Unknown error'}`,
      };
    }
  },
};

export const cancel_appointment: ToolImplementation = {
  schema: {
    name: 'cancel_appointment',
    description: 'Cancel an existing appointment',
    parameters: {
      type: 'object',
      properties: {
        appointment_id: { type: 'string' },
        reason: { type: 'string' },
      },
      required: ['appointment_id'],
    },
    returns: {
      type: 'object',
      properties: {
        success: { type: 'boolean' },
        message: { type: 'string' },
      },
    },
  },
  handler: async (params): Promise<ToolExecutionResult> => {
    const { appointment_id, reason } = params as { appointment_id: string; reason?: string };
    
    try {
      const appointment = mockAppointments.find(apt => apt.id === appointment_id);
      
      if (!appointment) {
        return {
          success: false,
          error: 'Appointment not found.',
        };
      }

      if (appointment.status === 'cancelled') {
        return {
          success: false,
          error: 'Appointment is already cancelled.',
        };
      }

      appointment.status = 'cancelled';

      return {
        success: true,
        data: {
          success: true,
          message: `Appointment cancelled successfully.${reason ? ` Reason: ${reason}` : ''}`,
        },
      };
    } catch (error) {
      return {
        success: false,
        error: `Failed to cancel appointment: ${error instanceof Error ? error.message : 'Unknown error'}`,
      };
    }
  },
};

export const check_availability: ToolImplementation = {
  schema: {
    name: 'check_availability',
    description: 'Check available appointment slots',
    parameters: {
      type: 'object',
      properties: {
        type: { type: 'string', enum: ['veterinary', 'agricultural', 'consultation'] },
        date: { type: 'string', description: 'Date in YYYY-MM-DD format' },
        start_time: { type: 'string', description: 'Start time in HH:MM format' },
        end_time: { type: 'string', description: 'End time in HH:MM format' },
      },
      required: ['type', 'date'],
    },
    returns: {
      type: 'object',
      properties: {
        available_slots: { type: 'array' },
        date: { type: 'string' },
      },
    },
  },
  handler: async (params): Promise<ToolExecutionResult> => {
    const { type, date, start_time, end_time } = params as {
      type: string;
      date: string;
      start_time?: string;
      end_time?: string;
    };
    
    try {
      // Generate available slots
      const slots: string[] = [];
      const startHour = start_time ? parseInt(start_time.split(':')[0]) : 9;
      const endHour = end_time ? parseInt(end_time.split(':')[0]) : 17;
      
      for (let hour = startHour; hour < endHour; hour++) {
        for (let minute of ['00', '15', '30', '45']) {
          const slotTime = `${hour.toString().padStart(2, '0')}:${minute}`;
          
          // Check if slot is taken
          const taken = mockAppointments.some(
            apt => apt.date === date && apt.time === slotTime && apt.status !== 'cancelled'
          );
          
          if (!taken) {
            slots.push(slotTime);
          }
        }
      }

      return {
        success: true,
        data: {
          available_slots: slots,
          date,
        },
      };
    } catch (error) {
      return {
        success: false,
        error: `Failed to check availability: ${error instanceof Error ? error.message : 'Unknown error'}`,
      };
    }
  },
};

// Export all tools
export default {
  get_appointments,
  book_appointment,
  cancel_appointment,
  check_availability,
};
