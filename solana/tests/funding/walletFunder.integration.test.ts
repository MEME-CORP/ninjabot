/// <reference types="jest" />

import { Keypair } from '@solana/web3.js';
import { WalletFunder, WalletFunderEvent, WalletFunderEventPayloads } from '../../src/funding/walletFunder';
import { SolanaRpcClient, createSolanaRpcClient } from '../../src/utils/solanaRpcClient';
import { FeeOracle, createFeeOracle } from '../../src/fees/feeOracle';

// Skip if SKIP_INTEGRATION_TESTS=true
const SKIP_TESTS = process.env.SKIP_INTEGRATION_TESTS === 'true';

// Integration tests for WalletFunder
// These tests interact with an actual blockchain
(SKIP_TESTS ? describe.skip : describe)('WalletFunder Integration', () => {
  // Test variables
  let walletFunder: WalletFunder;
  let rpcClient: SolanaRpcClient;
  let feeOracle: FeeOracle;
  let motherWallet: Keypair;
  let childWallets: Keypair[];
  
  // Setup before all tests
  beforeAll(async () => {
    // Use localhost for test validator
    const rpcUrl = 'http://localhost:8899';
    
    // Create real clients
    rpcClient = createSolanaRpcClient(rpcUrl);
    feeOracle = createFeeOracle(rpcClient);
    
    // Create a test wallet funder with shorter timeouts for faster tests
    walletFunder = new WalletFunder(
      rpcClient,
      feeOracle,
      2, // maxRetries
      500, // retryDelayMs
      10000, // confirmationTimeoutMs
      2 // maxChildrenPerChunk
    );
    
    // Generate test wallets
    motherWallet = Keypair.generate();
    childWallets = Array(3).fill(0).map(() => Keypair.generate());
    
    // Fund the mother wallet from faucet for tests
    // This requires a running test validator with airdrop capability
    try {
      const signature = await rpcClient.rpc.requestAirdrop?.(
        motherWallet.publicKey.toString(),
        10000000000 // 10 SOL
      )?.send();
      
      if (signature) {
        // Wait for confirmation
        await rpcClient.rpc.confirmTransaction?.({
          signature,
          blockhash: (await rpcClient.getLatestBlockhash()).blockhash,
          lastValidBlockHeight: (await rpcClient.getLatestBlockhash()).lastValidBlockHeight
        })?.send();
        
        console.log('Funded mother wallet with 10 SOL for tests');
      }
    } catch (error) {
      console.error('Failed to fund mother wallet. Is the test validator running?', error);
      // We'll continue and let individual tests fail if needed
    }
  });
  
  // Clean up after each test
  beforeEach(() => {
    // Remove all event listeners
    walletFunder.removeAllListeners();
  });
  
  it('should fund multiple child wallets from mother wallet', async () => {
    // Skip if the mother wallet wasn't funded
    const motherBalance = await rpcClient.rpc.getBalance?.(
      motherWallet.publicKey.toString()
    )?.send() || 0;
    
    if (BigInt(motherBalance) < 5000000000n) { // 5 SOL minimum
      console.warn('Skipping test: Mother wallet insufficiently funded');
      return;
    }
    
    // Track events
    const events: { type: WalletFunderEvent; data: any }[] = [];
    walletFunder.on(WalletFunderEvent.FUNDING_STARTED, 
      (data: WalletFunderEventPayloads[WalletFunderEvent.FUNDING_STARTED]) => {
        events.push({ type: WalletFunderEvent.FUNDING_STARTED, data });
      }
    );
    walletFunder.on(WalletFunderEvent.FUNDING_COMPLETED, 
      (data: WalletFunderEventPayloads[WalletFunderEvent.FUNDING_COMPLETED]) => {
        events.push({ type: WalletFunderEvent.FUNDING_COMPLETED, data });
      }
    );
    walletFunder.on(WalletFunderEvent.TRANSACTION_CONFIRMED, 
      (data: WalletFunderEventPayloads[WalletFunderEvent.TRANSACTION_CONFIRMED]) => {
        events.push({ type: WalletFunderEvent.TRANSACTION_CONFIRMED, data });
      }
    );
    
    // Get child addresses
    const childAddresses = childWallets.map(wallet => wallet.publicKey.toString());
    
    // Amount to fund each child (0.1 SOL)
    const amountPerChild = 100000000n;
    
    // Fund the children
    const result = await walletFunder.fundChildWallets(
      motherWallet,
      childAddresses,
      amountPerChild
    );
    
    // Verify the result
    expect(result.successfulTransactions).toBeGreaterThan(0);
    expect(result.failedTransactions).toBe(0);
    expect(result.fundedChildAddresses).toEqual(childAddresses);
    expect(result.failedChildAddresses).toEqual([]);
    
    // Verify events were emitted
    expect(events.some(e => e.type === WalletFunderEvent.FUNDING_STARTED)).toBe(true);
    expect(events.some(e => e.type === WalletFunderEvent.FUNDING_COMPLETED)).toBe(true);
    expect(events.some(e => e.type === WalletFunderEvent.TRANSACTION_CONFIRMED)).toBe(true);
    
    // Verify each child wallet was actually funded on-chain
    for (const childWallet of childWallets) {
      const balance = await rpcClient.rpc.getBalance?.(
        childWallet.publicKey.toString()
      )?.send() || 0;
      
      expect(BigInt(balance)).toBeGreaterThanOrEqual(amountPerChild);
    }
  }, 30000); // Allow 30 seconds for this test
  
  it('should handle funding errors gracefully', async () => {
    // Create a wallet with insufficient balance
    const emptyWallet = Keypair.generate();
    
    // Track failure events
    const failureEvents: any[] = [];
    walletFunder.on(WalletFunderEvent.FUNDING_FAILED, 
      (data: WalletFunderEventPayloads[WalletFunderEvent.FUNDING_FAILED]) => {
        failureEvents.push(data);
      }
    );
    
    // Get child addresses
    const childAddresses = childWallets.map(wallet => wallet.publicKey.toString());
    
    // Amount to fund each child (1 SOL)
    const amountPerChild = 1000000000n;
    
    // Attempt to fund the children (should fail)
    const result = await walletFunder.fundChildWallets(
      emptyWallet,
      childAddresses,
      amountPerChild
    ).catch(error => {
      // We expect an error about insufficient balance
      expect(error.message).toContain('Insufficient balance');
      return null;
    });
    
    // If we got a result (not an error), it should indicate failure
    if (result) {
      expect(result.successfulTransactions).toBe(0);
      expect(result.failedTransactions).toBeGreaterThan(0);
    }
  }, 15000); // Allow 15 seconds for this test
}); 