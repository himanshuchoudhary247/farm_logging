/**
 * Farm Q&A Skill - Tool Implementations
 * Database access tools for answering questions about farm data
 */

import type { ToolImplementation, ToolExecutionResult } from '../../core/types';

// Mock database - in production, this would connect to real database
const mockDatabase = {
  farmers: [
    {
      id: 'farmer_001',
      name: 'Rajesh Kumar',
      phone: '9876543210',
      email: 'rajesh@example.com',
      address: 'Village Khera',
      village: 'Khera',
      district: 'Muzaffarnagar',
      state: 'Uttar Pradesh',
      registration_date: '2023-01-15',
    },
    {
      id: 'farmer_002',
      name: 'Amit Singh',
      phone: '9876543211',
      email: 'amit@example.com',
      address: 'Village Rampur',
      village: 'Rampur',
      district: 'Meerut',
      state: 'Uttar Pradesh',
      registration_date: '2023-03-20',
    },
  ],
  animals: [
    {
      id: 'animal_001',
      farmer_id: 'farmer_001',
      tag_number: 'COW001',
      name: 'Gauri',
      type: 'cow',
      breed: 'Sahiwal',
      date_of_birth: '2020-05-15',
      gender: 'female',
      color: 'brown',
      weight: 450,
      health_status: 'healthy',
      acquisition_date: '2021-06-20',
      purchase_price: 45000,
    },
    {
      id: 'animal_002',
      farmer_id: 'farmer_001',
      tag_number: 'BUF001',
      name: 'Lakshmi',
      type: 'buffalo',
      breed: 'Murrah',
      date_of_birth: '2019-08-10',
      gender: 'female',
      color: 'black',
      weight: 550,
      health_status: 'healthy',
      acquisition_date: '2020-09-15',
      purchase_price: 65000,
    },
    {
      id: 'animal_003',
      farmer_id: 'farmer_001',
      tag_number: 'GOAT001',
      name: 'Moti',
      type: 'goat',
      breed: 'Jamunapari',
      date_of_birth: '2022-02-20',
      gender: 'male',
      color: 'white',
      weight: 45,
      health_status: 'healthy',
      acquisition_date: '2022-05-10',
      purchase_price: 8000,
    },
  ],
  farms: [
    {
      id: 'farm_001',
      farmer_id: 'farmer_001',
      name: 'Khera Farm',
      total_area: 12.5,
      area_unit: 'acres',
      soil_type: 'loamy',
      irrigation_type: 'canal',
      address: 'Village Khera, Muzaffarnagar',
      coordinates: '29.4500,77.7000',
    },
  ],
  fields: [
    { id: 'field_001', farm_id: 'farm_001', name: 'Field A', area: 4.5, current_crop: 'wheat', soil_quality: 'good' },
    { id: 'field_002', farm_id: 'farm_001', name: 'Field B', area: 5.0, current_crop: 'rice', soil_quality: 'excellent' },
    { id: 'field_003', farm_id: 'farm_001', name: 'Field C', area: 3.0, current_crop: null, soil_quality: 'good' },
  ],
  crops: [
    {
      id: 'crop_001',
      farmer_id: 'farmer_001',
      name: 'Wheat',
      variety: 'HD-2967',
      field_id: 'field_001',
      area_acres: 4.5,
      planting_date: '2025-11-15',
      expected_harvest: '2026-04-20',
      status: 'growing',
      season: 'rabi',
      yield_expected: 18,
    },
    {
      id: 'crop_002',
      farmer_id: 'farmer_001',
      name: 'Rice',
      variety: 'Pusa Basmati',
      field_id: 'field_002',
      area_acres: 5.0,
      planting_date: '2026-06-20',
      expected_harvest: '2026-10-30',
      status: 'planted',
      season: 'kharif',
      yield_expected: 22,
    },
  ],
  health_records: [
    {
      id: 'health_001',
      animal_id: 'animal_001',
      farmer_id: 'farmer_001',
      date: '2026-09-10',
      type: 'checkup',
      symptoms: 'none',
      diagnosis: 'healthy',
      treatment: 'routine check',
      vet_name: 'Dr. Sharma',
      follow_up_required: false,
    },
    {
      id: 'health_002',
      animal_id: 'animal_002',
      farmer_id: 'farmer_001',
      date: '2026-09-05',
      type: 'treatment',
      symptoms: 'fever, reduced appetite',
      diagnosis: 'mild infection',
      treatment: 'antibiotics for 5 days',
      vet_name: 'Dr. Verma',
      follow_up_required: true,
    },
  ],
  production: [
    { id: 'prod_001', animal_id: 'animal_001', date: '2026-09-19', quantity: 12.5, unit: 'liters', quality: 'A' },
    { id: 'prod_002', animal_id: 'animal_001', date: '2026-09-18', quantity: 13.0, unit: 'liters', quality: 'A' },
    { id: 'prod_003', animal_id: 'animal_001', date: '2026-09-17', quantity: 12.8, unit: 'liters', quality: 'A' },
    { id: 'prod_004', animal_id: 'animal_002', date: '2026-09-19', quantity: 8.5, unit: 'liters', quality: 'A' },
    { id: 'prod_005', animal_id: 'animal_002', date: '2026-09-18', quantity: 9.0, unit: 'liters', quality: 'A' },
  ],
  vaccinations: [
    {
      id: 'vac_001',
      animal_id: 'animal_001',
      farmer_id: 'farmer_001',
      vaccine_name: 'FMD Vaccine',
      scheduled_date: '2026-10-15',
      completed_date: null,
      status: 'scheduled',
      next_due: '2027-10-15',
      vet_name: 'Dr. Sharma',
    },
    {
      id: 'vac_002',
      animal_id: 'animal_002',
      farmer_id: 'farmer_001',
      vaccine_name: 'FMD Vaccine',
      scheduled_date: '2026-10-15',
      completed_date: '2026-09-01',
      status: 'completed',
      next_due: '2027-10-15',
      vet_name: 'Dr. Sharma',
    },
  ],
};

// Helper function to calculate age from date
function calculateAge(dateOfBirth: string): number {
  const birth = new Date(dateOfBirth);
  const now = new Date();
  return Math.floor((now.getTime() - birth.getTime()) / (365.25 * 24 * 60 * 60 * 1000));
}

export const query_farmer_profile: ToolImplementation = {
  schema: {
    name: 'query_farmer_profile',
    description: 'Get farmer profile information including personal details, contact info, and farm summary',
    parameters: {
      type: 'object',
      properties: {
        farmer_id: { type: 'string', description: 'Farmer ID or phone number' },
        include_farm_summary: { type: 'boolean', default: true },
      },
      required: ['farmer_id'],
    },
    returns: {
      type: 'object',
      properties: {
        farmer: { type: 'object' },
        farm_summary: { type: 'object' },
      },
    },
  },
  handler: async (params): Promise<ToolExecutionResult> => {
    const { farmer_id, include_farm_summary = true } = params as { farmer_id: string; include_farm_summary?: boolean };
    
    try {
      const farmer = mockDatabase.farmers.find(f => f.id === farmer_id || f.phone === farmer_id);
      
      if (!farmer) {
        return { success: false, error: 'Farmer not found' };
      }

      let farm_summary = undefined;
      
      if (include_farm_summary) {
        const farm = mockDatabase.farms.find(f => f.farmer_id === farmer.id);
        const animals = mockDatabase.animals.filter(a => a.farmer_id === farmer.id);
        const crops = mockDatabase.crops.filter(c => c.farmer_id === farmer.id && c.status === 'growing');
        
        farm_summary = {
          total_animals: animals.length,
          total_land_area: farm?.total_area || 0,
          active_crops: crops.length,
          last_visit: '2026-09-15',
        };
      }

      return {
        success: true,
        data: { farmer, farm_summary },
      };
    } catch (error) {
      return { success: false, error: String(error) };
    }
  },
};

export const query_animals: ToolImplementation = {
  schema: {
    name: 'query_animals',
    description: 'Query animals belonging to a farmer with optional filters',
    parameters: {
      type: 'object',
      properties: {
        farmer_id: { type: 'string' },
        animal_type: { type: 'string', enum: ['cow', 'buffalo', 'goat', 'sheep', 'chicken', 'bull', 'all'], default: 'all' },
        status: { type: 'string', enum: ['active', 'sold', 'deceased', 'all'], default: 'active' },
        limit: { type: 'number', default: 20 },
      },
      required: ['farmer_id'],
    },
    returns: { type: 'object', properties: { animals: { type: 'array' }, count: { type: 'number' }, by_type: { type: 'object' } } },
  },
  handler: async (params): Promise<ToolExecutionResult> => {
    const { farmer_id, animal_type = 'all', status = 'active', limit = 20 } = params;
    
    try {
      let animals = mockDatabase.animals.filter(a => a.farmer_id === farmer_id);
      
      if (animal_type !== 'all') {
        animals = animals.filter(a => a.type === animal_type);
      }
      
      animals = animals.slice(0, limit).map(a => ({
        ...a,
        age: calculateAge(a.date_of_birth),
      }));

      const by_type = animals.reduce((acc, a) => {
        acc[a.type] = (acc[a.type] || 0) + 1;
        return acc;
      }, {} as Record<string, number>);

      return {
        success: true,
        data: { animals, count: animals.length, by_type },
      };
    } catch (error) {
      return { success: false, error: String(error) };
    }
  },
};

export const query_animal_details: ToolImplementation = {
  schema: {
    name: 'query_animal_details',
    description: 'Get detailed information about a specific animal',
    parameters: {
      type: 'object',
      properties: {
        animal_id: { type: 'string' },
        include_health: { type: 'boolean', default: true },
        include_production: { type: 'boolean', default: true },
        include_vaccinations: { type: 'boolean', default: true },
      },
      required: ['animal_id'],
    },
    returns: { type: 'object', properties: { animal: { type: 'object' }, health_records: { type: 'array' }, production_data: { type: 'object' }, vaccination_history: { type: 'array' } } },
  },
  handler: async (params): Promise<ToolExecutionResult> => {
    const { animal_id, include_health = true, include_production = true, include_vaccinations = true } = params;
    
    try {
      const animal = mockDatabase.animals.find(a => a.id === animal_id || a.tag_number === animal_id);
      
      if (!animal) {
        return { success: false, error: 'Animal not found' };
      }

      const result: Record<string, unknown> = {
        animal: { ...animal, age: calculateAge(animal.date_of_birth) },
      };

      if (include_health) {
        result.health_records = mockDatabase.health_records.filter(h => h.animal_id === animal.id);
      }

      if (include_production) {
        const production = mockDatabase.production.filter(p => p.animal_id === animal.id);
        const avgProduction = production.reduce((sum, p) => sum + p.quantity, 0) / production.length;
        result.production_data = { records: production, average: avgProduction.toFixed(2), total_records: production.length };
      }

      if (include_vaccinations) {
        result.vaccination_history = mockDatabase.vaccinations.filter(v => v.animal_id === animal.id);
      }

      return { success: true, data: result };
    } catch (error) {
      return { success: false, error: String(error) };
    }
  },
};

export const query_crops: ToolImplementation = {
  schema: {
    name: 'query_crops',
    description: 'Query crops planted on the farm',
    parameters: {
      type: 'object',
      properties: {
        farmer_id: { type: 'string' },
        season: { type: 'string', enum: ['kharif', 'rabi', 'summer', 'all'], default: 'all' },
        status: { type: 'string', enum: ['planted', 'growing', 'harvested', 'all'], default: 'all' },
        year: { type: 'number' },
      },
      required: ['farmer_id'],
    },
    returns: { type: 'object', properties: { crops: { type: 'array' }, total_area: { type: 'number' }, crop_count: { type: 'number' } } },
  },
  handler: async (params): Promise<ToolExecutionResult> => {
    const { farmer_id, season = 'all', status = 'all', year } = params;
    
    try {
      let crops = mockDatabase.crops.filter(c => c.farmer_id === farmer_id);
      
      if (season !== 'all') {
        crops = crops.filter(c => c.season === season);
      }
      if (status !== 'all') {
        crops = crops.filter(c => c.status === status);
      }
      if (year) {
        crops = crops.filter(c => new Date(c.planting_date).getFullYear() === year);
      }

      const total_area = crops.reduce((sum, c) => sum + c.area_acres, 0);

      return {
        success: true,
        data: { crops, total_area, crop_count: crops.length },
      };
    } catch (error) {
      return { success: false, error: String(error) };
    }
  },
};

export const query_farm_land: ToolImplementation = {
  schema: {
    name: 'query_farm_land',
    description: 'Get information about farm land and fields',
    parameters: {
      type: 'object',
      properties: {
        farmer_id: { type: 'string' },
        include_fields: { type: 'boolean', default: true },
      },
      required: ['farmer_id'],
    },
    returns: { type: 'object', properties: { farm: { type: 'object' }, fields: { type: 'array' } } },
  },
  handler: async (params): Promise<ToolExecutionResult> => {
    const { farmer_id, include_fields = true } = params;
    
    try {
      const farm = mockDatabase.farms.find(f => f.farmer_id === farmer_id);
      
      if (!farm) {
        return { success: false, error: 'Farm not found' };
      }

      const result: Record<string, unknown> = { farm };

      if (include_fields) {
        result.fields = mockDatabase.fields.filter(field => field.farm_id === farm.id);
      }

      return { success: true, data: result };
    } catch (error) {
      return { success: false, error: String(error) };
    }
  },
};

export const query_health_records: ToolImplementation = {
  schema: {
    name: 'query_health_records',
    description: 'Query health records for animals',
    parameters: {
      type: 'object',
      properties: {
        animal_id: { type: 'string' },
        farmer_id: { type: 'string' },
        from_date: { type: 'string' },
        to_date: { type: 'string' },
        record_type: { type: 'string', enum: ['checkup', 'treatment', 'disease', 'all'], default: 'all' },
        limit: { type: 'number', default: 10 },
      },
      required: ['farmer_id'],
    },
    returns: { type: 'object', properties: { records: { type: 'array' }, count: { type: 'number' }, pending_followups: { type: 'number' } } },
  },
  handler: async (params): Promise<ToolExecutionResult> => {
    const { animal_id, farmer_id, from_date, to_date, record_type = 'all', limit = 10 } = params;
    
    try {
      let records = mockDatabase.health_records.filter(h => h.farmer_id === farmer_id);
      
      if (animal_id) {
        records = records.filter(h => h.animal_id === animal_id);
      }
      if (from_date) {
        records = records.filter(h => h.date >= from_date);
      }
      if (to_date) {
        records = records.filter(h => h.date <= to_date);
      }
      if (record_type !== 'all') {
        records = records.filter(h => h.type === record_type);
      }

      records = records.slice(0, limit).map(r => ({
        ...r,
        animal_name: mockDatabase.animals.find(a => a.id === r.animal_id)?.name || 'Unknown',
      }));

      const pending_followups = records.filter(r => r.follow_up_required).length;

      return {
        success: true,
        data: { records, count: records.length, pending_followups },
      };
    } catch (error) {
      return { success: false, error: String(error) };
    }
  },
};

export const query_production_data: ToolImplementation = {
  schema: {
    name: 'query_production_data',
    description: 'Query milk production or other production data',
    parameters: {
      type: 'object',
      properties: {
        animal_id: { type: 'string' },
        farmer_id: { type: 'string' },
        from_date: { type: 'string' },
        to_date: { type: 'string' },
        group_by: { type: 'string', enum: ['day', 'week', 'month', 'animal'], default: 'day' },
      },
      required: ['farmer_id', 'from_date', 'to_date'],
    },
    returns: { type: 'object', properties: { summary: { type: 'object' }, records: { type: 'array' } } },
  },
  handler: async (params): Promise<ToolExecutionResult> => {
    const { animal_id, farmer_id, from_date, to_date, group_by = 'day' } = params;
    
    try {
      let records = mockDatabase.production.filter(p => {
        const animal = mockDatabase.animals.find(a => a.id === p.animal_id);
        return animal?.farmer_id === farmer_id;
      });
      
      if (animal_id && animal_id !== 'all') {
        records = records.filter(p => p.animal_id === animal_id);
      }
      if (from_date) {
        records = records.filter(p => p.date >= from_date);
      }
      if (to_date) {
        records = records.filter(p => p.date <= to_date);
      }

      const total_quantity = records.reduce((sum, p) => sum + p.quantity, 0);
      const average_daily = records.length > 0 ? total_quantity / records.length : 0;

      // Find best animal
      const byAnimal: Record<string, number[]> = {};
      records.forEach(p => {
        if (!byAnimal[p.animal_id]) byAnimal[p.animal_id] = [];
        byAnimal[p.animal_id].push(p.quantity);
      });

      let bestAnimal = '';
      let bestAvg = 0;
      for (const [aid, quantities] of Object.entries(byAnimal)) {
        const avg = quantities.reduce((a, b) => a + b, 0) / quantities.length;
        if (avg > bestAvg) {
          bestAvg = avg;
          bestAnimal = aid;
        }
      }

      const bestAnimalName = bestAnimal ? mockDatabase.animals.find(a => a.id === bestAnimal)?.name || bestAnimal : '';

      return {
        success: true,
        data: {
          summary: {
            total_quantity,
            average_daily: average_daily.toFixed(2),
            unit: 'liters',
            best_animal: bestAnimalName,
            best_animal_avg: bestAvg.toFixed(2),
          },
          records,
        },
      };
    } catch (error) {
      return { success: false, error: String(error) };
    }
  },
};

export const query_vaccination_schedule: ToolImplementation = {
  schema: {
    name: 'query_vaccination_schedule',
    description: 'Get vaccination schedule and history for animals',
    parameters: {
      type: 'object',
      properties: {
        animal_id: { type: 'string' },
        farmer_id: { type: 'string' },
        upcoming_only: { type: 'boolean', default: false },
        days_ahead: { type: 'number', default: 30 },
      },
    },
    returns: { type: 'object', properties: { vaccinations: { type: 'array' }, upcoming_count: { type: 'number' }, overdue_count: { type: 'number' } } },
  },
  handler: async (params): Promise<ToolExecutionResult> => {
    const { animal_id, farmer_id, upcoming_only = false, days_ahead = 30 } = params;
    
    try {
      let vaccinations = mockDatabase.vaccinations.filter(v => {
        const animal = mockDatabase.animals.find(a => a.id === v.animal_id);
        return animal?.farmer_id === farmer_id;
      });
      
      if (animal_id) {
        vaccinations = vaccinations.filter(v => v.animal_id === animal_id);
      }

      const today = new Date().toISOString().split('T')[0];
      const futureDate = new Date();
      futureDate.setDate(futureDate.getDate() + days_ahead);
      const futureStr = futureDate.toISOString().split('T')[0];

      vaccinations = vaccinations.map(v => ({
        ...v,
        animal_name: mockDatabase.animals.find(a => a.id === v.animal_id)?.name || 'Unknown',
      }));

      if (upcoming_only) {
        vaccinations = vaccinations.filter(v => v.scheduled_date >= today && v.scheduled_date <= futureStr);
      }

      const upcoming_count = vaccinations.filter(v => v.scheduled_date >= today && v.status === 'scheduled').length;
      const overdue_count = vaccinations.filter(v => v.scheduled_date < today && v.status === 'scheduled').length;

      return {
        success: true,
        data: { vaccinations, upcoming_count, overdue_count },
      };
    } catch (error) {
      return { success: false, error: String(error) };
    }
  },
};

export const ask_database: ToolImplementation = {
  schema: {
    name: 'ask_database',
    description: 'Ask a natural language question that gets translated to a database query',
    parameters: {
      type: 'object',
      properties: {
        question: { type: 'string' },
        farmer_id: { type: 'string' },
        context: { type: 'string' },
      },
      required: ['question', 'farmer_id'],
    },
    returns: { type: 'object', properties: { question: { type: 'string' }, sql_query: { type: 'string' }, answer: { type: 'string' }, data: { type: 'object' }, confidence: { type: 'number' } } },
  },
  handler: async (params): Promise<ToolExecutionResult> => {
    const { question, farmer_id, context } = params as { question: string; farmer_id: string; context?: string };
    
    try {
      // Simple pattern matching for common questions
      const q = question.toLowerCase();
      let sql_query = '';
      let answer = '';
      let data: Record<string, unknown> = {};

      if (q.includes('how many animals') || q.includes('total animals')) {
        const animals = mockDatabase.animals.filter(a => a.farmer_id === farmer_id);
        sql_query = `SELECT COUNT(*) FROM animals WHERE farmer_id = '${farmer_id}'`;
        answer = `You have ${animals.length} animals in total.`;
        data = { count: animals.length, by_type: animals.reduce((acc, a) => { acc[a.type] = (acc[a.type] || 0) + 1; return acc; }, {} as Record<string, number>) };
      } else if (q.includes('cows') || q.includes('cow')) {
        const cows = mockDatabase.animals.filter(a => a.farmer_id === farmer_id && a.type === 'cow');
        sql_query = `SELECT * FROM animals WHERE farmer_id = '${farmer_id}' AND type = 'cow'`;
        answer = `You have ${cows.length} cows.`;
        data = { cows };
      } else if (q.includes('milk') || q.includes('production')) {
        const records = mockDatabase.production.filter(p => {
          const animal = mockDatabase.animals.find(a => a.id === p.animal_id);
          return animal?.farmer_id === farmer_id;
        });
        const total = records.reduce((sum, p) => sum + p.quantity, 0);
        sql_query = `SELECT SUM(quantity) FROM production WHERE farmer_id = '${farmer_id}'`;
        answer = `Your total milk production is ${total.toFixed(1)} liters.`;
        data = { total_quantity: total, records_count: records.length };
      } else if (q.includes('vaccination') || q.includes('vaccine')) {
        const upcoming = mockDatabase.vaccinations.filter(v => {
          const animal = mockDatabase.animals.find(a => a.id === v.animal_id);
          return animal?.farmer_id === farmer_id && v.status === 'scheduled';
        }).length;
        sql_query = `SELECT * FROM vaccinations WHERE farmer_id = '${farmer_id}' AND status = 'scheduled'`;
        answer = `You have ${upcoming} upcoming vaccinations scheduled.`;
        data = { upcoming_count: upcoming };
      } else if (q.includes('health') || q.includes('sick')) {
        const pending = mockDatabase.health_records.filter(h => h.farmer_id === farmer_id && h.follow_up_required).length;
        sql_query = `SELECT * FROM health_records WHERE farmer_id = '${farmer_id}' AND follow_up_required = true`;
        answer = pending > 0 ? `You have ${pending} animals requiring follow-up health checks.` : 'All your animals are in good health!';
        data = { pending_followups: pending };
      } else {
        sql_query = '-- Complex query generated by LLM';
        answer = 'I found information about your farm. You can ask me about your animals, crops, production, or health records.';
        data = { message: 'Use specific tools for detailed information' };
      }

      return {
        success: true,
        data: { question, sql_query, answer, data, confidence: 0.85 },
      };
    } catch (error) {
      return { success: false, error: String(error) };
    }
  },
};

export const get_summary: ToolImplementation = {
  schema: {
    name: 'get_summary',
    description: 'Get a comprehensive summary of the farm',
    parameters: {
      type: 'object',
      properties: {
        farmer_id: { type: 'string' },
        include: { type: 'array', items: { type: 'string', enum: ['animals', 'crops', 'production', 'health', 'vaccinations'] }, default: ['animals', 'crops', 'production'] },
      },
      required: ['farmer_id'],
    },
    returns: { type: 'object', properties: { farmer_name: { type: 'string' }, generated_at: { type: 'string' }, summary: { type: 'object' }, sections: { type: 'object' } } },
  },
  handler: async (params): Promise<ToolExecutionResult> => {
    const { farmer_id, include = ['animals', 'crops', 'production'] } = params;
    
    try {
      const farmer = mockDatabase.farmers.find(f => f.id === farmer_id);
      
      if (!farmer) {
        return { success: false, error: 'Farmer not found' };
      }

      const summary: Record<string, number> = {};
      const sections: Record<string, unknown> = {};

      // Animals
      if (include.includes('animals')) {
        const animals = mockDatabase.animals.filter(a => a.farmer_id === farmer_id);
        summary.total_animals = animals.length;
        sections.animals = {
          count: animals.length,
          by_type: animals.reduce((acc, a) => { acc[a.type] = (acc[a.type] || 0) + 1; return acc; }, {} as Record<string, number>),
          healthy: animals.filter(a => a.health_status === 'healthy').length,
        };
      }

      // Crops
      if (include.includes('crops')) {
        const crops = mockDatabase.crops.filter(c => c.farmer_id === farmer_id);
        summary.active_crops = crops.filter(c => c.status === 'growing').length;
        sections.crops = {
          total: crops.length,
          active: crops.filter(c => c.status === 'growing').length,
          total_area: crops.reduce((sum, c) => sum + c.area_acres, 0),
          list: crops.map(c => c.name),
        };
      }

      // Production
      if (include.includes('production')) {
        const production = mockDatabase.production.filter(p => {
          const animal = mockDatabase.animals.find(a => a.id === p.animal_id);
          return animal?.farmer_id === farmer_id;
        });
        const monthly = production.reduce((sum, p) => sum + p.quantity, 0);
        summary.monthly_production = monthly;
        sections.production = {
          total_liters: monthly,
          milking_animals: mockDatabase.animals.filter(a => a.farmer_id === farmer_id && ['cow', 'buffalo'].includes(a.type)).length,
        };
      }

      // Health
      if (include.includes('health')) {
        const healthAlerts = mockDatabase.health_records.filter(h => h.farmer_id === farmer_id && h.follow_up_required).length;
        summary.health_alerts = healthAlerts;
        sections.health = {
          pending_checkups: healthAlerts,
          last_checkup: mockDatabase.health_records.filter(h => h.farmer_id === farmer_id).sort((a, b) => b.date.localeCompare(a.date))[0]?.date,
        };
      }

      // Vaccinations
      if (include.includes('vaccinations')) {
        const today = new Date().toISOString().split('T')[0];
        const upcoming = mockDatabase.vaccinations.filter(v => {
          const animal = mockDatabase.animals.find(a => a.id === v.animal_id);
          return animal?.farmer_id === farmer_id && v.scheduled_date >= today && v.status === 'scheduled';
        }).length;
        summary.upcoming_vaccinations = upcoming;
        sections.vaccinations = {
          upcoming,
          completed: mockDatabase.vaccinations.filter(v => {
            const animal = mockDatabase.animals.find(a => a.id === v.animal_id);
            return animal?.farmer_id === farmer_id && v.status === 'completed';
          }).length,
        };
      }

      return {
        success: true,
        data: {
          farmer_name: farmer.name,
          generated_at: new Date().toISOString(),
          summary,
          sections,
        },
      };
    } catch (error) {
      return { success: false, error: String(error) };
    }
  },
};

// Export all tools
export default {
  query_farmer_profile,
  query_animals,
  query_animal_details,
  query_crops,
  query_farm_land,
  query_health_records,
  query_production_data,
  query_vaccination_schedule,
  ask_database,
  get_summary,
};
