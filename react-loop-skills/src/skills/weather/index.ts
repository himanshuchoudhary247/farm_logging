/**
 * Weather Skill - Tool Implementations
 */

import type { ToolImplementation, ToolExecutionResult } from '../../core/types';

// Mock weather data - in production, this would call a real weather API
const mockWeatherData: Record<string, Record<string, unknown>> = {
  'delhi': {
    temperature: 32,
    conditions: 'Sunny',
    humidity: 45,
    wind_speed: 12,
    location: 'Delhi',
  },
  'mumbai': {
    temperature: 28,
    conditions: 'Partly Cloudy',
    humidity: 78,
    wind_speed: 15,
    location: 'Mumbai',
  },
  'bangalore': {
    temperature: 24,
    conditions: 'Cloudy',
    humidity: 65,
    wind_speed: 8,
    location: 'Bangalore',
  },
  'default': {
    temperature: 25,
    conditions: 'Clear',
    humidity: 50,
    wind_speed: 10,
    location: 'Unknown Location',
  },
};

export const get_current_weather: ToolImplementation = {
  schema: {
    name: 'get_current_weather',
    description: 'Get the current weather conditions for a location',
    parameters: {
      type: 'object',
      properties: {
        location: {
          type: 'string',
          description: 'City name, village name, or coordinates (lat,long)',
        },
        units: {
          type: 'string',
          enum: ['celsius', 'fahrenheit'],
          default: 'celsius',
        },
      },
      required: ['location'],
    },
    returns: {
      type: 'object',
      properties: {
        temperature: { type: 'number' },
        conditions: { type: 'string' },
        humidity: { type: 'number' },
        wind_speed: { type: 'number' },
        location: { type: 'string' },
        timestamp: { type: 'string' },
      },
    },
  },
  handler: async (params): Promise<ToolExecutionResult> => {
    const { location, units = 'celsius' } = params as { location: string; units?: string };
    
    try {
      // In production, call actual weather API
      // For now, use mock data
      const locationKey = location.toLowerCase();
      const data = mockWeatherData[locationKey] || mockWeatherData.default;
      
      // Convert temperature if needed
      let temperature = data.temperature as number;
      if (units === 'fahrenheit') {
        temperature = (temperature * 9 / 5) + 32;
      }

      return {
        success: true,
        data: {
          ...data,
          temperature: Math.round(temperature * 10) / 10,
          timestamp: new Date().toISOString(),
        },
      };
    } catch (error) {
      return {
        success: false,
        error: `Failed to fetch weather for ${location}: ${error instanceof Error ? error.message : 'Unknown error'}`,
      };
    }
  },
};

export const get_forecast: ToolImplementation = {
  schema: {
    name: 'get_forecast',
    description: 'Get weather forecast for the next few days',
    parameters: {
      type: 'object',
      properties: {
        location: {
          type: 'string',
          description: 'City name, village name, or coordinates',
        },
        days: {
          type: 'number',
          minimum: 1,
          maximum: 7,
          default: 3,
        },
        units: {
          type: 'string',
          enum: ['celsius', 'fahrenheit'],
          default: 'celsius',
        },
      },
      required: ['location'],
    },
    returns: {
      type: 'object',
      properties: {
        location: { type: 'string' },
        forecast: { type: 'array' },
      },
    },
  },
  handler: async (params): Promise<ToolExecutionResult> => {
    const { location, days = 3, units = 'celsius' } = params as { 
      location: string; 
      days?: number; 
      units?: string;
    };
    
    try {
      // Generate mock forecast
      const forecast = [];
      const baseTemp = 25 + Math.random() * 10;
      const conditions = ['Sunny', 'Partly Cloudy', 'Cloudy', 'Light Rain', 'Clear'];
      
      for (let i = 0; i < days; i++) {
        const date = new Date();
        date.setDate(date.getDate() + i);
        
        let tempHigh = baseTemp + Math.random() * 5;
        let tempLow = baseTemp - 5 - Math.random() * 5;
        
        if (units === 'fahrenheit') {
          tempHigh = (tempHigh * 9 / 5) + 32;
          tempLow = (tempLow * 9 / 5) + 32;
        }
        
        forecast.push({
          date: date.toISOString().split('T')[0],
          temperature_high: Math.round(tempHigh),
          temperature_low: Math.round(tempLow),
          conditions: conditions[Math.floor(Math.random() * conditions.length)],
          rain_chance: Math.floor(Math.random() * 40),
        });
      }

      return {
        success: true,
        data: {
          location,
          forecast,
        },
      };
    } catch (error) {
      return {
        success: false,
        error: `Failed to fetch forecast for ${location}: ${error instanceof Error ? error.message : 'Unknown error'}`,
      };
    }
  },
};

export const check_weather_alerts: ToolImplementation = {
  schema: {
    name: 'check_weather_alerts',
    description: 'Check for weather warnings and alerts in a location',
    parameters: {
      type: 'object',
      properties: {
        location: {
          type: 'string',
          description: 'City or region name',
        },
      },
      required: ['location'],
    },
    returns: {
      type: 'object',
      properties: {
        has_alerts: { type: 'boolean' },
        alerts: { type: 'array' },
      },
    },
  },
  handler: async (params): Promise<ToolExecutionResult> => {
    const { location } = params as { location: string };
    
    try {
      // Mock alerts - randomly show alerts
      const hasAlerts = Math.random() > 0.7;
      const alerts = hasAlerts ? [
        {
          severity: 'medium',
          title: 'Heat Advisory',
          description: `High temperatures expected in ${location} area. Stay hydrated and avoid prolonged sun exposure.`,
          valid_until: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(),
        },
      ] : [];

      return {
        success: true,
        data: {
          has_alerts: hasAlerts,
          alerts,
        },
      };
    } catch (error) {
      return {
        success: false,
        error: `Failed to check alerts for ${location}: ${error instanceof Error ? error.message : 'Unknown error'}`,
      };
    }
  },
};

// Export all tools
export default {
  get_current_weather,
  get_forecast,
  check_weather_alerts,
};
