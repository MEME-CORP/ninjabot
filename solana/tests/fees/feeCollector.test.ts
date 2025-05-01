import { FeeCollector, createFeeCollector } from '../../src/fees/feeCollector';
import { TransferOp } from '../../src/models/types';
import { describe, beforeEach, test, expect } from '@jest/globals';

describe('FeeCollector', () => {
  // Test addresses
  const SERVICE_WALLET = 'ServiceWalletAddress12345';
  const DESTINATION_ADDRESSES = [
    'DestAddress1',
    'DestAddress2',
    'DestAddress3',
    'DestAddress4'
  ];
  
  // Default fee settings
  const DEFAULT_FEE_NUMERATOR = 1n;
  const DEFAULT_FEE_DENOMINATOR = 1000n; // 0.1%
  
  let feeCollector: FeeCollector;
  
  beforeEach(() => {
    // Create a new FeeCollector instance before each test
    feeCollector = new FeeCollector(
      DEFAULT_FEE_NUMERATOR,
      DEFAULT_FEE_DENOMINATOR,
      SERVICE_WALLET
    );
  });
  
  describe('constructor', () => {
    test('should create a FeeCollector with provided values', () => {
      const customCollector = new FeeCollector(2n, 100n, 'CustomAddress');
      expect(customCollector.getFeeRatePercentage()).toBe(2);
    });
    
    test('should throw error if fee rate is negative', () => {
      expect(() => {
        new FeeCollector(-1n, 1000n, SERVICE_WALLET);
      }).toThrow('Fee rate numerator must be positive');
    });
    
    test('should throw error if fee rate is zero', () => {
      expect(() => {
        new FeeCollector(0n, 1000n, SERVICE_WALLET);
      }).toThrow('Fee rate numerator must be positive');
    });
    
    test('should throw error if denominator is negative', () => {
      expect(() => {
        new FeeCollector(1n, -1000n, SERVICE_WALLET);
      }).toThrow('Fee rate denominator must be positive');
    });
    
    test('should throw error if denominator is zero', () => {
      expect(() => {
        new FeeCollector(1n, 0n, SERVICE_WALLET);
      }).toThrow('Fee rate denominator must be positive');
    });
    
    test('should throw error if fee rate is 100% or higher', () => {
      expect(() => {
        new FeeCollector(100n, 100n, SERVICE_WALLET);
      }).toThrow('Fee rate must be less than 100%');
      
      expect(() => {
        new FeeCollector(101n, 100n, SERVICE_WALLET);
      }).toThrow('Fee rate must be less than 100%');
    });
    
    test('should throw error if service wallet address is invalid', () => {
      expect(() => {
        new FeeCollector(1n, 1000n, '');
      }).toThrow('Service wallet address must be configured');
      
      expect(() => {
        new FeeCollector(1n, 1000n, 'YourServiceWalletAddressHere');
      }).toThrow('Service wallet address must be configured');
    });
  });
  
  describe('calculateFee', () => {
    test('should calculate 0.1% fee correctly for various amounts', () => {
      // For 1000, 0.1% is 1
      expect(feeCollector.calculateFee(1000n)).toBe(1n);
      
      // For 10000, 0.1% is 10
      expect(feeCollector.calculateFee(10000n)).toBe(10n);
      
      // For large numbers
      expect(feeCollector.calculateFee(1000000n)).toBe(1000n);
      
      // For very small numbers that would result in zero fee
      // We should still get 1 as the minimum fee
      expect(feeCollector.calculateFee(100n)).toBe(1n);
      expect(feeCollector.calculateFee(10n)).toBe(1n);
      
      // For zero amount, fee should be zero
      expect(feeCollector.calculateFee(0n)).toBe(0n);
      
      // For negative amounts (invalid), fee should be zero
      expect(feeCollector.calculateFee(-1000n)).toBe(0n);
    });
    
    test('should calculate fees with custom fee rates', () => {
      // 1% fee rate
      const onePercentCollector = new FeeCollector(1n, 100n, SERVICE_WALLET);
      expect(onePercentCollector.calculateFee(1000n)).toBe(10n);
      
      // 0.5% fee rate
      const halfPercentCollector = new FeeCollector(5n, 1000n, SERVICE_WALLET);
      expect(halfPercentCollector.calculateFee(1000n)).toBe(5n);
    });
  });
  
  describe('getFeeRatePercentage', () => {
    test('should return the fee rate as a percentage', () => {
      // Default 0.1%
      expect(feeCollector.getFeeRatePercentage()).toBe(0.1);
      
      // Custom rates
      const onePercentCollector = new FeeCollector(1n, 100n, SERVICE_WALLET);
      expect(onePercentCollector.getFeeRatePercentage()).toBe(1);
      
      const halfPercentCollector = new FeeCollector(5n, 1000n, SERVICE_WALLET);
      expect(halfPercentCollector.getFeeRatePercentage()).toBe(0.5);
    });
  });
  
  describe('prepareTransfersWithFees', () => {
    test('should add fee operations for each main operation', () => {
      // Create a simple set of transfer operations
      const mainOps: TransferOp[] = [
        { sourceIndex: 0, destinationIndex: 1, amount: 1000n }
      ];
      
      // Prepare transfers with fees
      const result = feeCollector.prepareTransfersWithFees(mainOps, DESTINATION_ADDRESSES);
      
      // Should have two operations: the main transfer and the fee transfer
      expect(result.allTransfers.length).toBe(2);
      
      // Check main transfer
      expect(result.allTransfers[0]).toEqual({
        sourceIndex: 0,
        destinationAddress: DESTINATION_ADDRESSES[1],
        amount: 1000n,
        isFee: false
      });
      
      // Check fee transfer
      expect(result.allTransfers[1]).toEqual({
        sourceIndex: 0,
        destinationAddress: SERVICE_WALLET,
        amount: 1n,
        isFee: true
      });
      
      // Check totals
      expect(result.totalAmount).toBe(1000n);
      expect(result.totalFee).toBe(1n);
    });
    
    test('should handle multiple operations correctly', () => {
      // Create multiple transfer operations
      const mainOps: TransferOp[] = [
        { sourceIndex: 0, destinationIndex: 1, amount: 1000n },
        { sourceIndex: 1, destinationIndex: 2, amount: 2000n },
        { sourceIndex: 2, destinationIndex: 3, amount: 3000n }
      ];
      
      // Prepare transfers with fees
      const result = feeCollector.prepareTransfersWithFees(mainOps, DESTINATION_ADDRESSES);
      
      // Should have 6 operations: 3 main transfers and 3 fee transfers
      expect(result.allTransfers.length).toBe(6);
      
      // Check totals
      expect(result.totalAmount).toBe(6000n);
      expect(result.totalFee).toBe(6n); // 1 + 2 + 3 = 6
      
      // First main transfer
      expect(result.allTransfers[0]).toEqual({
        sourceIndex: 0,
        destinationAddress: DESTINATION_ADDRESSES[1],
        amount: 1000n,
        isFee: false
      });
      
      // First fee transfer
      expect(result.allTransfers[1]).toEqual({
        sourceIndex: 0,
        destinationAddress: SERVICE_WALLET,
        amount: 1n,
        isFee: true
      });
      
      // Second main transfer
      expect(result.allTransfers[2]).toEqual({
        sourceIndex: 1,
        destinationAddress: DESTINATION_ADDRESSES[2],
        amount: 2000n,
        isFee: false
      });
      
      // Second fee transfer
      expect(result.allTransfers[3]).toEqual({
        sourceIndex: 1,
        destinationAddress: SERVICE_WALLET,
        amount: 2n,
        isFee: true
      });
    });
    
    test('should throw error if no operations are provided', () => {
      expect(() => {
        feeCollector.prepareTransfersWithFees([], DESTINATION_ADDRESSES);
      }).toThrow('No transfer operations provided');
    });
    
    test('should throw error if no destination addresses are provided', () => {
      const mainOps: TransferOp[] = [
        { sourceIndex: 0, destinationIndex: 1, amount: 1000n }
      ];
      
      expect(() => {
        feeCollector.prepareTransfersWithFees(mainOps, []);
      }).toThrow('No destination addresses provided');
    });
    
    test('should throw error for invalid destination index', () => {
      const mainOps: TransferOp[] = [
        { sourceIndex: 0, destinationIndex: 10, amount: 1000n } // index 10 does not exist
      ];
      
      expect(() => {
        feeCollector.prepareTransfersWithFees(mainOps, DESTINATION_ADDRESSES);
      }).toThrow('Invalid destination index 10 for operation 0');
    });
    
    test('should handle very small amounts correctly', () => {
      const mainOps: TransferOp[] = [
        { sourceIndex: 0, destinationIndex: 1, amount: 10n } // 0.1% of 10 would be 0.01, rounded to 1
      ];
      
      const result = feeCollector.prepareTransfersWithFees(mainOps, DESTINATION_ADDRESSES);
      
      expect(result.allTransfers.length).toBe(2);
      expect(result.totalFee).toBe(1n); // Minimum fee
    });
    
    test('should skip fee transfers for zero amount operations', () => {
      const mainOps: TransferOp[] = [
        { sourceIndex: 0, destinationIndex: 1, amount: 0n }
      ];
      
      const result = feeCollector.prepareTransfersWithFees(mainOps, DESTINATION_ADDRESSES);
      
      // Should only have the main transfer, no fee transfer (as fee would be 0)
      expect(result.allTransfers.length).toBe(1);
      expect(result.totalFee).toBe(0n);
    });
  });
  
  describe('createFeeCollector', () => {
    test('should create a new FeeCollector instance', () => {
      const collector = createFeeCollector(2n, 100n, 'CustomServiceWallet');
      expect(collector).toBeInstanceOf(FeeCollector);
      expect(collector.getFeeRatePercentage()).toBe(2);
    });
  });
}); 