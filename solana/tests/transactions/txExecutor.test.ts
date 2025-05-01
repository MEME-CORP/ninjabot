import { TxExecutor, TxExecutorEvent, TxExecutorEventPayloads } from '../../src/transactions/txExecutor';
import { SolanaRpcClient } from '../../src/utils/solanaRpcClient';
import { FeeOracle } from '../../src/fees/feeOracle';
import { TokenInfo } from '../../src/tokens/tokenInfo';
import { DetailedTransferOp, OperationStatus } from '../../src/models/types';
import { WalletSignatureError } from '../../src/wallet/errors';
import { SolNetworkError } from '../../src/utils/errors';
import { jest, describe, beforeEach, it, expect } from '@jest/globals';

// Mock v2 web3.js functions
jest.mock('@solana/web3.js', () => ({
  createTransaction: jest.fn().mockReturnValue({
    /* mock transaction object */
  }),
  createTransactionMessage: jest.fn().mockReturnValue({
    /* mock message object */
  }),
  setTransactionFeePayer: jest.fn(),
  setTransactionLifetimeUsingBlockhash: jest.fn(),
  appendTransactionInstruction: jest.fn(),
  getSignatureFromTransaction: jest.fn().mockReturnValue('mockedSignature123'),
  signTransaction: jest.fn().mockResolvedValue(undefined),
  createTransferInstruction: jest.fn().mockReturnValue({
    /* mock instruction object */
  })
}));

// Mock compute budget program
jest.mock('@solana-program/compute-budget', () => ({
  createSetComputeUnitPriceInstruction: jest.fn().mockReturnValue({
    /* mock instruction object */
  })
}));

// Mock spl-token
jest.mock('@solana/spl-token', () => ({
  createTransferCheckedInstruction: jest.fn().mockReturnValue({
    /* mock instruction object */
  })
}));

// Mock dependencies
jest.mock('../../src/utils/solanaRpcClient');
jest.mock('../../src/fees/feeOracle');
jest.mock('../../src/tokens/tokenInfo');
jest.mock('../../src/wallet/walletManager');
jest.mock('../../src/config');

describe('TxExecutor', () => {
  let txExecutor: TxExecutor;
  let mockRpcClient: jest.Mocked<SolanaRpcClient>;
  let mockFeeOracle: jest.Mocked<FeeOracle>;
  let mockTokenInfo: jest.Mocked<TokenInfo>;
  
  // Sample operation for testing
  const sampleOp: DetailedTransferOp = {
    sourceIndex: 1,
    destinationAddress: 'DestAddr123456789abcdef',
    amount: BigInt(1000000),
    isFee: false
  };

  // Mock implementation setup
  beforeEach(() => {
    // Clear all mocks
    jest.clearAllMocks();
    
    // Create mock instances
    mockRpcClient = {
      getLatestBlockhash: jest.fn().mockResolvedValue({
        blockhash: 'mockhash123',
        lastValidBlockHeight: BigInt(100)
      }),
      rpc: {
        sendTransaction: jest.fn().mockReturnValue({
          send: jest.fn().mockResolvedValue(undefined)
        }),
        confirmTransaction: jest.fn().mockReturnValue({
          send: jest.fn().mockResolvedValue({
            value: { err: null }
          })
        }),
        getTokenAccountsByOwner: jest.fn().mockReturnValue({
          send: jest.fn().mockResolvedValue({
            value: [{ pubkey: 'tokenAccount123' }]
          })
        })
      } as any,
      hasSubscriptions: jest.fn().mockReturnValue(true),
      rpcSubscriptions: {} as any
    } as unknown as jest.Mocked<SolanaRpcClient>;
    
    mockFeeOracle = {
      getOptimalPriorityFee: jest.fn().mockResolvedValue(BigInt(5000)),
      getFeeSpikeThreshold: jest.fn().mockResolvedValue(BigInt(7500))
    } as unknown as jest.Mocked<FeeOracle>;
    
    mockTokenInfo = {
      getTokenData: jest.fn().mockResolvedValue({
        mint: 'tokenMintAddress',
        decimals: 9,
        supply: BigInt(1000000000),
        symbol: 'TEST'
      })
    } as unknown as jest.Mocked<TokenInfo>;
    
    // Mock wallet manager
    const { getWalletFromIndex } = require('../../src/wallet/walletManager');
    getWalletFromIndex.mockResolvedValue({
      publicKey: {
        toString: () => 'mockedPublicKey'
      }
    });
    
    // Create TxExecutor instance with mocked dependencies
    txExecutor = new TxExecutor(
      mockRpcClient,
      mockFeeOracle,
      mockTokenInfo as any,
      2, // maxRetries
      100, // retryDelayMs (short for testing)
      1000 // confirmationTimeoutMs (short for testing)
    );
  });

  describe('executeSolTransfer', () => {
    it('should execute a successful SOL transfer', async () => {
      // Setup event listener to verify events
      const sentEvent = jest.fn();
      const confirmedEvent = jest.fn();
      txExecutor.on(TxExecutorEvent.TRANSACTION_SENT, sentEvent);
      txExecutor.on(TxExecutorEvent.TRANSACTION_CONFIRMED, confirmedEvent);
      
      // Execute the transfer
      const result = await txExecutor.executeSolTransfer(sampleOp);
      
      // Verify result
      expect(result.status).toBe(OperationStatus.CONFIRMED);
      expect(result.signature).toBe('mockedSignature123');
      expect(result.confirmationTime).toBeDefined();
      expect(result.error).toBeUndefined();
      
      // Verify events
      expect(sentEvent).toHaveBeenCalledWith(expect.objectContaining({
        signature: 'mockedSignature123',
        operation: sampleOp
      }));
      
      expect(confirmedEvent).toHaveBeenCalledWith(expect.objectContaining({
        signature: 'mockedSignature123',
        operation: sampleOp,
        confirmationTime: expect.any(Number)
      }));
      
      // Verify transaction creation and submission flow
      const { 
        createTransaction, 
        createTransactionMessage, 
        setTransactionFeePayer, 
        setTransactionLifetimeUsingBlockhash,
        createTransferInstruction,
        appendTransactionInstruction,
        signTransaction
      } = require('@solana/web3.js');
      
      expect(createTransactionMessage).toHaveBeenCalled();
      expect(setTransactionFeePayer).toHaveBeenCalled();
      expect(setTransactionLifetimeUsingBlockhash).toHaveBeenCalled();
      expect(createTransferInstruction).toHaveBeenCalledWith(expect.objectContaining({
        from: 'mockedPublicKey',
        to: sampleOp.destinationAddress,
        amount: sampleOp.amount
      }));
      expect(appendTransactionInstruction).toHaveBeenCalled();
      expect(createTransaction).toHaveBeenCalled();
      expect(signTransaction).toHaveBeenCalled();
      expect(mockRpcClient.rpc.sendTransaction).toHaveBeenCalled();
      expect(mockRpcClient.rpc.confirmTransaction).toHaveBeenCalled();
    });
    
    it('should handle dry run mode', async () => {
      const result = await txExecutor.executeSolTransfer(sampleOp, { dryRun: true });
      
      expect(result.status).toBe(OperationStatus.SKIPPED);
      expect(result.signature).toBe('DRY_RUN_MODE');
      
      // Verify no transaction was created or sent
      const { createTransactionMessage } = require('@solana/web3.js');
      expect(createTransactionMessage).not.toHaveBeenCalled();
      expect(mockRpcClient.rpc.sendTransaction).not.toHaveBeenCalled();
    });
    
    it('should handle missing source wallet', async () => {
      // Mock wallet manager to return null
      const { getWalletFromIndex } = require('../../src/wallet/walletManager');
      getWalletFromIndex.mockResolvedValueOnce(null);
      
      const result = await txExecutor.executeSolTransfer(sampleOp);
      
      expect(result.status).toBe(OperationStatus.FAILED);
      expect(result.error).toContain('Failed to load source wallet');
    });
    
    it('should detect fee spikes and skip transactions', async () => {
      // Setup high fee condition
      mockFeeOracle.getOptimalPriorityFee.mockResolvedValueOnce(BigInt(10000));
      mockFeeOracle.getFeeSpikeThreshold.mockResolvedValueOnce(BigInt(7500));
      
      // Setup event listener for fee spike events
      const feeSpike = jest.fn();
      txExecutor.on(TxExecutorEvent.FEE_SPIKE_DETECTED, feeSpike);
      
      const result = await txExecutor.executeSolTransfer(sampleOp);
      
      expect(result.status).toBe(OperationStatus.SKIPPED);
      expect(result.error).toContain('Fee spike detected');
      
      expect(feeSpike).toHaveBeenCalledWith(expect.objectContaining({
        operation: sampleOp,
        currentFee: BigInt(10000),
        thresholdFee: BigInt(7500)
      }));
      
      // Verify no transaction was sent
      expect(mockRpcClient.rpc.sendTransaction).not.toHaveBeenCalled();
    });
    
    it('should bypass fee spike checks when disabled', async () => {
      // Setup high fee condition
      mockFeeOracle.getOptimalPriorityFee.mockResolvedValueOnce(BigInt(10000));
      mockFeeOracle.getFeeSpikeThreshold.mockResolvedValueOnce(BigInt(7500));
      
      const result = await txExecutor.executeSolTransfer(sampleOp, {
        checkFeeSpikeThreshold: false
      });
      
      // Should process the transaction despite the fee spike
      expect(result.status).toBe(OperationStatus.CONFIRMED);
      expect(mockRpcClient.rpc.sendTransaction).toHaveBeenCalled();
    });
    
    it('should retry on transient errors', async () => {
      // Set up sendTransaction to fail on first attempt but succeed on second
      let attempts = 0;
      mockRpcClient.rpc.sendTransaction = jest.fn().mockReturnValue({
        send: jest.fn().mockImplementation(() => {
          if (attempts === 0) {
            attempts++;
            throw new SolNetworkError('network timeout');
          }
          return Promise.resolve(undefined);
        })
      }) as any;
      
      // Setup event listeners
      const retryEvent = jest.fn();
      txExecutor.on(TxExecutorEvent.RETRY_ATTEMPT, retryEvent);
      
      const result = await txExecutor.executeSolTransfer(sampleOp);
      
      // Should eventually succeed
      expect(result.status).toBe(OperationStatus.CONFIRMED);
      
      // Should have triggered a retry event
      expect(retryEvent).toHaveBeenCalledWith(expect.objectContaining({
        attempt: 1,
        error: 'network timeout'
      }));
      
      // Should have called createTransactionMessage twice (initial + retry)
      const { createTransactionMessage } = require('@solana/web3.js');
      expect(createTransactionMessage).toHaveBeenCalledTimes(2);
    });
    
    it('should fail after max retries', async () => {
      // Always fail with network error
      mockRpcClient.rpc.sendTransaction = jest.fn().mockReturnValue({
        send: jest.fn().mockRejectedValue(new SolNetworkError('persistent network error'))
      }) as any;
      
      // Failed event listener
      const failedEvent = jest.fn();
      txExecutor.on(TxExecutorEvent.TRANSACTION_FAILED, failedEvent);
      
      const result = await txExecutor.executeSolTransfer(sampleOp);
      
      // Should fail
      expect(result.status).toBe(OperationStatus.FAILED);
      expect(result.error).toContain('persistent network error');
      
      // Failure event should be triggered
      expect(failedEvent).toHaveBeenCalledWith(expect.objectContaining({
        operation: sampleOp,
        error: expect.any(Error),
        retryCount: 2 // We should have tried the maxRetries (2) times
      }));
      
      // Should have called createTransactionMessage maxRetries + 1 times
      const { createTransactionMessage } = require('@solana/web3.js');
      expect(createTransactionMessage).toHaveBeenCalledTimes(3); // initial + 2 retries
    });
    
    it('should not retry on non-retryable errors', async () => {
      // Fail with signature error (non-retryable)
      mockRpcClient.rpc.sendTransaction = jest.fn().mockReturnValue({
        send: jest.fn().mockRejectedValue(new WalletSignatureError('Invalid signature'))
      }) as any;
      
      const result = await txExecutor.executeSolTransfer(sampleOp);
      
      // Should fail immediately without retry
      expect(result.status).toBe(OperationStatus.FAILED);
      expect(result.error).toContain('Invalid signature');
      
      // Should only try once
      const { createTransactionMessage } = require('@solana/web3.js');
      expect(createTransactionMessage).toHaveBeenCalledTimes(1);
    });
    
    it('should handle confirmation timeout', async () => {
      // Mock confirmTransaction to timeout
      mockRpcClient.rpc.confirmTransaction = jest.fn().mockReturnValue({
        send: jest.fn().mockImplementation(() => new Promise(resolve => setTimeout(() => resolve(null), 2000)))
      }) as any;
      
      const result = await txExecutor.executeSolTransfer(sampleOp);
      
      // Should fail due to timeout
      expect(result.status).toBe(OperationStatus.FAILED);
      expect(result.error).toContain('confirmation timeout');
    });
    
    it('should handle failed transaction confirmation', async () => {
      // Mock confirmation to return error
      mockRpcClient.rpc.confirmTransaction = jest.fn().mockReturnValue({
        send: jest.fn().mockResolvedValue({
          value: { err: { InstructionError: [0, 'Custom'] } }
        })
      }) as any;
      
      const result = await txExecutor.executeSolTransfer(sampleOp);
      
      expect(result.status).toBe(OperationStatus.FAILED);
      expect(result.error).toContain('Transaction failed');
    });
  });

  describe('executeTokenTransfer', () => {
    const tokenMint = 'TokenMintAddr123';
    
    it('should execute a successful token transfer', async () => {
      const result = await txExecutor.executeTokenTransfer(sampleOp, tokenMint);
      
      expect(result.status).toBe(OperationStatus.CONFIRMED);
      expect(result.signature).toBe('mockedSignature123');
      
      // Verify token account lookups
      expect(mockRpcClient.rpc.getTokenAccountsByOwner).toHaveBeenCalledTimes(2);
      
      // Verify token-specific instruction creation
      const { createTransferCheckedInstruction } = require('@solana/spl-token');
      expect(createTransferCheckedInstruction).toHaveBeenCalledWith(
        'tokenAccount123',
        tokenMint,
        'tokenAccount123',
        'mockedPublicKey',
        sampleOp.amount,
        9 // decimals
      );
      
      // Should have sent the transaction
      expect(mockRpcClient.rpc.sendTransaction).toHaveBeenCalled();
    });
    
    it('should handle missing source token account', async () => {
      // Mock empty token accounts for source
      mockRpcClient.rpc.getTokenAccountsByOwner = jest.fn().mockReturnValue({
        send: jest.fn().mockImplementationOnce(() => Promise.resolve({ value: [] }))
      }) as any;
      
      const result = await txExecutor.executeTokenTransfer(sampleOp, tokenMint);
      
      expect(result.status).toBe(OperationStatus.FAILED);
      expect(result.error).toContain('Source wallet has no token account');
    });
    
    it('should handle missing destination token account', async () => {
      // Mock empty token accounts for destination (second call)
      let callCount = 0;
      mockRpcClient.rpc.getTokenAccountsByOwner = jest.fn().mockReturnValue({
        send: jest.fn().mockImplementation(() => {
          callCount++;
          if (callCount === 1) {
            return Promise.resolve({ value: [{ pubkey: 'sourceTokenAccount' }] });
          } else {
            return Promise.resolve({ value: [] });
          }
        })
      }) as any;
      
      const result = await txExecutor.executeTokenTransfer(sampleOp, tokenMint);
      
      expect(result.status).toBe(OperationStatus.FAILED);
      expect(result.error).toContain('Destination wallet has no token account');
    });
    
    it('should handle invalid token mint', async () => {
      // Mock token info to throw TokenNotFoundError
      const { TokenNotFoundError } = require('../../src/tokens/tokenInfo');
      mockTokenInfo.getTokenData.mockRejectedValueOnce(
        new TokenNotFoundError('Invalid token mint')
      );
      
      const result = await txExecutor.executeTokenTransfer(sampleOp, 'invalidMint');
      
      expect(result.status).toBe(OperationStatus.FAILED);
      expect(result.error).toContain('Invalid token mint address');
    });
  });

  describe('executeBatch', () => {
    const operations: DetailedTransferOp[] = [
      { sourceIndex: 1, destinationAddress: 'Dest1', amount: BigInt(100), isFee: false },
      { sourceIndex: 2, destinationAddress: 'Dest2', amount: BigInt(200), isFee: false },
      { sourceIndex: 3, destinationAddress: 'FeeWallet', amount: BigInt(3), isFee: true }
    ];
    
    beforeEach(() => {
      // Mock config
      const { getConfig } = require('../../src/config');
      getConfig.mockReturnValue({ continueOnError: false });
    });
    
    it('should execute all operations in a batch', async () => {
      const results = await txExecutor.executeBatch(operations);
      
      expect(results.length).toBe(3);
      expect(results.every(r => r.status === OperationStatus.CONFIRMED)).toBe(true);
      
      // Should have been called for each operation
      const { createTransactionMessage } = require('@solana/web3.js');
      expect(createTransactionMessage).toHaveBeenCalledTimes(3);
    });
    
    it('should abort batch on critical error', async () => {
      // Make the second operation fail with a critical error
      let opIndex = 0;
      mockRpcClient.rpc.sendTransaction = jest.fn().mockReturnValue({
        send: jest.fn().mockImplementation(() => {
          opIndex++;
          if (opIndex === 2) {
            throw new Error('insufficient funds');
          }
          return Promise.resolve(undefined);
        })
      }) as any;
      
      const results = await txExecutor.executeBatch(operations);
      
      // Should have results for first and second operations only
      expect(results.length).toBe(2);
      expect(results[0].status).toBe(OperationStatus.CONFIRMED);
      expect(results[1].status).toBe(OperationStatus.FAILED);
      expect(results[1].error).toContain('insufficient funds');
      
      // Should not have executed the third operation
      const { createTransactionMessage } = require('@solana/web3.js');
      expect(createTransactionMessage).toHaveBeenCalledTimes(2);
    });
    
    it('should continue batch on non-critical error with continueOnError flag', async () => {
      // Configure to continue on error
      const { getConfig } = require('../../src/config');
      getConfig.mockReturnValue({ continueOnError: true });
      
      // Make the second operation fail with a non-critical error
      let opIndex = 0;
      mockRpcClient.rpc.sendTransaction = jest.fn().mockReturnValue({
        send: jest.fn().mockImplementation(() => {
          opIndex++;
          if (opIndex === 2) {
            throw new Error('transaction simulation failed');
          }
          return Promise.resolve(undefined);
        })
      }) as any;
      
      const results = await txExecutor.executeBatch(operations);
      
      // Should have results for all operations
      expect(results.length).toBe(3);
      expect(results[0].status).toBe(OperationStatus.CONFIRMED);
      expect(results[1].status).toBe(OperationStatus.FAILED);
      expect(results[2].status).toBe(OperationStatus.CONFIRMED);
      
      // Should have executed all operations
      const { createTransactionMessage } = require('@solana/web3.js');
      expect(createTransactionMessage).toHaveBeenCalledTimes(3);
    });
    
    it('should execute token transfers in batch mode', async () => {
      const tokenMint = 'TokenMintAddress123';
      const results = await txExecutor.executeBatch(operations, tokenMint);
      
      expect(results.length).toBe(3);
      expect(results.every(r => r.status === OperationStatus.CONFIRMED)).toBe(true);
      
      // Verify token-specific instruction creation was used
      const { createTransferCheckedInstruction } = require('@solana/spl-token');
      expect(createTransferCheckedInstruction).toHaveBeenCalledTimes(3);
    });
  });
}); 