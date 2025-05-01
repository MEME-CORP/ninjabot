import { Scheduler } from '../../src/scheduler/scheduler';
import { TransferOp } from '../../src/models/types';
import { describe, beforeEach, test, expect } from '@jest/globals';

describe('Scheduler', () => {
  let scheduler: Scheduler;
  
  beforeEach(() => {
    scheduler = new Scheduler();
  });
  
  describe('generateSchedule', () => {
    test('should generate a valid schedule with the correct number of operations', () => {
      const n = 5;
      const totalVolume = 1000000n;
      const tokenDecimals = 6;
      
      const result = scheduler.generateSchedule(n, totalVolume, tokenDecimals);
      
      expect(result.length).toBe(n);
      expect(scheduler.verifyTransfers(result, totalVolume)).toBe(true);
    });
    
    test('should generate unique amounts that sum to the total volume', () => {
      const n = 3;
      const totalVolume = 10000000n;
      const tokenDecimals = 6;
      
      const result = scheduler.generateSchedule(n, totalVolume, tokenDecimals);
      
      // Check sum
      const sum = result.reduce((acc, op) => acc + op.amount, 0n);
      expect(sum).toBe(totalVolume);
      
      // Check uniqueness
      const amounts = result.map(op => op.amount.toString());
      const uniqueAmounts = new Set(amounts);
      expect(uniqueAmounts.size).toBe(n);
    });
    
    test('should create a round-robin pattern for wallets', () => {
      const n = 4;
      const totalVolume = 100000n;
      const tokenDecimals = 6;
      
      const result = scheduler.generateSchedule(n, totalVolume, tokenDecimals);
      
      // Check round-robin pattern (0→1, 1→2, ..., n-1→0)
      for (let i = 0; i < n; i++) {
        expect(result[i].sourceIndex).toBe(i);
        expect(result[i].destinationIndex).toBe((i + 1) % n);
      }
    });
    
    test('should throw an error if number of wallets is less than 2', () => {
      expect(() => {
        scheduler.generateSchedule(1, 1000n, 6);
      }).toThrow('Number of wallets must be at least 2');
    });
    
    test('should throw an error if total volume is 0 or negative', () => {
      expect(() => {
        scheduler.generateSchedule(3, 0n, 6);
      }).toThrow('Total volume must be greater than 0');
      
      expect(() => {
        scheduler.generateSchedule(3, -100n, 6);
      }).toThrow('Total volume must be greater than 0');
    });
    
    test('should throw an error if token decimals are out of range', () => {
      expect(() => {
        scheduler.generateSchedule(3, 1000n, -1);
      }).toThrow('Token decimals must be between 0 and 18');
      
      expect(() => {
        scheduler.generateSchedule(3, 1000n, 19);
      }).toThrow('Token decimals must be between 0 and 18');
    });
    
    test('should throw an error if total volume is too small for the number of wallets', () => {
      // For 6 decimals, minAmount would be 10^4 (0.01 tokens)
      // For 3 wallets, we need at least 3 * 10^4 = 30,000
      expect(() => {
        scheduler.generateSchedule(3, 20000n, 6);
      }).toThrow('Total volume too small');
    });
  });
  
  describe('verifyTransfers', () => {
    test('should return true for valid transfers', () => {
      const transfers: TransferOp[] = [
        { sourceIndex: 0, destinationIndex: 1, amount: 100n },
        { sourceIndex: 1, destinationIndex: 2, amount: 200n },
        { sourceIndex: 2, destinationIndex: 0, amount: 300n }
      ];
      
      const result = scheduler.verifyTransfers(transfers, 600n);
      expect(result).toBe(true);
    });
    
    test('should return false if amounts are not unique', () => {
      const transfers: TransferOp[] = [
        { sourceIndex: 0, destinationIndex: 1, amount: 100n },
        { sourceIndex: 1, destinationIndex: 2, amount: 100n }, // Duplicate amount
        { sourceIndex: 2, destinationIndex: 0, amount: 200n }
      ];
      
      const result = scheduler.verifyTransfers(transfers, 400n);
      expect(result).toBe(false);
    });
    
    test('should return false if an amount is less than minimum', () => {
      const transfers: TransferOp[] = [
        { sourceIndex: 0, destinationIndex: 1, amount: 5n },
        { sourceIndex: 1, destinationIndex: 2, amount: 15n },
        { sourceIndex: 2, destinationIndex: 0, amount: 20n }
      ];
      
      const result = scheduler.verifyTransfers(transfers, 40n, 10n);
      expect(result).toBe(false);
    });
    
    test('should return false if sum does not equal total volume', () => {
      const transfers: TransferOp[] = [
        { sourceIndex: 0, destinationIndex: 1, amount: 100n },
        { sourceIndex: 1, destinationIndex: 2, amount: 200n },
        { sourceIndex: 2, destinationIndex: 0, amount: 300n }
      ];
      
      const result = scheduler.verifyTransfers(transfers, 700n); // Total is 600, not 700
      expect(result).toBe(false);
    });
  });
  
  describe('edge cases', () => {
    test('should handle large volumes correctly', () => {
      const n = 5;
      const totalVolume = 10000000000000000n; // Very large number
      const tokenDecimals = 9;
      
      const result = scheduler.generateSchedule(n, totalVolume, tokenDecimals);
      expect(result.length).toBe(n);
      expect(scheduler.verifyTransfers(result, totalVolume)).toBe(true);
    });
    
    test('should handle minimum viable volume', () => {
      const n = 2;
      const tokenDecimals = 6;
      // Minimum amount would be 10^4, so for 2 wallets we need at least 2*10^4
      // Add some more to ensure uniqueness
      const totalVolume = 3n * (10n ** 4n);
      
      const result = scheduler.generateSchedule(n, totalVolume, tokenDecimals);
      expect(result.length).toBe(n);
      expect(scheduler.verifyTransfers(result, totalVolume)).toBe(true);
    });
    
    test('should handle tokens with 0 decimals', () => {
      const n = 3;
      const totalVolume = 100n;
      const tokenDecimals = 0;
      
      const result = scheduler.generateSchedule(n, totalVolume, tokenDecimals);
      expect(result.length).toBe(n);
      expect(scheduler.verifyTransfers(result, totalVolume)).toBe(true);
    });
  });
}); 