/**
 * Common types and interfaces used throughout the application
 */

/**
 * Represents a transfer operation from one wallet to another
 */
export interface TransferOp {
  sourceIndex: number;
  destinationIndex: number;
  amount: bigint;
}

/**
 * Detailed transfer operation with fee information
 */
export interface DetailedTransferOp {
  sourceIndex: number;
  destinationAddress: string;
  amount: bigint;
  isFee: boolean;
}

/**
 * Operation status after execution
 */
export enum OperationStatus {
  PENDING = 'pending',
  CONFIRMED = 'confirmed',
  FAILED = 'failed',
  SKIPPED = 'skipped'
}

/**
 * Result of an attempted transfer operation
 */
export interface OperationResult {
  opIndex: number;
  status: OperationStatus;
  signature?: string;
  error?: string;
  confirmationTime?: number; // milliseconds
}

/**
 * Summary of a completed run
 */
export interface RunSummary {
  networkType: 'devnet' | 'mainnet';
  totalOperations: number;
  confirmedOperations: number;
  failedOperations: number;
  skippedOperations: number;
  totalAmount: bigint;
  totalFees: bigint;
  feesCollected: bigint;
  averageConfirmationTimeMs: number;
  startTime: number; // timestamp
  endTime: number; // timestamp
  results: OperationResult[];
} 