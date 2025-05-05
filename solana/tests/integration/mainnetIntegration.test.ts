/**
 * Unit tests for MainnetIntegration class
 */

import path from 'path';
import fs from 'fs';
import os from 'os';
import { Connection, Keypair, LAMPORTS_PER_SOL, PublicKey } from '@solana/web3.js';
import { MainnetIntegration } from '../../src/integration/mainnetIntegration';

// Mock dependencies
jest.mock('@solana/web3.js');
jest.mock('../../src/integration/walletStorage');
jest.mock('../../src/funding/walletFunder');
jest.mock('../../src/scheduler/scheduler');
jest.mock('../../src/transactions/txExecutor');

describe('MainnetIntegration', () => {
  let mainnetIntegration: MainnetIntegration;
  let tempDir: string;
  
  beforeEach(() => {
    // Create a temporary directory for test wallet storage
    tempDir = path.join(os.tmpdir(), `mainnet-integration-test-${Date.now()}`);
    fs.mkdirSync(tempDir, { recursive: true });
    
    // Create the instance with temp directory
    mainnetIntegration = new MainnetIntegration(tempDir);
    
    // Reset all mocks
    jest.clearAllMocks();
  });
  
  afterEach(() => {
    // Clean up temporary directory
    if (fs.existsSync(tempDir)) {
      fs.rmSync(tempDir, { recursive: true, force: true });
    }
  });
  
  test('should initialize with mainnet configuration', () => {
    // Manually test constructor properties
    expect((mainnetIntegration as any).walletStoragePath).toBe(tempDir);
    expect(Connection).toHaveBeenCalledWith(expect.stringContaining('mainnet'));
  });
  
  test('should run complete workflow', async () => {
    // Mock necessary methods for workflow
    const mockMotherWallet = Keypair.generate();
    const mockChildWallets = [Keypair.generate(), Keypair.generate()];
    
    // Mock balance to pass zero balance check
    (Connection.prototype.getBalance as jest.Mock).mockResolvedValue(LAMPORTS_PER_SOL);
    
    // Mock private methods
    (mainnetIntegration as any).getOrCreateMotherWallet = jest.fn().mockResolvedValue(mockMotherWallet);
    (mainnetIntegration as any).getOrCreateChildWallets = jest.fn().mockResolvedValue(mockChildWallets);
    (mainnetIntegration as any).executeTransferSchedule = jest.fn().mockResolvedValue([
      { status: 'confirmed', operation: { amount: BigInt(1000000) }, confirmationTime: 1000 }
    ]);
    
    // Mock scheduler
    const mockOperations = [{ from: new PublicKey('x'), to: new PublicKey('y'), amount: BigInt(1000000) }];
    (mainnetIntegration as any).scheduler.generateSchedule = jest.fn().mockReturnValue(mockOperations);
    
    // Mock wallet funder
    (mainnetIntegration as any).walletFunder.fundWallet = jest.fn().mockResolvedValue('mock-signature');
    
    // Run workflow
    const summary = await mainnetIntegration.runCompleteWorkflow(
      2, // childCount
      0.001, // fundingAmountSol
      0.0005 // totalVolumeSol
    );
    
    // Verify the summary
    expect(summary).toBeDefined();
    expect(summary.networkType).toBe('mainnet');
    expect(summary.totalOperations).toBeGreaterThan(0);
    expect(summary.error).toBeUndefined();
  });
  
  test('should handle errors during workflow', async () => {
    // Mock to throw an error
    (Connection.prototype.getBalance as jest.Mock).mockRejectedValue(new Error('RPC connection failed'));
    
    // Run workflow
    const summary = await mainnetIntegration.runCompleteWorkflow();
    
    // Verify the error is captured
    expect(summary.error).toContain('RPC connection failed');
  });
  
  // More tests can be added for specific methods as needed
}); 