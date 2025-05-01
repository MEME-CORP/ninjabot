/// <reference types="jest" />

import { Keypair, PublicKey } from '@solana/web3.js';
import { WalletFunder, WalletFunderEvent, createWalletFunder, WalletFunderEventPayloads } from '../../src/funding/walletFunder';
import { SolanaRpcClient } from '../../src/utils/solanaRpcClient';
import { FeeOracle } from '../../src/fees/feeOracle';
import { SolNetworkError, TxTimeoutError } from '../../src/utils/errors';
import { createMockRpcClient, createMockFeeOracle } from '../helpers/testMocks';

// Mock dependencies
jest.mock('../../src/utils/solanaRpcClient');
jest.mock('../../src/fees/feeOracle');

describe('WalletFunder', () => {
  // Test variables
  let walletFunder: WalletFunder;
  let mockRpcClient: jest.Mocked<SolanaRpcClient>;
  let mockFeeOracle: jest.Mocked<FeeOracle>;
  let motherWallet: Keypair;
  let childAddresses: string[];
  
  // Set up mocks and test instances before each test
  beforeEach(() => {
    // Reset mocks
    jest.clearAllMocks();
    
    // Create mock instances using test helpers
    mockRpcClient = createMockRpcClient();
    mockFeeOracle = createMockFeeOracle();
    
    // Create test wallet funder
    walletFunder = createWalletFunder(
      mockRpcClient,
      mockFeeOracle,
      3, // maxRetries
      100, // retryDelayMs (using small value for faster tests)
      1000, // confirmationTimeoutMs (using small value for faster tests)
      2 // maxChildrenPerChunk (small value to test chunking)
    );
    
    // Create test mother wallet
    motherWallet = Keypair.generate();
    
    // Create test child addresses
    childAddresses = [
      Keypair.generate().publicKey.toString(),
      Keypair.generate().publicKey.toString(),
      Keypair.generate().publicKey.toString()
    ];
  });
  
  describe('constructor', () => {
    it('should create a WalletFunder instance with default values', () => {
      const defaultWalletFunder = new WalletFunder();
      expect(defaultWalletFunder).toBeInstanceOf(WalletFunder);
    });
    
    it('should create a WalletFunder instance with custom values', () => {
      const customWalletFunder = new WalletFunder(
        mockRpcClient,
        mockFeeOracle,
        5,
        1000,
        30000,
        10
      );
      expect(customWalletFunder).toBeInstanceOf(WalletFunder);
    });
  });
  
  describe('createWalletFunder', () => {
    it('should create a WalletFunder instance with factory function', () => {
      const factoryWalletFunder = createWalletFunder(
        mockRpcClient,
        mockFeeOracle
      );
      expect(factoryWalletFunder).toBeInstanceOf(WalletFunder);
    });
  });
  
  describe('fundChildWallets', () => {
    it('should successfully fund child wallets', async () => {
      // Mock event listener to track emitted events
      const events: { type: WalletFunderEvent; data: any }[] = [];
      walletFunder.on(WalletFunderEvent.FUNDING_STARTED, 
        (data: WalletFunderEventPayloads[WalletFunderEvent.FUNDING_STARTED]) => {
          events.push({ type: WalletFunderEvent.FUNDING_STARTED, data });
        }
      );
      walletFunder.on(WalletFunderEvent.FUNDING_COMPLETED, 
        (data: WalletFunderEventPayloads[WalletFunderEvent.FUNDING_COMPLETED]) => {
          events.push({ type: WalletFunderEvent.FUNDING_COMPLETED, data });
        }
      );
      walletFunder.on(WalletFunderEvent.TRANSACTION_SENT, 
        (data: WalletFunderEventPayloads[WalletFunderEvent.TRANSACTION_SENT]) => {
          events.push({ type: WalletFunderEvent.TRANSACTION_SENT, data });
        }
      );
      
      // Call the function
      const result = await walletFunder.fundChildWallets(
        motherWallet,
        childAddresses,
        1000000000n, // 1 SOL per child
        { maxChildrenPerChunk: 2 }
      );
      
      // Verify RPC calls were made correctly
      expect(mockRpcClient.rpc.getBalance).toHaveBeenCalledWith(
        motherWallet.publicKey.toString(),
        { commitment: 'confirmed' }
      );
      
      // Expect two chunks (3 children with 2 per chunk)
      expect(mockRpcClient.rpc.sendTransaction).toHaveBeenCalledTimes(2);
      
      // Verify the result
      expect(result).toEqual(expect.objectContaining({
        totalTransactions: 2,
        successfulTransactions: 2,
        failedTransactions: 0,
        totalFundedAmount: 3000000000n, // 3 SOL total
        fundedChildAddresses: childAddresses,
        failedChildAddresses: []
      }));
      
      // Verify events were emitted
      expect(events).toContainEqual(
        expect.objectContaining({
          type: WalletFunderEvent.FUNDING_STARTED
        })
      );
      expect(events).toContainEqual(
        expect.objectContaining({
          type: WalletFunderEvent.FUNDING_COMPLETED
        })
      );
      expect(events.filter(e => e.type === WalletFunderEvent.TRANSACTION_SENT).length).toBe(2);
    });
    
    it('should throw an error if mother wallet has insufficient balance', async () => {
      // Override the mock to return a small balance
      mockRpcClient.rpc.getBalance = jest.fn().mockReturnValue({
        send: jest.fn().mockResolvedValue(100000n) // 0.0001 SOL
      });
      
      // Expect the function to throw
      await expect(
        walletFunder.fundChildWallets(
          motherWallet,
          childAddresses,
          1000000000n // 1 SOL per child
        )
      ).rejects.toThrow('Insufficient balance in mother wallet');
    });
    
    it('should handle validation errors', async () => {
      // Test with invalid mother wallet
      await expect(
        walletFunder.fundChildWallets(
          null as unknown as Keypair,
          childAddresses,
          1000000000n
        )
      ).rejects.toThrow('Invalid mother wallet');
      
      // Test with empty child addresses
      await expect(
        walletFunder.fundChildWallets(
          motherWallet,
          [],
          1000000000n
        )
      ).rejects.toThrow('No child addresses provided');
      
      // Test with negative amount
      await expect(
        walletFunder.fundChildWallets(
          motherWallet,
          childAddresses,
          -1000000000n
        )
      ).rejects.toThrow('Amount per child must be positive');
    });
    
    it('should handle transaction failures with retries', async () => {
      // Set up mock to fail on first attempt, succeed on second
      const mockSendFn = jest.fn()
        .mockRejectedValueOnce(new SolNetworkError('Network error'))
        .mockResolvedValueOnce('mock-signature');
      
      mockRpcClient.rpc.sendTransaction = jest.fn().mockReturnValue({
        send: mockSendFn
      });
      
      // Mock event listener for retry events
      const retryEvents: any[] = [];
      walletFunder.on(WalletFunderEvent.RETRY_ATTEMPT, 
        (data: WalletFunderEventPayloads[WalletFunderEvent.RETRY_ATTEMPT]) => {
          retryEvents.push(data);
        }
      );
      
      // Call the function
      const result = await walletFunder.fundChildWallets(
        motherWallet,
        childAddresses.slice(0, 2), // Use just 2 addresses for simplicity
        1000000000n,
        { maxChildrenPerChunk: 2 }
      );
      
      // Verify sendTransaction was called twice (initial fail + retry)
      expect(mockSendFn).toHaveBeenCalledTimes(2);
      
      // Verify retry event was emitted
      expect(retryEvents.length).toBe(1);
      expect(retryEvents[0]).toEqual(expect.objectContaining({
        attempt: 1,
        error: 'Network error'
      }));
      
      // Verify the result
      expect(result.successfulTransactions).toBe(1);
      expect(result.failedTransactions).toBe(0);
    });
    
    it('should handle transaction confirmation timeouts', async () => {
      // Override confirmTransaction to time out
      mockRpcClient.rpc.confirmTransaction = jest.fn().mockReturnValue({
        send: jest.fn().mockImplementation(() => {
          // This promise intentionally doesn't resolve within the timeout
          return new Promise(resolve => {
            setTimeout(() => resolve({
              value: { err: null }
            }), 2000);
          });
        })
      });
      
      // Mock event listener for transaction failure
      const failEvents: any[] = [];
      walletFunder.on(WalletFunderEvent.TRANSACTION_FAILED, 
        (data: WalletFunderEventPayloads[WalletFunderEvent.TRANSACTION_FAILED]) => {
          failEvents.push(data);
        }
      );
      
      // Call the function with a very short confirmation timeout
      const result = await walletFunder.fundChildWallets(
        motherWallet,
        childAddresses.slice(0, 2),
        1000000000n,
        { 
          maxChildrenPerChunk: 2,
          confirmationTimeoutMs: 100 // Very short timeout to trigger error
        }
      );
      
      // Verify failure events
      expect(failEvents.length).toBe(1);
      expect(failEvents[0].error).toBeInstanceOf(TxTimeoutError);
      
      // Verify the result
      expect(result.successfulTransactions).toBe(0);
      expect(result.failedTransactions).toBe(1);
      expect(result.fundedChildAddresses).toEqual([]);
      expect(result.failedChildAddresses).toEqual(childAddresses.slice(0, 2));
    });
    
    it('should handle non-retryable errors', async () => {
      // Override sendTransaction to fail with a non-retryable error
      mockRpcClient.rpc.sendTransaction = jest.fn().mockReturnValue({
        send: jest.fn().mockRejectedValue(new Error('Invalid parameter'))
      });
      
      // Call the function
      const result = await walletFunder.fundChildWallets(
        motherWallet,
        childAddresses.slice(0, 2),
        1000000000n,
        { maxChildrenPerChunk: 2 }
      );
      
      // Verify the result
      expect(result.successfulTransactions).toBe(0);
      expect(result.failedTransactions).toBe(1);
      expect(result.fundedChildAddresses).toEqual([]);
      expect(result.failedChildAddresses).toEqual(childAddresses.slice(0, 2));
    });
  });
  
  describe('event emission', () => {
    it('should emit all expected events during successful funding', async () => {
      // Set up event tracking
      const eventCounts = new Map<WalletFunderEvent, number>();
      Object.values(WalletFunderEvent).forEach(event => {
        walletFunder.on(event, () => {
          eventCounts.set(event, (eventCounts.get(event) || 0) + 1);
        });
      });
      
      // Call the function
      await walletFunder.fundChildWallets(
        motherWallet,
        childAddresses,
        1000000000n,
        { maxChildrenPerChunk: 2 }
      );
      
      // Verify events
      expect(eventCounts.get(WalletFunderEvent.FUNDING_STARTED)).toBe(1);
      expect(eventCounts.get(WalletFunderEvent.FUNDING_COMPLETED)).toBe(1);
      expect(eventCounts.get(WalletFunderEvent.CHUNK_STARTED)).toBe(2); // 2 chunks
      expect(eventCounts.get(WalletFunderEvent.CHUNK_COMPLETED)).toBe(2); // 2 chunks
      expect(eventCounts.get(WalletFunderEvent.TRANSACTION_SENT)).toBe(2); // 2 transactions
      expect(eventCounts.get(WalletFunderEvent.TRANSACTION_CONFIRMED)).toBe(2); // 2 confirmations
    });
  });
}); 