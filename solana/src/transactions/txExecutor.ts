/**
 * TxExecutor - Transaction Execution Module for Solana
 * 
 * This module handles the execution of Solana transactions including:
 * - SOL transfers
 * - SPL token transfers
 * - Fee spike detection
 * - Retry mechanisms for failed transactions
 * 
 * It uses web3.js v2, which has significant API differences from v1.
 */

import { 
  DetailedTransferOp, 
  OperationResult, 
  OperationStatus 
} from '../models/types';
import { SolanaRpcClient, defaultSolanaRpcClient } from '../utils/solanaRpcClient';
import { FeeOracle, defaultFeeOracle } from '../fees/feeOracle';
import { TokenInfo, TokenNotFoundError } from '../tokens/tokenInfo';
import { getWalletFromIndex } from '../wallet/walletManager';
import { WalletSignatureError } from '../wallet/errors';
import { 
  SolNetworkError, 
  InvalidInstructionParameterError,
  TransactionCreationError 
} from '../utils/errors';
import { EventEmitter } from '../utils/eventEmitter';
import { getConfig } from '../config';
import {
  isTransactionConfirmationResponse,
  isTokenAccountsByOwnerResponse
} from '../utils/rpcTypes';

// Import web3.js v1 modules
import { 
  PublicKey,
  Keypair,
  SystemProgram,
  Transaction,
  TransactionInstruction,
  ComputeBudgetProgram
} from '@solana/web3.js';
import { 
  createTransferCheckedInstruction 
} from '@solana/spl-token';

// Default configuration for transaction execution
const DEFAULT_MAX_RETRIES = 3;
const DEFAULT_RETRY_DELAY_MS = 2000;
const DEFAULT_CONFIRMATION_TIMEOUT_MS = 60000; // 60 seconds

/**
 * Event types that TxExecutor can emit
 */
export enum TxExecutorEvent {
  TRANSACTION_SENT = 'transaction_sent',
  TRANSACTION_CONFIRMED = 'transaction_confirmed',
  TRANSACTION_FAILED = 'transaction_failed',
  RETRY_ATTEMPT = 'retry_attempt',
  FEE_SPIKE_DETECTED = 'fee_spike_detected'
}

/**
 * Payload types for different TxExecutor events
 */
export interface TxExecutorEventPayloads {
  [TxExecutorEvent.TRANSACTION_SENT]: { 
    signature: string; 
    operation: DetailedTransferOp;
  };
  [TxExecutorEvent.TRANSACTION_CONFIRMED]: { 
    signature: string; 
    operation: DetailedTransferOp;
    confirmationTime: number;
  };
  [TxExecutorEvent.TRANSACTION_FAILED]: { 
    operation: DetailedTransferOp;
    error: Error;
    retryCount: number;
    signature?: string;
  };
  [TxExecutorEvent.RETRY_ATTEMPT]: { 
    operation: DetailedTransferOp;
    attempt: number;
    error: string;
  };
  [TxExecutorEvent.FEE_SPIKE_DETECTED]: {
    operation: DetailedTransferOp;
    currentFee: bigint;
    thresholdFee: bigint;
  };
}

/**
 * Interface for transaction execution options
 */
export interface TxExecuteOptions {
  skipPreflight?: boolean;
  maxRetries?: number;
  retryDelayMs?: number;
  confirmationTimeoutMs?: number;
  priorityFee?: bigint; // in micro-lamports
  dryRun?: boolean;
  checkFeeSpikeThreshold?: boolean;
}

/**
 * Helper function to convert a Uint8Array to base64 string
 */
function bufferToBase64(buffer: Uint8Array): string {
  return Buffer.from(buffer).toString('base64');
}

/**
 * TxExecutor is responsible for executing Solana transactions with retry logic,
 * handling signatures, and monitoring transaction confirmations.
 */
export class TxExecutor extends EventEmitter<TxExecutorEvent, TxExecutorEventPayloads> {
  private rpcClient: SolanaRpcClient;
  private feeOracle: FeeOracle;
  private tokenInfo: TokenInfo;
  private maxRetries: number;
  private retryDelayMs: number;
  private confirmationTimeoutMs: number;
  
  /**
   * Creates a new TxExecutor instance
   * 
   * @param rpcClient - Solana RPC client instance
   * @param feeOracle - Fee Oracle for determining optimal fees
   * @param tokenInfo - Token information service
   * @param maxRetries - Maximum number of retry attempts for failed transactions
   * @param retryDelayMs - Delay between retry attempts in milliseconds
   * @param confirmationTimeoutMs - Timeout for transaction confirmations in milliseconds
   */
  constructor(
    rpcClient: SolanaRpcClient = defaultSolanaRpcClient,
    feeOracle: FeeOracle = defaultFeeOracle,
    tokenInfo = new TokenInfo(),
    maxRetries: number = DEFAULT_MAX_RETRIES,
    retryDelayMs: number = DEFAULT_RETRY_DELAY_MS,
    confirmationTimeoutMs: number = DEFAULT_CONFIRMATION_TIMEOUT_MS
  ) {
    super();
    this.rpcClient = rpcClient;
    this.feeOracle = feeOracle;
    this.tokenInfo = tokenInfo;
    this.maxRetries = maxRetries;
    this.retryDelayMs = retryDelayMs;
    this.confirmationTimeoutMs = confirmationTimeoutMs;
  }

  /**
   * Execute a SOL transfer operation
   * 
   * @param operation - The detailed transfer operation to execute
   * @param options - Optional execution parameters
   * @returns The operation result including status and signature
   */
  async executeSolTransfer(
    operation: DetailedTransferOp,
    options: TxExecuteOptions = {}
  ): Promise<OperationResult> {
    // Extract options with defaults
    const {
      skipPreflight = false,
      maxRetries = this.maxRetries,
      retryDelayMs = this.retryDelayMs,
      confirmationTimeoutMs = this.confirmationTimeoutMs,
      priorityFee,
      dryRun = false,
      checkFeeSpikeThreshold = true
    } = options;

    // Initialize result with pending status
    const result: OperationResult = {
      opIndex: operation.sourceIndex,
      status: OperationStatus.PENDING
    };

    // Skip actual execution in dry run mode
    if (dryRun) {
      result.status = OperationStatus.SKIPPED;
      result.signature = 'DRY_RUN_MODE';
      return result;
    }

    // Load the source wallet
    const sourceWallet = await getWalletFromIndex(operation.sourceIndex);
    if (!sourceWallet) {
      result.status = OperationStatus.FAILED;
      result.error = `Failed to load source wallet at index ${operation.sourceIndex}`;
      return result;
    }

    let currentAttempt = 0;
    let lastError: Error | null = null;

    // Retry loop
    while (currentAttempt <= maxRetries) {
      try {
        // Only apply backoff delay after first attempt
        if (currentAttempt > 0) {
          await new Promise(resolve => setTimeout(resolve, retryDelayMs));
          this.emit(TxExecutorEvent.RETRY_ATTEMPT, { 
            operation, 
            attempt: currentAttempt, 
            error: lastError?.message || 'Unknown error'
          });
        }

        // Get latest blockhash for transaction
        const blockHashResponse = await this.rpcClient.getLatestBlockhash();
        const { blockhash, lastValidBlockHeight } = blockHashResponse;

        // Get optimal priority fee
        const actualPriorityFee = priorityFee || await this.feeOracle.getOptimalPriorityFee();
        
        // Check for fee spikes if enabled
        if (checkFeeSpikeThreshold) {
          const thresholdFee = await this.feeOracle.getFeeSpikeThreshold();
          if (actualPriorityFee > thresholdFee) {
            // Emit fee spike event
            this.emit(TxExecutorEvent.FEE_SPIKE_DETECTED, {
              operation,
              currentFee: actualPriorityFee,
              thresholdFee
            });
            
            // Update result with skipped status
            result.status = OperationStatus.SKIPPED;
            result.error = `Fee spike detected: current fee ${actualPriorityFee} > threshold ${thresholdFee}`;
            return result;
          }
        }

        // Create transaction message to construct a v0 transaction
        const instructions = [];

        // Add priority fee instruction if needed
        if (actualPriorityFee > 0n) {
          const priorityFeeInstruction = ComputeBudgetProgram.setComputeUnitPrice({
            microLamports: actualPriorityFee
          });
          instructions.push(priorityFeeInstruction);
        }
        
        // Add SOL transfer instruction
        const sourceAddress = new PublicKey(sourceWallet.publicKey.toString());
        const destinationAddress = new PublicKey(operation.destinationAddress);
        
        const transferInstruction = SystemProgram.transfer({
          fromPubkey: sourceAddress,
          toPubkey: destinationAddress,
          lamports: operation.amount
        });
        
        instructions.push(transferInstruction);

        // Build the transaction
        const transaction = new Transaction().add(...instructions);
        transaction.feePayer = sourceAddress;
        transaction.recentBlockhash = blockhash;
        
        // Sign transaction with source wallet (convert to Keypair if needed)
        const signers = [sourceWallet];
        transaction.sign(...signers as unknown as Keypair[]);
        
        // Get signature from transaction
        const txSignature = await this.rpcClient.connection.sendRawTransaction(
          transaction.serialize(),
          {
            skipPreflight,
            preflightCommitment: 'confirmed'
          }
        );

        // Emit transaction sent event
        this.emit(TxExecutorEvent.TRANSACTION_SENT, { 
          signature: txSignature, 
          operation 
        });

        // Record transaction start time
        const confirmStartTime = Date.now();

        // Wait for confirmation with timeout
        const confirmationPromise = new Promise<any>((resolve, reject) => {
          // Use the standard Connection.confirmTransaction method instead of WebSockets
          this.rpcClient.connection.confirmTransaction(
            {
              signature: txSignature,
              lastValidBlockHeight,
              blockhash
            },
            'confirmed'
          ).then(resolve).catch(reject);
        });
        
        const timeoutPromise = new Promise<null>((resolve) => 
          setTimeout(() => resolve(null), confirmationTimeoutMs)
        );
        
        const confirmationResult = await Promise.race([confirmationPromise, timeoutPromise]);
        
        // Check for timeout
        if (confirmationResult === null) {
          throw new Error(`Transaction confirmation timeout after ${confirmationTimeoutMs}ms`);
        }

        // Check confirmation status (format is different in v1)
        if (confirmationResult.value && confirmationResult.value.err) {
          throw new Error(`Transaction failed: ${JSON.stringify(confirmationResult.value.err)}`);
        }

        // Calculate confirmation time
        const confirmationTime = Date.now() - confirmStartTime;

        // Update result with success
        result.status = OperationStatus.CONFIRMED;
        result.signature = txSignature;
        result.confirmationTime = confirmationTime;

        // Emit confirmation event
        this.emit(TxExecutorEvent.TRANSACTION_CONFIRMED, { 
          signature: txSignature, 
          operation,
          confirmationTime
        });

        return result;

      } catch (error) {
        lastError = error instanceof Error ? error : new Error(String(error));
        
        // Log detailed information about the error
        console.error(`Transaction error details:`, {
          message: lastError.message,
          stack: lastError.stack,
          operation: {
            sourceIndex: operation.sourceIndex,
            destinationAddress: operation.destinationAddress,
            amount: operation.amount.toString()
          }
        });
        
        // Check if this is a retryable error
        const isRetryable = this.isRetryableError(lastError);
        
        // If we've exhausted retries or error isn't retryable, fail permanently
        if (currentAttempt >= maxRetries || !isRetryable) {
          result.status = OperationStatus.FAILED;
          result.error = lastError.message;
          
          this.emit(TxExecutorEvent.TRANSACTION_FAILED, { 
            operation, 
            error: lastError,
            retryCount: currentAttempt
          });
          
          return result;
        }
        
        // Increment attempt counter for next iteration
        currentAttempt++;
      }
    }

    // This should never be reached, but TypeScript requires a return
    result.status = OperationStatus.FAILED;
    result.error = 'Exhausted all retry attempts';
    return result;
  }

  /**
   * Execute a token transfer operation (SPL token)
   * 
   * @param operation - The detailed transfer operation to execute
   * @param tokenMint - The mint address of the token
   * @param options - Optional execution parameters
   * @returns The operation result including status and signature
   */
  async executeTokenTransfer(
    operation: DetailedTransferOp,
    tokenMint: string,
    options: TxExecuteOptions = {}
  ): Promise<OperationResult> {
    // Extract options with defaults
    const {
      skipPreflight = false,
      maxRetries = this.maxRetries,
      retryDelayMs = this.retryDelayMs,
      confirmationTimeoutMs = this.confirmationTimeoutMs,
      priorityFee,
      dryRun = false,
      checkFeeSpikeThreshold = true
    } = options;

    // Initialize result with pending status
    const result: OperationResult = {
      opIndex: operation.sourceIndex,
      status: OperationStatus.PENDING
    };

    // Skip actual execution in dry run mode
    if (dryRun) {
      result.status = OperationStatus.SKIPPED;
      result.signature = 'DRY_RUN_MODE';
      return result;
    }

    // Load the source wallet
    const sourceWallet = await getWalletFromIndex(operation.sourceIndex);
    if (!sourceWallet) {
      result.status = OperationStatus.FAILED;
      result.error = `Failed to load source wallet at index ${operation.sourceIndex}`;
      return result;
    }

    // Get token information
    let tokenDecimals: number;
    try {
      const tokenData = await this.tokenInfo.getTokenData(tokenMint);
      tokenDecimals = tokenData.decimals;
    } catch (error) {
      if (error instanceof TokenNotFoundError) {
        result.status = OperationStatus.FAILED;
        result.error = `Invalid token mint address: ${tokenMint}`;
        return result;
      }
      throw error;
    }

    let currentAttempt = 0;
    let lastError: Error | null = null;

    // Retry loop
    while (currentAttempt <= maxRetries) {
      try {
        // Only apply backoff delay after first attempt
        if (currentAttempt > 0) {
          await new Promise(resolve => setTimeout(resolve, retryDelayMs));
          this.emit(TxExecutorEvent.RETRY_ATTEMPT, { 
            operation, 
            attempt: currentAttempt, 
            error: lastError?.message || 'Unknown error'
          });
        }

        // Get source token account
        const sourceTokenAccountsResponse = await this.rpcClient.getTokenAccountsByOwner(
          sourceWallet.publicKey.toString(),
          { mint: tokenMint },
          { encoding: 'jsonParsed' }
        );

        // Validate token accounts response
        if (!isTokenAccountsByOwnerResponse(sourceTokenAccountsResponse) || 
            sourceTokenAccountsResponse.value.length === 0) {
          throw new Error(`Source wallet has no token account for mint ${tokenMint}`);
        }

        const sourceTokenAccount = sourceTokenAccountsResponse.value[0].pubkey;

        // Get or create destination token account
        const destinationTokenAccountsResponse = await this.rpcClient.getTokenAccountsByOwner(
          operation.destinationAddress,
          { mint: tokenMint },
          { encoding: 'jsonParsed' }
        );

        // Validate destination token accounts response
        if (!isTokenAccountsByOwnerResponse(destinationTokenAccountsResponse) || 
            destinationTokenAccountsResponse.value.length === 0) {
          throw new Error(`Destination wallet has no token account for mint ${tokenMint}`);
        }

        const destinationTokenAccount = destinationTokenAccountsResponse.value[0].pubkey;

        // Get latest blockhash for transaction
        const blockHashResponse = await this.rpcClient.getLatestBlockhash();
        const { blockhash, lastValidBlockHeight } = blockHashResponse;

        // Get optimal priority fee
        const actualPriorityFee = priorityFee || await this.feeOracle.getOptimalPriorityFee();
        
        // Check for fee spikes if enabled
        if (checkFeeSpikeThreshold) {
          const thresholdFee = await this.feeOracle.getFeeSpikeThreshold();
          if (actualPriorityFee > thresholdFee) {
            // Emit fee spike event
            this.emit(TxExecutorEvent.FEE_SPIKE_DETECTED, {
              operation,
              currentFee: actualPriorityFee,
              thresholdFee
            });
            
            // Update result with skipped status
            result.status = OperationStatus.SKIPPED;
            result.error = `Fee spike detected: current fee ${actualPriorityFee} > threshold ${thresholdFee}`;
            return result;
          }
        }

        // Create array to hold instructions
        const instructions = [];
        
        // Add priority fee instruction if needed
        if (actualPriorityFee > 0n) {
          const priorityFeeInstruction = ComputeBudgetProgram.setComputeUnitPrice({
            microLamports: actualPriorityFee
          });
          instructions.push(priorityFeeInstruction);
        }
        
        // For SPL token transfers, we need to use Token Program instructions
        const sourceAddress = new PublicKey(sourceWallet.publicKey.toString());
        const tokenMintPubkey = new PublicKey(tokenMint);
        const sourceTokenAccountPubkey = new PublicKey(sourceTokenAccount);
        const destinationTokenAccountPubkey = new PublicKey(destinationTokenAccount);
        
        // Add SPL token transfer instruction
        const transferInstruction = createTransferCheckedInstruction(
          sourceTokenAccountPubkey,
          tokenMintPubkey,
          destinationTokenAccountPubkey,
          sourceAddress,
          operation.amount,
          tokenDecimals
        );
        
        instructions.push(transferInstruction);
        
        // Build the transaction
        const transaction = new Transaction().add(...instructions);
        transaction.feePayer = sourceAddress;
        transaction.recentBlockhash = blockhash;
        
        // Sign transaction with source wallet (convert to Keypair if needed)
        const signers = [sourceWallet];
        transaction.sign(...signers as unknown as Keypair[]);
        
        // Get signature from transaction
        const txSignature = await this.rpcClient.connection.sendRawTransaction(
          transaction.serialize(),
          {
            skipPreflight,
            preflightCommitment: 'confirmed'
          }
        );

        // Emit transaction sent event
        this.emit(TxExecutorEvent.TRANSACTION_SENT, { 
          signature: txSignature, 
          operation 
        });

        // Record transaction start time
        const confirmStartTime = Date.now();

        // Wait for confirmation with timeout
        const confirmationPromise = new Promise<any>((resolve, reject) => {
          // Use the standard Connection.confirmTransaction method instead of WebSockets
          this.rpcClient.connection.confirmTransaction(
            {
              signature: txSignature,
              lastValidBlockHeight,
              blockhash
            },
            'confirmed'
          ).then(resolve).catch(reject);
        });
        
        const timeoutPromise = new Promise<null>((resolve) => 
          setTimeout(() => resolve(null), confirmationTimeoutMs)
        );
        
        const confirmationResult = await Promise.race([confirmationPromise, timeoutPromise]);
        
        // Check for timeout
        if (confirmationResult === null) {
          throw new Error(`Transaction confirmation timeout after ${confirmationTimeoutMs}ms`);
        }

        // Check confirmation status (format is different in v1)
        if (confirmationResult.value && confirmationResult.value.err) {
          throw new Error(`Transaction failed: ${JSON.stringify(confirmationResult.value.err)}`);
        }

        // Calculate confirmation time
        const confirmationTime = Date.now() - confirmStartTime;

        // Update result with success
        result.status = OperationStatus.CONFIRMED;
        result.signature = txSignature;
        result.confirmationTime = confirmationTime;

        // Emit confirmation event
        this.emit(TxExecutorEvent.TRANSACTION_CONFIRMED, { 
          signature: txSignature, 
          operation,
          confirmationTime
        });

        return result;

      } catch (error) {
        lastError = error instanceof Error ? error : new Error(String(error));
        
        // Log detailed information about the error
        console.error(`Transaction error details:`, {
          message: lastError.message,
          stack: lastError.stack,
          operation: {
            sourceIndex: operation.sourceIndex,
            destinationAddress: operation.destinationAddress,
            amount: operation.amount.toString()
          }
        });
        
        // Check if this is a retryable error
        const isRetryable = this.isRetryableError(lastError);
        
        // If we've exhausted retries or error isn't retryable, fail permanently
        if (currentAttempt >= maxRetries || !isRetryable) {
          result.status = OperationStatus.FAILED;
          result.error = lastError.message;
          
          this.emit(TxExecutorEvent.TRANSACTION_FAILED, { 
            operation, 
            error: lastError,
            retryCount: currentAttempt
          });
          
          return result;
        }
        
        // Increment attempt counter for next iteration
        currentAttempt++;
      }
    }

    // This should never be reached, but TypeScript requires a return
    result.status = OperationStatus.FAILED;
    result.error = 'Exhausted all retry attempts';
    return result;
  }

  /**
   * Determine if an error is retryable
   * 
   * @param error - The error to check
   * @returns True if the error is retryable
   */
  private isRetryableError(error: Error): boolean {
    // Wallet signature errors are not retryable
    if (error instanceof WalletSignatureError) {
      return false;
    }
    
    // Network errors are generally retryable
    if (error instanceof SolNetworkError) {
      return true;
    }
    
    // Check error message for common retryable errors
    const errorMessage = error.message.toLowerCase();
    
    // Transaction confirmation timeout is retryable
    if (errorMessage.includes('timeout')) {
      return true;
    }
    
    // Block height errors are retryable
    if (errorMessage.includes('blockhash') || errorMessage.includes('block height')) {
      return true;
    }
    
    // Various network-related errors
    if (
      errorMessage.includes('network') || 
      errorMessage.includes('connection') || 
      errorMessage.includes('socket') ||
      errorMessage.includes('rate limit') ||
      errorMessage.includes('429') // HTTP 429 Too Many Requests
    ) {
      return true;
    }
    
    // Some in-chain errors may be retryable
    if (
      errorMessage.includes('already processed') ||
      errorMessage.includes('slot skipped') ||
      errorMessage.includes('cluster maintenance')
    ) {
      return true;
    }
    
    // Non-retryable errors specific to transactions
    if (
      errorMessage.includes('insufficient funds') ||
      errorMessage.includes('invalid') || // Invalid account, parameter, etc.
      errorMessage.includes('custom program error')
    ) {
      return false;
    }
    
    // Default to non-retryable for safety
    return false;
  }

  /**
   * Execute a batch of operations
   * 
   * @param operations - List of operations to execute
   * @param tokenMint - Optional token mint address if these are token transfers
   * @param options - Transaction execution options
   * @returns Array of operation results
   */
  async executeBatch(
    operations: DetailedTransferOp[],
    tokenMint?: string,
    options: TxExecuteOptions = {}
  ): Promise<OperationResult[]> {
    const results: OperationResult[] = [];
    const config = getConfig();
    const continueOnError = config.continueOnError === true;
    
    for (const operation of operations) {
      let result: OperationResult;
      
      if (tokenMint) {
        // Token transfer
        result = await this.executeTokenTransfer(operation, tokenMint, options);
      } else {
        // SOL transfer
        result = await this.executeSolTransfer(operation, options);
      }
      
      results.push(result);
      
      // Check if we should abort the batch on critical errors
      if (result.status === OperationStatus.FAILED && !continueOnError) {
        if (result.error && this.shouldAbortBatch(result.error)) {
          console.error(`Aborting batch due to critical error: ${result.error}`);
          break;
        }
      }
    }
    
    return results;
  }
  
  /**
   * Determine if a batch should be aborted based on an error message
   * 
   * @param errorMessage - The error message to check
   * @returns True if the batch should be aborted
   */
  private shouldAbortBatch(errorMessage: string): boolean {
    const criticalErrors = [
      'insufficient funds',
      'invalid wallet',
      'account does not exist',
      'unauthorized',
      'account does not have enough SOL',
      'SolTransferLimitReached'
    ];
    
    const lowerCaseError = errorMessage.toLowerCase();
    return criticalErrors.some(phrase => lowerCaseError.includes(phrase.toLowerCase()));
  }
}

/**
 * Create and export a default instance of TxExecutor
 */
export const defaultTxExecutor = new TxExecutor();

/**
 * Convenience function to create a new TxExecutor instance
 * 
 * @param rpcClient - Solana RPC client instance
 * @param feeOracle - Fee Oracle for determining optimal fees
 * @param tokenInfo - Token information service
 * @param maxRetries - Maximum number of retry attempts for failed transactions
 * @param retryDelayMs - Delay between retry attempts in milliseconds
 * @param confirmationTimeoutMs - Timeout for transaction confirmations in milliseconds
 * @returns A new TxExecutor instance
 */
export function createTxExecutor(
  rpcClient?: SolanaRpcClient,
  feeOracle?: FeeOracle,
  tokenInfo?: TokenInfo,
  maxRetries?: number,
  retryDelayMs?: number,
  confirmationTimeoutMs?: number
): TxExecutor {
  return new TxExecutor(
    rpcClient,
    feeOracle,
    tokenInfo,
    maxRetries,
    retryDelayMs,
    confirmationTimeoutMs
  );
} 