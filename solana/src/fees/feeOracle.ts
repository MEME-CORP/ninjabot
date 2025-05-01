import { defaultSolanaRpcClient, SolanaRpcClient } from '../utils/solanaRpcClient';
import { PrioritizationFeesResponse, isPrioritizationFeesResponse } from '../utils/rpcTypes';

/**
 * Default increase factor for fee spike threshold calculation
 * We set the threshold at 150% of the current P90 fee
 */
const DEFAULT_THRESHOLD_FACTOR = 150n;
const DEFAULT_PERCENTILE = 90; // P90 for prioritization fees

/**
 * Interface for prioritization fee item returned by the RPC
 */
interface PrioritizationFeeItem {
  slot: number;
  prioritizationFee: number;
}

/**
 * FeeOracle is responsible for determining optimal priority fees 
 * and detecting fee spikes in the Solana network.
 */
export class FeeOracle {
  private rpcClient: SolanaRpcClient;
  private thresholdFactor: bigint;
  private percentile: number;

  /**
   * Creates a new FeeOracle
   * 
   * @param rpcClient - Solana RPC client instance
   * @param thresholdFactor - Factor to multiply the base fee by to determine spike threshold (150 = 1.5x)
   * @param percentile - Percentile to use for the prioritization fee analysis (0-100)
   */
  constructor(
    rpcClient: SolanaRpcClient = defaultSolanaRpcClient,
    thresholdFactor: bigint = DEFAULT_THRESHOLD_FACTOR,
    percentile: number = DEFAULT_PERCENTILE
  ) {
    this.rpcClient = rpcClient;
    this.thresholdFactor = thresholdFactor;
    
    if (percentile < 0 || percentile > 100) {
      throw new Error('Percentile must be between 0 and 100');
    }
    this.percentile = percentile;
  }

  /**
   * Gets the current recommended priority fee in micro-lamports per compute unit
   * 
   * @returns The recommended fee in micro-lamports
   */
  async getCurrentPriorityFee(): Promise<bigint> {
    try {
      // Get recent prioritization fees from the network
      const response = await this.rpcClient.getRecentPrioritizationFees();
      
      // Use type guard to validate response format
      if (isPrioritizationFeesResponse(response)) {
        const fees = response.value;
        
        if (fees.length === 0) {
          // If no data available, return a reasonable default (5000 micro-lamports)
          console.warn('No recent prioritization fees available, using default value');
          return 5000n;
        }

        // Extract just the prioritizationFee values from each slot's data
        const allFees = fees.map(item => Number(item.prioritizationFee));
        
        if (allFees.length === 0) {
          console.warn('No prioritization fees in result, using default value');
          return 5000n;
        }

        // Calculate the requested percentile fee
        const sortedFees = [...allFees].sort((a, b) => a - b);
        const index = Math.ceil((this.percentile / 100) * sortedFees.length) - 1;
        const clampedIndex = Math.max(0, Math.min(sortedFees.length - 1, index));
        
        return BigInt(sortedFees[clampedIndex]);
      } else {
        console.warn('Invalid response from getRecentPrioritizationFees, using default value', response);
        return 5000n;
      }
    } catch (error) {
      console.error('Error fetching priority fees:', error);
      // Return a reasonable default in case of error
      return 5000n;
    }
  }

  /**
   * Calculates the fee spike threshold based on current network conditions
   * A fee spike is detected when the current priority fee exceeds this threshold
   * 
   * @returns The threshold in micro-lamports per compute unit
   */
  async getFeeSpikeThreshold(): Promise<bigint> {
    const currentFee = await this.getCurrentPriorityFee();
    // Calculate threshold with a safety margin (e.g., 1.5x current fee)
    const threshold = (currentFee * this.thresholdFactor) / 100n;
    return threshold;
  }

  /**
   * Checks if the current priority fee constitutes a fee spike
   * 
   * @param currentFee - The current priority fee to check
   * @returns Promise resolving to true if there's a fee spike, false otherwise
   */
  async isFeeSpikeDetected(currentFee: bigint): Promise<boolean> {
    const threshold = await this.getFeeSpikeThreshold();
    return currentFee > threshold;
  }

  /**
   * Gets the optimal priority fee to use for a transaction
   * This balances transaction success probability with cost
   * 
   * @returns The optimal fee in micro-lamports per compute unit
   */
  async getOptimalPriorityFee(): Promise<bigint> {
    // For optimal fee, we use a slightly higher percentile to ensure transaction inclusion
    // but not as high as the spike threshold
    const currentFee = await this.getCurrentPriorityFee();
    // Use 120% of the current fee as the optimal fee (lower than the 150% spike threshold)
    return (currentFee * 120n) / 100n;
  }
}

/**
 * Create and export a default instance of FeeOracle
 */
export const defaultFeeOracle = new FeeOracle();

/**
 * Convenience function to create a new FeeOracle instance
 * 
 * @param rpcClient - Solana RPC client instance
 * @param thresholdFactor - Factor to multiply the base fee by to determine spike threshold (150 = 1.5x)
 * @param percentile - Percentile to use for the prioritization fee analysis (0-100)
 * @returns A new FeeOracle instance
 */
export function createFeeOracle(
  rpcClient?: SolanaRpcClient,
  thresholdFactor?: bigint,
  percentile?: number
): FeeOracle {
  return new FeeOracle(rpcClient, thresholdFactor, percentile);
} 