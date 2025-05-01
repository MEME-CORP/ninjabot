import { TokenInfo } from '../../src/tokens/tokenInfo';
import { SolanaRpcClient } from '../../src/utils/solanaRpcClient';
import { describe, beforeEach, test, expect, jest } from '@jest/globals';

// Simplified mock implementation
const createMockRpcClient = () => {
  // Mock token account data
  const createTokenData = (decimals: number, supply: number) => {
    const buffer = Buffer.alloc(82); // Standard mint size
    buffer.writeUInt8(1, 45); // Set isInitialized to true
    buffer.writeUInt8(decimals, 44); // Set decimals
    buffer.writeUInt32LE(supply, 36); // Set supply lower bits
    buffer.writeUInt32LE(0, 40); // Set supply upper bits
    return buffer.toString('base64');
  };

  // Create mock data for different token types
  const mockData = {
    'validMint6Decimals': createTokenData(6, 1000000),
    'validMint9Decimals': createTokenData(9, 0),
    'invalidMint': 'invalid-data' // Not a valid base64 encoded token
  };

  // Mock send function for getAccountInfo
  const mockSend = jest.fn().mockImplementation(() => {
    // This will be modified by _setMintAddress to return different responses
    const mintAddress = mockRpcClient._currentMintAddress;
    
    if (mintAddress in mockData) {
      return {
        executable: false,
        owner: 'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA', // Token program ID
        lamports: 1000000,
        data: [mockData[mintAddress], 'base64'],
        rentEpoch: 0
      };
    }
    
    return null; // Account not found
  });

  // Create the mock RPC client
  const mockRpcClient: any = {
    rpc: {
      getAccountInfo: jest.fn().mockReturnValue({ send: mockSend })
    },
    // Track the current mint address we're testing
    _currentMintAddress: 'validMint6Decimals',
    // Helper to set the mint address for testing
    _setMintAddress: (address: string) => {
      mockRpcClient._currentMintAddress = address;
    },
    // Helper to simulate RPC errors
    _setMockError: () => {
      mockSend.mockRejectedValueOnce(new Error('RPC Error'));
    }
  };

  return mockRpcClient;
};

// Skip actually mocking the module, we're injecting our mock directly
jest.mock('../../src/utils/solanaRpcClient', () => ({
  SolanaRpcClient: jest.fn()
}));

describe('TokenInfo', () => {
  let tokenInfo: TokenInfo;
  let mockRpcClient: any;
  
  beforeEach(() => {
    // Reset all mocks before each test
    jest.clearAllMocks();
    
    // Create our custom mock client
    mockRpcClient = createMockRpcClient();
    
    // Create a new TokenInfo with the mock RPC client
    tokenInfo = new TokenInfo(mockRpcClient);
  });
  
  describe('getTokenDecimals', () => {
    test('should return correct decimals for a 6-decimal token', async () => {
      mockRpcClient._setMintAddress('validMint6Decimals');
      const decimals = await tokenInfo.getTokenDecimals('validMint6Decimals');
      expect(decimals).toBe(6);
    });
    
    test('should return correct decimals for a 9-decimal token', async () => {
      mockRpcClient._setMintAddress('validMint9Decimals');
      const decimals = await tokenInfo.getTokenDecimals('validMint9Decimals');
      expect(decimals).toBe(9);
    });
    
    test('should return default decimals for a non-existent mint', async () => {
      mockRpcClient._setMintAddress('nonExistentMint');
      const decimals = await tokenInfo.getTokenDecimals('nonExistentMint');
      expect(decimals).toBe(9); // Default is 9 for SOL
    });
    
    test('should return default decimals for invalid mint data', async () => {
      mockRpcClient._setMintAddress('invalidMint');
      const decimals = await tokenInfo.getTokenDecimals('invalidMint');
      expect(decimals).toBe(9); // Default is 9 for SOL
    });
    
    test('should handle RPC errors and return default decimals', async () => {
      mockRpcClient._setMintAddress('validMint6Decimals');
      mockRpcClient._setMockError();
      
      const decimals = await tokenInfo.getTokenDecimals('validMint6Decimals');
      expect(decimals).toBe(9); // Default is 9 for SOL
    });
  });
  
  describe('isValidTokenMint', () => {
    test('should return true for a valid mint', async () => {
      mockRpcClient._setMintAddress('validMint6Decimals');
      const isValid = await tokenInfo.isValidTokenMint('validMint6Decimals');
      expect(isValid).toBe(true);
    });
    
    test('should return false for a non-existent mint', async () => {
      mockRpcClient._setMintAddress('nonExistentMint');
      const isValid = await tokenInfo.isValidTokenMint('nonExistentMint');
      expect(isValid).toBe(false);
    });
    
    test('should return false for invalid mint data', async () => {
      mockRpcClient._setMintAddress('invalidMint');
      const isValid = await tokenInfo.isValidTokenMint('invalidMint');
      expect(isValid).toBe(false);
    });
    
    test('should handle RPC errors and return false', async () => {
      mockRpcClient._setMintAddress('validMint6Decimals');
      mockRpcClient._setMockError();
      
      const isValid = await tokenInfo.isValidTokenMint('validMint6Decimals');
      expect(isValid).toBe(false);
    });
  });
  
  describe('getTokenSupply', () => {
    test('should return correct supply for a token', async () => {
      mockRpcClient._setMintAddress('validMint6Decimals');
      const supply = await tokenInfo.getTokenSupply('validMint6Decimals');
      expect(supply).toBe(1000000n);
    });
    
    test('should return correct supply for a token with large supply', async () => {
      // Create special data for a token with large supply
      const largeSupplyBuffer = Buffer.alloc(82);
      largeSupplyBuffer.writeUInt8(1, 45); // Set isInitialized to true
      largeSupplyBuffer.writeUInt8(9, 44); // Set decimals to 9
      largeSupplyBuffer.writeUInt32LE(0, 36); // Lower 32 bits
      largeSupplyBuffer.writeUInt32LE(1, 40); // Upper 32 bits (1 << 32 = 4,294,967,296)
      
      // Add custom handler for the large supply case
      const mockSend = mockRpcClient.rpc.getAccountInfo().send;
      mockSend.mockImplementationOnce(() => ({
        executable: false,
        owner: 'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA',
        lamports: 1000000,
        data: [largeSupplyBuffer.toString('base64'), 'base64'],
        rentEpoch: 0
      }));
      
      const supply = await tokenInfo.getTokenSupply('largeMint');
      const expectedSupply = 1n << 32n; // 4,294,967,296
      expect(supply).toBe(expectedSupply);
    });
    
    test('should return 0 for a non-existent mint', async () => {
      mockRpcClient._setMintAddress('nonExistentMint');
      const supply = await tokenInfo.getTokenSupply('nonExistentMint');
      expect(supply).toBe(0n);
    });
    
    test('should return 0 for invalid mint data', async () => {
      mockRpcClient._setMintAddress('invalidMint');
      const supply = await tokenInfo.getTokenSupply('invalidMint');
      expect(supply).toBe(0n);
    });
    
    test('should handle RPC errors and return 0', async () => {
      mockRpcClient._setMintAddress('validMint6Decimals');
      mockRpcClient._setMockError();
      
      const supply = await tokenInfo.getTokenSupply('validMint6Decimals');
      expect(supply).toBe(0n);
    });
  });
  
  describe('standalone getTokenDecimals function', () => {
    test('should use the TokenInfo class internally and return decimals', async () => {
      // Import the standalone function
      const { getTokenDecimals } = require('../../src/tokens/tokenInfo');
      
      // Set up the mock to return data for this test
      mockRpcClient._setMintAddress('validMint6Decimals');
      
      // Use the standalone function with our mock client
      const decimals = await getTokenDecimals('doesnt-matter', mockRpcClient);
      
      expect(decimals).toBe(6);
    });
  });
}); 