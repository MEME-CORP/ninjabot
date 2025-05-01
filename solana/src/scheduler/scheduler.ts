import { TransferOp } from '../models/types';

/**
 * Scheduler is responsible for generating transfer schedules
 * with random, unique amounts that sum to the total volume.
 */
export class Scheduler {
  /**
   * Generates a schedule of transfer operations with random, unique amounts
   * that sum to the specified total volume.
   * 
   * @param n - Number of child wallets to create transfers between
   * @param totalVolume - Total volume to distribute (in token base units)
   * @param tokenDecimals - Decimal places of the token (e.g., 9 for SOL, 6 for USDC)
   * @returns Array of TransferOp objects
   */
  generateSchedule(n: number, totalVolume: bigint, tokenDecimals: number): TransferOp[] {
    if (n < 2) {
      throw new Error('Number of wallets must be at least 2');
    }
    if (totalVolume <= 0n) {
      throw new Error('Total volume must be greater than 0');
    }
    if (tokenDecimals < 0 || tokenDecimals > 18) {
      throw new Error('Token decimals must be between 0 and 18');
    }

    try {
      // Generate n random, unique amounts that sum to totalVolume
      const amounts = this.generateUniqueAmounts(n, totalVolume, tokenDecimals);
      
      // Create transfer operations with round-robin pattern
      const ops: TransferOp[] = [];
      for (let i = 0; i < n; i++) {
        ops.push({
          sourceIndex: i,
          destinationIndex: (i + 1) % n, // Round-robin: 0→1, 1→2, ..., n-1→0
          amount: amounts[i],
        });
      }
      
      return ops;
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      console.error('Error generating schedule:', errorMessage);
      throw new Error(`Failed to generate schedule: ${errorMessage}`);
    }
  }

  /**
   * Generates n random, unique bigint amounts that sum to the total volume
   * 
   * @param n - Number of amounts to generate
   * @param totalVolume - The sum of all amounts
   * @param tokenDecimals - Decimal places of the token
   * @returns Array of n unique bigint amounts
   */
  private generateUniqueAmounts(n: number, totalVolume: bigint, tokenDecimals: number): bigint[] {
    // Minimum amount to ensure we don't have amounts too small to be useful
    // For smaller decimal tokens like USDC (6 decimals), this would be 0.01 units
    // For larger decimal tokens like SOL (9 decimals), this would be 0.001 units
    const minAmount = BigInt(10) ** BigInt(Math.max(0, tokenDecimals - 2));
    
    // Check if the total volume is sufficient for the minimum amount per wallet
    if (totalVolume < minAmount * BigInt(n)) {
      throw new Error(`Total volume too small for ${n} wallets with minimum amount of ${minAmount}`);
    }
    
    // Dividing points (n-1 points for n amounts)
    // We'll use a set to ensure uniqueness
    const divPointsSet = new Set<bigint>();
    
    // Maximum attempts to avoid infinite loop in rare cases
    const maxAttempts = n * 10;
    let attempts = 0;
    
    // Adjust the range to ensure we have room for uniqueness
    // The range is 1 to totalVolume - 1
    while (divPointsSet.size < n - 1 && attempts < maxAttempts) {
      attempts++;
      
      // Generate a random bigint between minAmount and totalVolume - minAmount
      const randPoint = this.randomBigInt(minAmount, totalVolume - minAmount);
      divPointsSet.add(randPoint);
    }
    
    if (divPointsSet.size < n - 1) {
      throw new Error('Could not generate enough unique division points');
    }
    
    // Convert set to array and sort
    const divPoints = Array.from(divPointsSet).sort((a, b) => 
      a < b ? -1 : a > b ? 1 : 0
    );
    
    // Generate amounts from division points
    const amounts: bigint[] = [];
    
    // First amount is from 0 to first division point
    amounts.push(divPoints[0]);
    
    // Middle amounts are differences between adjacent division points
    for (let i = 1; i < divPoints.length; i++) {
      amounts.push(divPoints[i] - divPoints[i - 1]);
    }
    
    // Last amount is from last division point to totalVolume
    amounts.push(totalVolume - divPoints[divPoints.length - 1]);
    
    // Shuffle the amounts to ensure randomness in the distribution
    return this.shuffleArray(amounts);
  }

  /**
   * Generates a random bigint between min and max (inclusive)
   * 
   * @param min - Minimum value
   * @param max - Maximum value
   * @returns Random bigint
   */
  private randomBigInt(min: bigint, max: bigint): bigint {
    // Calculate range and convert to Number for Math.random
    // This is safe because we're using it for random generation, not arithmetic
    const range = Number(max - min + 1n);
    
    // Generate random value and convert back to BigInt
    const randomOffset = BigInt(Math.floor(Math.random() * range));
    return min + randomOffset;
  }

  /**
   * Shuffles an array using the Fisher-Yates algorithm
   * 
   * @param array - Array to shuffle
   * @returns Shuffled array
   */
  private shuffleArray<T>(array: T[]): T[] {
    const result = [...array];
    for (let i = result.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [result[i], result[j]] = [result[j], result[i]];
    }
    return result;
  }

  /**
   * Verifies that the generated transfers are valid:
   * - All amounts are unique
   * - All amounts are greater than or equal to minAmount
   * - The sum of amounts equals totalVolume
   * 
   * @param transfers - Array of TransferOp objects
   * @param totalVolume - Expected total volume
   * @param minAmount - Minimum allowed amount
   * @returns True if valid, false otherwise
   */
  verifyTransfers(transfers: TransferOp[], totalVolume: bigint, minAmount: bigint = 1n): boolean {
    // Check that all amounts are unique
    const amounts = transfers.map(t => t.amount);
    const uniqueAmounts = new Set(amounts.map(a => a.toString())); // Convert to string for Set comparison
    if (uniqueAmounts.size !== amounts.length) {
      console.error('Not all amounts are unique');
      return false;
    }
    
    // Check that all amounts are >= minAmount
    if (amounts.some(a => a < minAmount)) {
      console.error('Some amounts are less than the minimum amount');
      return false;
    }
    
    // Check that the sum of amounts equals totalVolume
    const sum = amounts.reduce((acc, curr) => acc + curr, 0n);
    if (sum !== totalVolume) {
      console.error(`Sum of amounts (${sum}) does not equal total volume (${totalVolume})`);
      return false;
    }
    
    return true;
  }
}

/**
 * Create and export a default instance of Scheduler.
 */
export const defaultScheduler = new Scheduler();

/**
 * Convenience function to create a new Scheduler instance.
 */
export function createScheduler(): Scheduler {
  return new Scheduler();
} 