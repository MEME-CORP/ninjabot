/// <reference types="jest" />

/**
 * Test helpers for creating mock objects
 */
import { SolanaRpcClient } from '../../src/utils/solanaRpcClient';
import { FeeOracle } from '../../src/fees/feeOracle';

/**
 * Creates a mock SolanaRpcClient with common methods predefined
 */
export function createMockRpcClient(
  overrides: Partial<Record<string, jest.Mock>> = {}
): jest.Mocked<SolanaRpcClient> {
  const defaultMocks = {
    getLatestBlockhash: jest.fn().mockReturnValue({
      send: jest.fn().mockResolvedValue({
        value: {
          blockhash: 'mock-blockhash',
          lastValidBlockHeight: 1000n
        }
      })
    }),
    sendTransaction: jest.fn().mockReturnValue({
      send: jest.fn().mockResolvedValue('mock-signature')
    }),
    confirmTransaction: jest.fn().mockReturnValue({
      send: jest.fn().mockResolvedValue({
        value: { err: null }
      })
    }),
    getTransaction: jest.fn().mockReturnValue({
      send: jest.fn().mockResolvedValue({
        meta: { fee: 5000 }
      })
    }),
    getBalance: jest.fn().mockReturnValue({
      send: jest.fn().mockResolvedValue(10000000000n) // 10 SOL
    }),
    requestAirdrop: jest.fn().mockReturnValue({
      send: jest.fn().mockResolvedValue('mock-airdrop-signature')
    })
  };

  // Merge defaults with overrides
  const mockMethods = { ...defaultMocks, ...overrides };

  // Create the mock RPC client
  return {
    rpc: mockMethods,
    getLatestBlockhash: jest.fn().mockResolvedValue({
      blockhash: 'mock-blockhash',
      lastValidBlockHeight: 1000n
    }),
    hasSubscriptions: jest.fn().mockReturnValue(false)
  } as unknown as jest.Mocked<SolanaRpcClient>;
}

/**
 * Creates a mock FeeOracle with common methods predefined
 */
export function createMockFeeOracle(): jest.Mocked<FeeOracle> {
  return {
    getOptimalPriorityFee: jest.fn().mockResolvedValue(1000n),
    detectFeeSpike: jest.fn().mockResolvedValue(false)
  } as unknown as jest.Mocked<FeeOracle>;
} 