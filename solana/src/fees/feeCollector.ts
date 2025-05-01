import { TransferOp, DetailedTransferOp } from '../models/types';
import { FEE_RATE_NUMERATOR, FEE_RATE_DENOMINATOR, SERVICE_WALLET_ADDRESS } from '../config';

/**
 * Result of fee calculations
 */
export interface FeeCalculationResult {
  allTransfers: DetailedTransferOp[];
  totalAmount: bigint;
  totalFee: bigint;
}

/**
 * FeeCollector manages the calculation and collection of service fees for token transfers
 */
export class FeeCollector {
  private feeRateNumerator: bigint;
  private feeRateDenominator: bigint;
  private serviceWalletAddress: string;

  /**
   * Creates a new FeeCollector
   * 
   * @param feeRateNumerator - Numerator for fee rate calculation (defaults to 1n)
   * @param feeRateDenominator - Denominator for fee rate calculation (defaults to 1000n, creating a 0.1% fee)
   * @param serviceWalletAddress - Address where fees will be sent
   */
  constructor(
    feeRateNumerator: bigint = FEE_RATE_NUMERATOR,
    feeRateDenominator: bigint = FEE_RATE_DENOMINATOR,
    serviceWalletAddress: string = SERVICE_WALLET_ADDRESS
  ) {
    // Validate inputs
    if (feeRateNumerator <= 0n) {
      throw new Error('Fee rate numerator must be positive');
    }
    
    if (feeRateDenominator <= 0n) {
      throw new Error('Fee rate denominator must be positive');
    }
    
    if (feeRateNumerator >= feeRateDenominator) {
      throw new Error('Fee rate must be less than 100%');
    }
    
    if (!serviceWalletAddress || serviceWalletAddress === 'YourServiceWalletAddressHere') {
      throw new Error('Service wallet address must be configured');
    }
    
    this.feeRateNumerator = feeRateNumerator;
    this.feeRateDenominator = feeRateDenominator;
    this.serviceWalletAddress = serviceWalletAddress;
  }

  /**
   * Calculate the fee amount for a given transfer amount
   * 
   * @param amount - Amount to calculate fee for
   * @returns The calculated fee amount
   */
  calculateFee(amount: bigint): bigint {
    if (amount <= 0n) {
      return 0n;
    }
    
    // Calculate fee based on fee rate (amount * numerator / denominator)
    const fee = (amount * this.feeRateNumerator) / this.feeRateDenominator;
    
    // Ensure fee is at least 1 (if the original amount is non-zero)
    return fee > 0n ? fee : (amount > 0n ? 1n : 0n);
  }

  /**
   * Get the current fee rate as a percentage
   * 
   * @returns Fee rate as a percentage (e.g., 0.1 for 0.1%)
   */
  getFeeRatePercentage(): number {
    return Number(this.feeRateNumerator * 100n) / Number(this.feeRateDenominator);
  }

  /**
   * Prepare transfers with fee operations
   * For each main transfer, a fee transfer is added
   * 
   * @param mainOps - Main transfer operations
   * @param destinationAddresses - Mapping of destination indices to addresses
   * @returns Object containing all transfers, total amount, and total fee
   */
  prepareTransfersWithFees(
    mainOps: TransferOp[],
    destinationAddresses: string[]
  ): FeeCalculationResult {
    // Validate inputs
    if (!mainOps || mainOps.length === 0) {
      throw new Error('No transfer operations provided');
    }
    
    if (!destinationAddresses || destinationAddresses.length === 0) {
      throw new Error('No destination addresses provided');
    }
    
    const allTransfers: DetailedTransferOp[] = [];
    let totalAmount = 0n;
    let totalFee = 0n;
    
    // Process each main operation
    for (let i = 0; i < mainOps.length; i++) {
      const op = mainOps[i];
      const destIndex = op.destinationIndex;
      
      // Validate destination index
      if (destIndex < 0 || destIndex >= destinationAddresses.length) {
        throw new Error(`Invalid destination index ${destIndex} for operation ${i}`);
      }
      
      const destAddress = destinationAddresses[destIndex];
      
      // Calculate fee for this operation
      const fee = this.calculateFee(op.amount);
      totalFee += fee;
      totalAmount += op.amount;
      
      // Add main transfer operation
      allTransfers.push({
        sourceIndex: op.sourceIndex,
        destinationAddress: destAddress,
        amount: op.amount,
        isFee: false
      });
      
      // Add fee transfer operation (if fee is greater than zero)
      if (fee > 0n) {
        allTransfers.push({
          sourceIndex: op.sourceIndex,
          destinationAddress: this.serviceWalletAddress,
          amount: fee,
          isFee: true
        });
      }
    }
    
    return {
      allTransfers,
      totalAmount,
      totalFee
    };
  }
  
  /**
   * Prepare detailed transfers with fee operations
   * This variant works directly with DetailedTransferOp objects
   * 
   * @param detailedOps - Detailed transfer operations
   * @returns Object containing all transfers (including fee transfers), total amount, and total fee
   */
  prepareDetailedTransfersWithFees(
    detailedOps: DetailedTransferOp[]
  ): FeeCalculationResult {
    // Validate inputs
    if (!detailedOps || detailedOps.length === 0) {
      throw new Error('No transfer operations provided');
    }
    
    const allTransfers: DetailedTransferOp[] = [];
    let totalAmount = 0n;
    let totalFee = 0n;
    
    // Process each operation
    for (const op of detailedOps) {
      // Skip operations that are already fee operations
      if (op.isFee) {
        continue;
      }
      
      // Calculate fee for this operation
      const fee = this.calculateFee(op.amount);
      totalFee += fee;
      totalAmount += op.amount;
      
      // Add main transfer operation
      allTransfers.push(op);
      
      // Add fee transfer operation (if fee is greater than zero)
      if (fee > 0n) {
        allTransfers.push({
          sourceIndex: op.sourceIndex,
          destinationAddress: this.serviceWalletAddress,
          amount: fee,
          isFee: true
        });
      }
    }
    
    return {
      allTransfers,
      totalAmount,
      totalFee
    };
  }
}

/**
 * Create and export a default instance of FeeCollector
 */
export const defaultFeeCollector = new FeeCollector();

/**
 * Convenience function to create a new FeeCollector
 * 
 * @param feeRateNumerator - Numerator for fee rate calculation
 * @param feeRateDenominator - Denominator for fee rate calculation
 * @param serviceWalletAddress - Address where fees will be sent
 * @returns A new FeeCollector instance
 */
export function createFeeCollector(
  feeRateNumerator?: bigint,
  feeRateDenominator?: bigint,
  serviceWalletAddress?: string
): FeeCollector {
  return new FeeCollector(feeRateNumerator, feeRateDenominator, serviceWalletAddress);
}

/**
 * Utility function to prepare fee transfers
 * This is a convenience wrapper around the FeeCollector.prepareDetailedTransfersWithFees method
 * 
 * @param transferOps - The detailed transfer operations
 * @param tokenDecimals - Number of decimals for the token (used for validation)
 * @param serviceWalletAddress - Optional override for the service wallet address
 * @returns Object containing all transfers (including fee transfers), total amount, and total fee
 */
export function prepareFeeTransfers(
  transferOps: DetailedTransferOp[],
  tokenDecimals: number,
  serviceWalletAddress?: string
): FeeCalculationResult {
  const collector = serviceWalletAddress 
    ? createFeeCollector(FEE_RATE_NUMERATOR, FEE_RATE_DENOMINATOR, serviceWalletAddress)
    : defaultFeeCollector;
  
  return collector.prepareDetailedTransfersWithFees(transferOps);
} 