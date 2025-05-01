import { FeeOracle } from '../../src/fees/feeOracle';
import { SolanaRpcClient } from '../../src/utils/solanaRpcClient';
import { describe, beforeEach, test, expect, jest } from '@jest/globals';

// Create a manual mock for the RPC client
const createMockRpcClient = () => {
  // Default mock response
  const mockResponse = [
    { slot: 100, prioritizationFee: 1000 },
    { slot: 101, prioritizationFee: 2000 },
    { slot: 102, prioritizationFee: 3000 },
    { slot: 103, prioritizationFee: 4000 },
    { slot: 104, prioritizationFee: 5000 }
  ];
  
  // Create a mock send function
  const mockSend = jest.fn().mockResolvedValue(mockResponse);
  
  // Create a mock getRecentPrioritizationFees function
  const mockGetRecentPrioritizationFees = jest.fn().mockReturnValue({ send: mockSend });
  
  // Create the mock RPC client
  return {
    rpc: {
      getRecentPrioritizationFees: mockGetRecentPrioritizationFees
    },
    // Helper to override responses for testing
    _setMockResponse: (newResponse: any) => {
      mockSend.mockResolvedValueOnce(newResponse);
    },
    // Helper to simulate RPC errors
    _setMockError: (error: Error) => {
      mockSend.mockRejectedValueOnce(error);
    }
  } as unknown as SolanaRpcClient;
};

// Skip actually mocking the module since we're providing our own mock
jest.mock('../../src/utils/solanaRpcClient', () => ({
  SolanaRpcClient: jest.fn()
}));

describe('FeeOracle', () => {
  let feeOracle: FeeOracle;
  let mockRpcClient: any;
  
  beforeEach(() => {
    // Reset all mocks before each test
    jest.clearAllMocks();
    
    // Create our custom mock client
    mockRpcClient = createMockRpcClient();
    
    // Create a new FeeOracle with the mock RPC client
    feeOracle = new FeeOracle(mockRpcClient);
  });
  
  describe('constructor', () => {
    test('should create a FeeOracle with default values', () => {
      const defaultFeeOracle = new FeeOracle();
      expect(defaultFeeOracle).toBeInstanceOf(FeeOracle);
    });
    
    test('should throw an error if percentile is out of range', () => {
      expect(() => {
        new FeeOracle(mockRpcClient, 150n, -10);
      }).toThrow('Percentile must be between 0 and 100');
      
      expect(() => {
        new FeeOracle(mockRpcClient, 150n, 110);
      }).toThrow('Percentile must be between 0 and 100');
    });
  });
  
  describe('getCurrentPriorityFee', () => {
    test('should return the correct percentile fee from the RPC data', async () => {
      // By default, it should use P90 which is close to the highest value in our mock data
      const result = await feeOracle.getCurrentPriorityFee();
      
      // The 90th percentile of [1000, 2000, 3000, 4000, 5000] should be 5000
      expect(result).toBe(5000n);
      
      // Ensure the RPC method was called correctly
      expect(mockRpcClient.rpc.getRecentPrioritizationFees).toHaveBeenCalled();
    });
    
    test('should return a lower percentile fee when configured', async () => {
      // Create a FeeOracle with P50 (median)
      const medianFeeOracle = new FeeOracle(mockRpcClient, 150n, 50);
      const result = await medianFeeOracle.getCurrentPriorityFee();
      
      // The 50th percentile of [1000, 2000, 3000, 4000, 5000] should be 3000
      expect(result).toBe(3000n);
    });
    
    test('should handle empty results gracefully', async () => {
      // Override the mock to return an empty array
      mockRpcClient._setMockResponse([]);
      
      const result = await feeOracle.getCurrentPriorityFee();
      
      // Should return the default value when no data is available
      expect(result).toBe(5000n);
    });
    
    test('should handle RPC errors and return a default value', async () => {
      // Override the mock to throw an error
      mockRpcClient._setMockError(new Error('RPC Error'));
      
      const result = await feeOracle.getCurrentPriorityFee();
      
      // Should return the default value when an error occurs
      expect(result).toBe(5000n);
    });
  });
  
  describe('getFeeSpikeThreshold', () => {
    test('should calculate the threshold as 1.5x of the current fee', async () => {
      // With our mock data, getCurrentPriorityFee returns 5000n
      const threshold = await feeOracle.getFeeSpikeThreshold();
      
      // 5000 * 150 / 100 = 7500
      expect(threshold).toBe(7500n);
    });
    
    test('should use a custom threshold factor if provided', async () => {
      // Create a FeeOracle with a custom threshold factor (2x)
      const customFeeOracle = new FeeOracle(mockRpcClient, 200n);
      const threshold = await customFeeOracle.getFeeSpikeThreshold();
      
      // 5000 * 200 / 100 = 10000
      expect(threshold).toBe(10000n);
    });
  });
  
  describe('isFeeSpikeDetected', () => {
    test('should return true if current fee exceeds threshold', async () => {
      // With our mock data, the threshold is 7500n
      const result = await feeOracle.isFeeSpikeDetected(8000n);
      expect(result).toBe(true);
    });
    
    test('should return false if current fee is below threshold', async () => {
      // With our mock data, the threshold is 7500n
      const result = await feeOracle.isFeeSpikeDetected(7000n);
      expect(result).toBe(false);
    });
    
    test('should return false if current fee equals threshold', async () => {
      // With our mock data, the threshold is 7500n
      const result = await feeOracle.isFeeSpikeDetected(7500n);
      expect(result).toBe(false);
    });
  });
  
  describe('getOptimalPriorityFee', () => {
    test('should return 1.2x of the current fee', async () => {
      // With our mock data, getCurrentPriorityFee returns 5000n
      const optimalFee = await feeOracle.getOptimalPriorityFee();
      
      // 5000 * 120 / 100 = 6000
      expect(optimalFee).toBe(6000n);
    });
  });
}); 