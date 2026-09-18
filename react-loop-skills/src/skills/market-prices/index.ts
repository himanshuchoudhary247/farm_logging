/**
 * Market Prices Skill - Tool Implementations
 */

import type { ToolImplementation, ToolExecutionResult } from '../../core/types';

// Mock market price data
interface PriceData {
  commodity: string;
  market: string;
  min_price: number;
  max_price: number;
  modal_price: number;
  unit: string;
  date: string;
}

const mockPrices: Record<string, PriceData[]> = {
  'wheat': [
    { commodity: 'Wheat', market: 'Delhi', min_price: 2100, max_price: 2300, modal_price: 2200, unit: 'per quintal', date: '2026-09-19' },
    { commodity: 'Wheat', market: 'Mumbai', min_price: 2050, max_price: 2250, modal_price: 2150, unit: 'per quintal', date: '2026-09-19' },
    { commodity: 'Wheat', market: 'Bangalore', min_price: 2150, max_price: 2350, modal_price: 2250, unit: 'per quintal', date: '2026-09-19' },
  ],
  'rice': [
    { commodity: 'Rice', market: 'Delhi', min_price: 3500, max_price: 3800, modal_price: 3650, unit: 'per quintal', date: '2026-09-19' },
    { commodity: 'Rice', market: 'Mumbai', min_price: 3400, max_price: 3700, modal_price: 3550, unit: 'per quintal', date: '2026-09-19' },
    { commodity: 'Rice', market: 'Kolkata', min_price: 3300, max_price: 3600, modal_price: 3450, unit: 'per quintal', date: '2026-09-19' },
  ],
  'cotton': [
    { commodity: 'Cotton', market: 'Ahmedabad', min_price: 6500, max_price: 7200, modal_price: 6850, unit: 'per quintal', date: '2026-09-19' },
    { commodity: 'Cotton', market: 'Surat', min_price: 6400, max_price: 7100, modal_price: 6750, unit: 'per quintal', date: '2026-09-19' },
  ],
  'corn': [
    { commodity: 'Corn', market: 'Delhi', min_price: 1800, max_price: 2000, modal_price: 1900, unit: 'per quintal', date: '2026-09-19' },
    { commodity: 'Corn', market: 'Hyderabad', min_price: 1750, max_price: 1950, modal_price: 1850, unit: 'per quintal', date: '2026-09-19' },
  ],
};

export const get_market_prices: ToolImplementation = {
  schema: {
    name: 'get_market_prices',
    description: 'Get current market prices for crops and commodities',
    parameters: {
      type: 'object',
      properties: {
        commodity: {
          type: 'string',
          description: 'Name of the commodity (e.g., wheat, rice, cotton)',
        },
        market: {
          type: 'string',
          description: 'Market name or location',
          default: 'nearest',
        },
        state: {
          type: 'string',
          description: 'State name',
        },
      },
      required: ['commodity'],
    },
    returns: {
      type: 'object',
      properties: {
        commodity: { type: 'string' },
        market: { type: 'string' },
        min_price: { type: 'number' },
        max_price: { type: 'number' },
        modal_price: { type: 'number' },
        unit: { type: 'string' },
        date: { type: 'string' },
      },
    },
  },
  handler: async (params): Promise<ToolExecutionResult> => {
    const { commodity, market = 'nearest', state } = params as {
      commodity: string;
      market?: string;
      state?: string;
    };
    
    try {
      const commodityKey = commodity.toLowerCase();
      const prices = mockPrices[commodityKey];
      
      if (!prices || prices.length === 0) {
        return {
          success: false,
          error: `No price data available for ${commodity}. Please try wheat, rice, cotton, or corn.`,
        };
      }

      // Filter by market if specified
      let priceData = prices;
      if (market !== 'nearest') {
        const marketFilter = market.toLowerCase();
        priceData = prices.filter(p => p.market.toLowerCase().includes(marketFilter));
      }

      if (priceData.length === 0) {
        priceData = prices; // Use all markets if specific not found
      }

      // Return the first match or average
      const result = priceData[0];

      return {
        success: true,
        data: {
          commodity: result.commodity,
          market: result.market,
          min_price: result.min_price,
          max_price: result.max_price,
          modal_price: result.modal_price,
          unit: result.unit,
          date: result.date,
        },
      };
    } catch (error) {
      return {
        success: false,
        error: `Failed to get market prices: ${error instanceof Error ? error.message : 'Unknown error'}`,
      };
    }
  },
};

export const get_price_history: ToolImplementation = {
  schema: {
    name: 'get_price_history',
    description: 'Get historical price data for a commodity',
    parameters: {
      type: 'object',
      properties: {
        commodity: { type: 'string' },
        market: { type: 'string', default: 'nearest' },
        days: { type: 'number', default: 7, description: 'Number of days of history' },
      },
      required: ['commodity'],
    },
    returns: {
      type: 'object',
      properties: {
        commodity: { type: 'string' },
        market: { type: 'string' },
        history: { type: 'array' },
      },
    },
  },
  handler: async (params): Promise<ToolExecutionResult> => {
    const { commodity, market = 'nearest', days = 7 } = params as {
      commodity: string;
      market?: string;
      days?: number;
    };
    
    try {
      const commodityKey = commodity.toLowerCase();
      const prices = mockPrices[commodityKey];
      
      if (!prices || prices.length === 0) {
        return {
          success: false,
          error: `No price data available for ${commodity}.`,
        };
      }

      // Generate mock history
      const history = [];
      const basePrice = prices[0].modal_price;
      
      for (let i = days - 1; i >= 0; i--) {
        const date = new Date();
        date.setDate(date.getDate() - i);
        
        // Add some variation
        const variation = (Math.random() - 0.5) * 200;
        const price = Math.max(1000, basePrice + variation);
        
        history.push({
          date: date.toISOString().split('T')[0],
          price: Math.round(price),
          trend: variation > 0 ? 'up' : variation < 0 ? 'down' : 'stable',
        });
      }

      return {
        success: true,
        data: {
          commodity: prices[0].commodity,
          market: prices[0].market,
          history,
        },
      };
    } catch (error) {
      return {
        success: false,
        error: `Failed to get price history: ${error instanceof Error ? error.message : 'Unknown error'}`,
      };
    }
  },
};

export const compare_prices: ToolImplementation = {
  schema: {
    name: 'compare_prices',
    description: 'Compare prices across different markets',
    parameters: {
      type: 'object',
      properties: {
        commodity: { type: 'string' },
        markets: {
          type: 'array',
          items: { type: 'string' },
          description: 'List of market names to compare',
        },
      },
      required: ['commodity', 'markets'],
    },
    returns: {
      type: 'object',
      properties: {
        commodity: { type: 'string' },
        comparisons: { type: 'array' },
      },
    },
  },
  handler: async (params): Promise<ToolExecutionResult> => {
    const { commodity, markets } = params as {
      commodity: string;
      markets: string[];
    };
    
    try {
      const commodityKey = commodity.toLowerCase();
      const prices = mockPrices[commodityKey];
      
      if (!prices || prices.length === 0) {
        return {
          success: false,
          error: `No price data available for ${commodity}.`,
        };
      }

      const comparisons = markets.map(marketName => {
        const marketLower = marketName.toLowerCase();
        const marketData = prices.find(p => 
          p.market.toLowerCase().includes(marketLower)
        );
        
        return {
          market: marketName,
          available: !!marketData,
          min_price: marketData?.min_price,
          max_price: marketData?.max_price,
          modal_price: marketData?.modal_price,
          unit: marketData?.unit,
        };
      });

      return {
        success: true,
        data: {
          commodity: prices[0].commodity,
          comparisons,
        },
      };
    } catch (error) {
      return {
        success: false,
        error: `Failed to compare prices: ${error instanceof Error ? error.message : 'Unknown error'}`,
      };
    }
  },
};

// Export all tools
export default {
  get_market_prices,
  get_price_history,
  compare_prices,
};
