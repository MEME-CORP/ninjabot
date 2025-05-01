import { describe, beforeAll, afterAll, it, expect } from '@jest/globals';
import {
  createAndStoreMotherWallet,
  loadMotherWallet,
  generateAndStoreChildWallets,
  loadChildWallets,
  clearWalletStorage
} from '../../src/integration/walletStorage';
import { defaultIntegrationManager } from '../../src/integration/integrationManager';
import { PublicKey } from '@solana/web3.js';

// This test actually connects to Solana devnet
// and creates real wallets
describe('Wallet Integration Tests', () => {
  const TEST_WALLET_COUNT = 2; // Keep low for faster tests
  
  // Clear wallet storage before and after tests
  beforeAll(async () => {
    clearWalletStorage();
  });
  
  afterAll(async () => {
    // Comment this out if you want to keep the wallets for manual inspection
    // clearWalletStorage();
  });
  
  it('should create a mother wallet', async () => {
    const motherWallet = await createAndStoreMotherWallet();
    expect(motherWallet).toBeDefined();
    expect(motherWallet.publicKey).toBeDefined();
    expect(motherWallet.mnemonic).toBeDefined();
    expect(motherWallet.mnemonic.split(' ').length).toBeGreaterThanOrEqual(12);
    expect(motherWallet.privateKeyBase64).toBeDefined();
    
    // Verify the stored wallet can be loaded
    const loadedWallet = loadMotherWallet();
    expect(loadedWallet).toBeDefined();
    expect(loadedWallet.publicKey).toBe(motherWallet.publicKey);
    
    // Verify the public key is valid
    expect(() => new PublicKey(motherWallet.publicKey)).not.toThrow();
  }, 20000); // Allow 20 seconds for wallet creation
  
  it('should generate child wallets from the mother wallet', async () => {
    // Ensure mother wallet exists
    let motherWallet = loadMotherWallet();
    if (!motherWallet) {
      motherWallet = await createAndStoreMotherWallet();
    }
    
    // Generate child wallets
    const childWallets = await generateAndStoreChildWallets(TEST_WALLET_COUNT);
    expect(childWallets).toHaveLength(TEST_WALLET_COUNT);
    
    // Verify each child wallet
    childWallets.forEach((child, index) => {
      expect(child.index).toBe(index);
      expect(child.publicKey).toBeDefined();
      expect(child.parentPublicKey).toBe(motherWallet.publicKey);
      expect(() => new PublicKey(child.publicKey)).not.toThrow();
    });
    
    // Verify the stored wallets can be loaded
    const loadedChildren = loadChildWallets();
    expect(loadedChildren).toHaveLength(TEST_WALLET_COUNT);
  }, 30000); // Allow 30 seconds for derivation
  
  it('should be able to check balance of created wallets', async () => {
    // Load mother wallet
    const motherWallet = loadMotherWallet();
    expect(motherWallet).toBeDefined();
    
    // Check balance of mother wallet (it will be 0 until funded)
    const balance = await defaultIntegrationManager.checkBalance(motherWallet.publicKey);
    expect(typeof balance).toBe('number');
    console.log(`Mother wallet balance: ${balance} SOL`);
    
    // Note: For a complete test, we would need to fund this wallet
    // from a testnet faucet, but that's beyond the scope of this test
  }, 20000); // Allow 20 seconds for balance check
});

// This will be a limited version of the complete workflow test
// that doesn't execute actual transactions (to avoid needing SOL)
describe('Integration Manager Basic Tests', () => {
  beforeAll(async () => {
    clearWalletStorage();
  });
  
  it('should initialize the system with wallets', async () => {
    const { motherWallet, childWallets } = await defaultIntegrationManager.initializeSystem(3);
    expect(motherWallet).toBeDefined();
    expect(childWallets).toHaveLength(3);
    
    // Verify public keys are valid
    expect(() => new PublicKey(motherWallet.publicKey)).not.toThrow();
    childWallets.forEach(child => {
      expect(() => new PublicKey(child.publicKey)).not.toThrow();
    });
  }, 30000);
  
  it('should generate a valid transfer schedule', async () => {
    const { schedule, totalAmount, totalFees } = await defaultIntegrationManager.generateTransferSchedule(0.01);
    
    expect(schedule).toBeDefined();
    expect(schedule.length).toBeGreaterThan(0);
    expect(totalAmount).toBeDefined();
    expect(typeof totalAmount).toBe('bigint');
    expect(totalFees).toBeDefined();
    expect(typeof totalFees).toBe('bigint');
    
    // Verify the operations in the schedule
    schedule.forEach(op => {
      expect(typeof op.sourceIndex).toBe('number');
      expect(typeof op.destinationAddress).toBe('string');
      expect(typeof op.amount).toBe('bigint');
      expect(typeof op.isFee).toBe('boolean');
    });
  }, 20000);
}); 