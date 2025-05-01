import { Keypair, PublicKey, SystemProgram, Transaction } from '@solana/web3.js';
import { SolanaRpcClient, defaultSolanaRpcClient } from '../utils/solanaRpcClient';
import { FeeOracle, defaultFeeOracle } from '../fees/feeOracle';
import { SolNetworkError, TxTimeoutError } from '../utils/errors';
import { EventEmitter } from '../utils/eventEmitter';

/**
 * Event types that WalletFunder can emit
 */
export enum WalletFunderEvent {
  FUNDING_STARTED = 'funding_started',
  FUNDING_COMPLETED = 'funding_completed',
  FUNDING_FAILED = 'funding_failed',
  CHUNK_STARTED = 'chunk_started',
  CHUNK_COMPLETED = 'chunk_completed',
  TRANSACTION_SENT = 'transaction_sent',
  TRANSACTION_CONFIRMED = 'transaction_confirmed',
  TRANSACTION_FAILED = 'transaction_failed',
  RETRY_ATTEMPT = 'retry_attempt'
}

/**
 * Event payload types for WalletFunder events
 */
export interface WalletFunderEventPayloads {
  [WalletFunderEvent.FUNDING_STARTED]: {
    motherAddress: string;
    childCount: number;
    amountPerChild: bigint;
    totalAmount: bigint;
  };
  [WalletFunderEvent.FUNDING_COMPLETED]: FundingResult;
  [WalletFunderEvent.FUNDING_FAILED]: {
    error: Error | string;
    motherAddress?: string;
  };
  [WalletFunderEvent.CHUNK_STARTED]: {
    chunkIndex: number;
    addresses: string[];
    amountPerChild: bigint;
  };
  [WalletFunderEvent.CHUNK_COMPLETED]: {
    chunkIndex: number;
    success: boolean;
    addresses: string[];
    signature?: string;
    error?: string;
  };
  [WalletFunderEvent.TRANSACTION_SENT]: {
    signature: string;
    motherAddress: string;
    childAddresses: string[];
  };
  [WalletFunderEvent.TRANSACTION_CONFIRMED]: {
    signature: string;
    motherAddress: string;
    childAddresses: string[];
    confirmationTime: number;
    fee: bigint;
  };
  [WalletFunderEvent.TRANSACTION_FAILED]: {
    motherAddress: string;
    childAddresses: string[];
    error: Error;
    retryCount: number;
  };
  [WalletFunderEvent.RETRY_ATTEMPT]: {
    attempt: number;
    error?: string;
    motherAddress: string;
    childCount: number;
  };
}

/**
 * Interface for wallet funding options
 */
export interface WalletFundingOptions {
  skipPreflight?: boolean;
  maxRetries?: number;
  retryDelayMs?: number;
  confirmationTimeoutMs?: number;
  priorityFee?: bigint; // in micro-lamports
  maxChildrenPerChunk?: number; // Maximum number of children to fund in a single transaction
}

/**
 * Result of a funding operation
 */
export interface FundingResult {
  totalTransactions: number;
  successfulTransactions: number;
  failedTransactions: number;
  totalFundedAmount: bigint;
  totalFees: bigint;
  averageConfirmationTimeMs: number;
  startTime: number;
  endTime: number;
  fundedChildAddresses: string[];
  failedChildAddresses: string[];
}

// Default configuration for wallet funding
const DEFAULT_MAX_RETRIES = 3;
const DEFAULT_RETRY_DELAY_MS = 2000;
const DEFAULT_CONFIRMATION_TIMEOUT_MS = 60000; // 60 seconds
const DEFAULT_MAX_CHILDREN_PER_CHUNK = 5; // Maximum number of transfer instructions per transaction

/**
 * WalletFunder is responsible for funding child wallets from a mother wallet.
 * It handles chunking transfers, transaction building, sending, and confirmations.
 */
export class WalletFunder extends EventEmitter<WalletFunderEvent, WalletFunderEventPayloads> {
  private rpcClient: SolanaRpcClient;
  private feeOracle: FeeOracle;
  private maxRetries: number;
  private retryDelayMs: number;
  private confirmationTimeoutMs: number;
  private maxChildrenPerChunk: number;
  
  /**
   * Creates a new WalletFunder instance
   * 
   * @param rpcClient - Solana RPC client instance
   * @param feeOracle - Fee Oracle for determining optimal fees
   * @param maxRetries - Maximum number of retry attempts for failed transactions
   * @param retryDelayMs - Delay between retry attempts in milliseconds
   * @param confirmationTimeoutMs - Timeout for transaction confirmations in milliseconds
   * @param maxChildrenPerChunk - Maximum number of children to fund in a single transaction
   */
  constructor(
    rpcClient: SolanaRpcClient = defaultSolanaRpcClient,
    feeOracle: FeeOracle = defaultFeeOracle,
    maxRetries: number = DEFAULT_MAX_RETRIES,
    retryDelayMs: number = DEFAULT_RETRY_DELAY_MS,
    confirmationTimeoutMs: number = DEFAULT_CONFIRMATION_TIMEOUT_MS,
    maxChildrenPerChunk: number = DEFAULT_MAX_CHILDREN_PER_CHUNK
  ) {
    super();
    this.rpcClient = rpcClient;
    this.feeOracle = feeOracle;
    this.maxRetries = maxRetries;
    this.retryDelayMs = retryDelayMs;
    this.confirmationTimeoutMs = confirmationTimeoutMs;
    this.maxChildrenPerChunk = maxChildrenPerChunk;
  }

  /**
   * Fund multiple child wallets from a mother wallet
   * 
   * @param motherWallet - The mother wallet keypair to fund from
   * @param childAddresses - Array of child wallet addresses to fund
   * @param amountPerChild - Amount of SOL (in lamports) to fund each child wallet
   * @param options - Optional funding parameters
   * @returns A promise resolving to the funding result
   */
  async fundChildWallets(
    motherWallet: Keypair,
    childAddresses: string[],
    amountPerChild: bigint,
    options: WalletFundingOptions = {}
  ): Promise<FundingResult> {
    // Extract options with defaults
    const {
      skipPreflight = false,
      maxRetries = this.maxRetries,
      retryDelayMs = this.retryDelayMs,
      confirmationTimeoutMs = this.confirmationTimeoutMs,
      priorityFee,
      maxChildrenPerChunk = this.maxChildrenPerChunk
    } = options;

    // Initialize result
    const result: FundingResult = {
      totalTransactions: 0,
      successfulTransactions: 0,
      failedTransactions: 0,
      totalFundedAmount: 0n,
      totalFees: 0n,
      averageConfirmationTimeMs: 0,
      startTime: Date.now(),
      endTime: 0,
      fundedChildAddresses: [],
      failedChildAddresses: []
    };

    // Validate inputs
    if (!motherWallet || !motherWallet.publicKey) {
      throw new Error('Invalid mother wallet');
    }

    if (!childAddresses || childAddresses.length === 0) {
      throw new Error('No child addresses provided');
    }

    if (amountPerChild <= 0n) {
      throw new Error('Amount per child must be positive');
    }

    // Calculate total funding amount needed
    const totalFundingAmount = amountPerChild * BigInt(childAddresses.length);

    // Check if mother wallet has enough balance
    try {
      const motherBalance = await this.getWalletBalance(motherWallet.publicKey.toString());
      
      // We need to account for transaction fees too, estimate conservatively
      // Each transaction costs ~5000 lamports, and we'll have childAddresses.length / maxChildrenPerChunk transactions
      const estimatedTxCount = Math.ceil(childAddresses.length / maxChildrenPerChunk);
      const estimatedBaseFees = BigInt(estimatedTxCount * 5000);
      
      // Priority fees are additional - let's estimate based on current rates
      const estimatedPriorityFee = priorityFee || await this.feeOracle.getOptimalPriorityFee();
      // Compute units per transaction ~200k, multiplied by estimatedTxCount
      const estimatedPriorityFees = (estimatedPriorityFee * BigInt(200000) * BigInt(estimatedTxCount)) / 1000000n;
      
      const totalEstimatedCost = totalFundingAmount + estimatedBaseFees + estimatedPriorityFees;
      
      if (motherBalance < totalEstimatedCost) {
        throw new Error(`Insufficient balance in mother wallet. Available: ${motherBalance}, Required: ${totalEstimatedCost}`);
      }
    } catch (error) {
      if (error instanceof Error && error.message.includes('Insufficient balance')) {
        throw error; // Re-throw the insufficient balance error
      }
      throw new Error(`Failed to check mother wallet balance: ${error instanceof Error ? error.message : String(error)}`);
    }

    // Emit funding started event
    this.emit(WalletFunderEvent.FUNDING_STARTED, {
      motherAddress: motherWallet.publicKey.toString(),
      childCount: childAddresses.length,
      amountPerChild,
      totalAmount: totalFundingAmount
    });

    // Split child addresses into chunks
    const chunks: string[][] = [];
    for (let i = 0; i < childAddresses.length; i += maxChildrenPerChunk) {
      chunks.push(childAddresses.slice(i, i + maxChildrenPerChunk));
    }

    // Process each chunk
    let totalConfirmationTime = 0;
    let confirmedCount = 0;

    for (let chunkIndex = 0; chunkIndex < chunks.length; chunkIndex++) {
      const chunk = chunks[chunkIndex];
      
      // Emit chunk started event
      this.emit(WalletFunderEvent.CHUNK_STARTED, {
        chunkIndex,
        addresses: chunk,
        amountPerChild
      });

      try {
        // Fund the chunk
        const chunkResult = await this.fundChildWalletsChunk(
          motherWallet,
          chunk,
          amountPerChild,
          {
            skipPreflight,
            maxRetries,
            retryDelayMs,
            confirmationTimeoutMs,
            priorityFee
          }
        );

        // Update result statistics
        result.totalTransactions++;
        
        if (chunkResult.success) {
          result.successfulTransactions++;
          result.totalFundedAmount += amountPerChild * BigInt(chunk.length);
          result.totalFees += chunkResult.fee || 0n;
          result.fundedChildAddresses.push(...chunk);
          
          // Track confirmation time for average calculation
          if (chunkResult.confirmationTime) {
            totalConfirmationTime += chunkResult.confirmationTime;
            confirmedCount++;
          }
        } else {
          result.failedTransactions++;
          result.failedChildAddresses.push(...chunk);
        }

        // Emit chunk completed event
        this.emit(WalletFunderEvent.CHUNK_COMPLETED, {
          chunkIndex,
          success: chunkResult.success,
          addresses: chunk,
          signature: chunkResult.signature,
          error: chunkResult.error
        });

      } catch (error) {
        // If chunk fails, mark all addresses in the chunk as failed
        result.failedTransactions++;
        result.failedChildAddresses.push(...chunk);
        
        // Emit chunk failed event
        this.emit(WalletFunderEvent.CHUNK_COMPLETED, {
          chunkIndex,
          success: false,
          addresses: chunk,
          error: error instanceof Error ? error.message : String(error)
        });
      }
    }

    // Calculate average confirmation time
    result.averageConfirmationTimeMs = confirmedCount > 0 
      ? totalConfirmationTime / confirmedCount 
      : 0;
    
    // Set end time
    result.endTime = Date.now();

    // Emit funding completed event
    this.emit(WalletFunderEvent.FUNDING_COMPLETED, result);

    return result;
  }

  /**
   * Fund a chunk of child wallets from a mother wallet
   * 
   * @param motherWallet - The mother wallet keypair to fund from
   * @param childAddresses - Array of child wallet addresses to fund in this chunk
   * @param amountPerChild - Amount of SOL (in lamports) to fund each child wallet
   * @param options - Optional funding parameters
   * @returns A promise resolving to the chunk funding result
   */
  private async fundChildWalletsChunk(
    motherWallet: Keypair,
    childAddresses: string[],
    amountPerChild: bigint,
    options: WalletFundingOptions = {}
  ): Promise<{
    success: boolean;
    signature?: string;
    error?: string;
    fee?: bigint;
    confirmationTime?: number;
  }> {
    // Extract options with defaults
    const {
      skipPreflight = false,
      maxRetries = this.maxRetries,
      retryDelayMs = this.retryDelayMs,
      confirmationTimeoutMs = this.confirmationTimeoutMs,
      priorityFee
    } = options;

    let currentAttempt = 0;
    let lastError: Error | null = null;

    // Retry loop
    while (currentAttempt <= maxRetries) {
      try {
        // Only apply backoff delay after first attempt
        if (currentAttempt > 0) {
          await new Promise(resolve => setTimeout(resolve, retryDelayMs));
          this.emit(WalletFunderEvent.RETRY_ATTEMPT, { 
            attempt: currentAttempt, 
            error: lastError?.message,
            motherAddress: motherWallet.publicKey.toString(),
            childCount: childAddresses.length
          });
        }

        // Get latest blockhash for transaction
        const { blockhash, lastValidBlockHeight } = await this.rpcClient.getLatestBlockhash();

        // Create a new transaction
        const transaction = new Transaction({
          feePayer: motherWallet.publicKey,
          blockhash,
          lastValidBlockHeight: Number(lastValidBlockHeight)
        });

        // Add transfer instructions for each child wallet
        for (const childAddress of childAddresses) {
          // Convert string address to PublicKey
          const childPublicKey = new PublicKey(childAddress);
          
          // Add SOL transfer instruction
          transaction.add(
            SystemProgram.transfer({
              fromPubkey: motherWallet.publicKey,
              toPubkey: childPublicKey,
              lamports: amountPerChild
            })
          );
        }

        // Apply priority fee if provided or get optimal fee
        const actualPriorityFee = priorityFee || await this.feeOracle.getOptimalPriorityFee();
        if (actualPriorityFee > 0n) {
          // Set a computeBudget instruction for priority fees
          const ComputeBudgetProgram = await import('@solana/web3.js').then(m => m.ComputeBudgetProgram);
          transaction.add(
            ComputeBudgetProgram.setComputeUnitPrice({
              microLamports: Number(actualPriorityFee)
            })
          );
        }

        // Sign transaction
        transaction.sign(motherWallet);

        // Send transaction
        const txSignature = await this.rpcClient.sendTransaction(transaction, {
          skipPreflight,
          maxRetries: 1,
          preflightCommitment: 'confirmed'
        });

        if (!txSignature) {
          throw new SolNetworkError('Failed to send transaction: Empty signature returned');
        }

        // Emit transaction sent event
        this.emit(WalletFunderEvent.TRANSACTION_SENT, { 
          signature: txSignature, 
          motherAddress: motherWallet.publicKey.toString(),
          childAddresses
        });

        // Record transaction start time
        const confirmStartTime = Date.now();

        // Wait for confirmation with timeout
        const confirmationPromise = this.rpcClient.confirmTransaction(
          { signature: txSignature, blockhash, lastValidBlockHeight: Number(lastValidBlockHeight) },
          'confirmed'
        );
        
        const timeoutPromise = new Promise<null>((resolve) => 
          setTimeout(() => resolve(null), confirmationTimeoutMs)
        );
        
        const confirmationResult = await Promise.race([confirmationPromise, timeoutPromise]);

        // Check for timeout
        if (confirmationResult === null) {
          throw new TxTimeoutError(`Transaction confirmation timeout after ${confirmationTimeoutMs}ms`);
        }

        // Check confirmation status
        if (!confirmationResult || confirmationResult.value?.err) {
          throw new Error(`Transaction failed: ${JSON.stringify(confirmationResult?.value?.err)}`);
        }

        // Calculate confirmation time
        const confirmationTime = Date.now() - confirmStartTime;

        // Get transaction fee from the transaction response
        let fee: bigint = 0n;
        try {
          const txResponse = await this.rpcClient.connection.getTransaction(
            txSignature,
            { commitment: 'confirmed', maxSupportedTransactionVersion: 0 }
          );
          
          if (txResponse?.meta?.fee) {
            fee = BigInt(txResponse.meta.fee);
          }
        } catch (error) {
          console.warn('Could not fetch transaction fee:', error);
          // Continue anyway as this is non-critical
        }

        // Emit confirmation event
        this.emit(WalletFunderEvent.TRANSACTION_CONFIRMED, { 
          signature: txSignature, 
          motherAddress: motherWallet.publicKey.toString(),
          childAddresses,
          confirmationTime,
          fee
        });

        // Return success
        return {
          success: true,
          signature: txSignature,
          fee,
          confirmationTime
        };

      } catch (error) {
        lastError = error instanceof Error ? error : new Error(String(error));
        
        // Check if this is a retryable error
        const isRetryable = this.isRetryableError(lastError);
        
        // If we've exhausted retries or error isn't retryable, fail permanently
        if (currentAttempt >= maxRetries || !isRetryable) {
          // Emit transaction failed event
          this.emit(WalletFunderEvent.TRANSACTION_FAILED, { 
            motherAddress: motherWallet.publicKey.toString(),
            childAddresses,
            error: lastError,
            retryCount: currentAttempt
          });
          
          // Return failure
          return {
            success: false,
            error: lastError.message
          };
        }
        
        // Increment attempt counter for next iteration
        currentAttempt++;
      }
    }

    // This should never be reached, but TypeScript requires a return
    return {
      success: false,
      error: 'Exhausted all retry attempts'
    };
  }

  /**
   * Get the balance of a wallet in lamports
   * 
   * @param address - The wallet address to check
   * @returns The balance in lamports
   */
  private async getWalletBalance(address: string): Promise<bigint> {
    try {
      const response = await this.rpcClient.getBalance(address);
      return BigInt(response.value);
    } catch (error) {
      throw new Error(`Failed to get wallet balance: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  /**
   * Determine if an error is retryable based on its type and message
   * 
   * @param error - The error to check
   * @returns True if the error is retryable, false otherwise
   */
  private isRetryableError(error: Error): boolean {
    // Network errors and timeouts are retryable
    if (error instanceof SolNetworkError || error instanceof TxTimeoutError) {
      return true;
    }

    // Check error message for known retryable patterns
    const retryablePatterns = [
      'timeout',
      'timed out',
      'rate limit',
      'network error',
      'connection error',
      'socket hang up',
      'blockhash not found',
      'block height exceeded',
      'dropped'
    ];

    const errorMsg = error.message.toLowerCase();
    return retryablePatterns.some(pattern => errorMsg.includes(pattern));
  }
}

/**
 * Create and export a default instance of WalletFunder
 */
export const defaultWalletFunder = new WalletFunder();

/**
 * Convenience function to create a new WalletFunder instance
 * 
 * @param rpcClient - Solana RPC client instance
 * @param feeOracle - Fee Oracle for determining optimal fees
 * @param maxRetries - Maximum number of retry attempts for failed transactions
 * @param retryDelayMs - Delay between retry attempts in milliseconds
 * @param confirmationTimeoutMs - Timeout for transaction confirmations in milliseconds
 * @param maxChildrenPerChunk - Maximum number of children to fund in a single transaction
 * @returns A new WalletFunder instance
 */
export function createWalletFunder(
  rpcClient?: SolanaRpcClient,
  feeOracle?: FeeOracle,
  maxRetries?: number,
  retryDelayMs?: number,
  confirmationTimeoutMs?: number,
  maxChildrenPerChunk?: number
): WalletFunder {
  return new WalletFunder(
    rpcClient,
    feeOracle,
    maxRetries,
    retryDelayMs,
    confirmationTimeoutMs,
    maxChildrenPerChunk
  );
} 