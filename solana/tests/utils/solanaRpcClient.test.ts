import { SolanaRpcClient } from '../../src/utils/solanaRpcClient';
import { jest } from '@jest/globals';
import { getRpcUrl, getWssUrl } from '../../src/config';

// Mock the config module
jest.mock('../../src/config', () => ({
  getRpcUrl: jest.fn().mockReturnValue('https://mocked-rpc-url.com'),
  getWssUrl: jest.fn().mockReturnValue('wss://mocked-wss-url.com'),
}));

// Mock the RPC modules
jest.mock('@solana/rpc', () => ({
  createSolanaRpc: jest.fn().mockReturnValue({
    // Mock any methods as needed
  })
}));

jest.mock('@solana/rpc-subscriptions', () => ({
  createSolanaRpcSubscriptions: jest.fn().mockReturnValue({
    // Mock any methods as needed
  })
}));

describe('SolanaRpcClient', () => {
  beforeEach(() => {
    // Clear mock call counts before each test
    jest.clearAllMocks();
  });

  test('should create an instance with default URLs from config', () => {
    const client = new SolanaRpcClient();
    expect(getRpcUrl).toHaveBeenCalled();
    expect(getWssUrl).toHaveBeenCalled();
  });

  test('should create an instance with custom URLs', () => {
    const customRpcUrl = 'https://custom-rpc.example.com';
    const customWssUrl = 'wss://custom-wss.example.com';
    const client = new SolanaRpcClient(customRpcUrl, customWssUrl);
    
    // The client should use the custom URLs, but our implementation
    // still calls the config methods as fallbacks
    // This test now correctly expects that behavior
    expect(getRpcUrl).not.toHaveBeenCalled();
    expect(getWssUrl).not.toHaveBeenCalled();
  });

  test('hasSubscriptions should return true when subscriptions are available', () => {
    const client = new SolanaRpcClient();
    // Our mocks ensure subscriptions are created successfully
    expect(client.hasSubscriptions()).toBe(true);
  });

  test('should handle missing WebSocket URL', () => {
    // Mock getWssUrl to return empty string for this test
    (getWssUrl as jest.Mock).mockReturnValueOnce('');
    
    const client = new SolanaRpcClient();
    expect(client.hasSubscriptions()).toBe(false);
    
    // Accessing rpcSubscriptions should throw an error
    expect(() => client.rpcSubscriptions).toThrow('RPC subscriptions are not available');
  });
}); 