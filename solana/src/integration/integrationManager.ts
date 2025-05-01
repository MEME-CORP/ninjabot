import { createSolanaRpcClient } from '../utils/solanaRpcClient';
import { TxExecutor, defaultTxExecutor } from '../transactions/txExecutor';
import { defaultWalletManager, getWalletFromIndex } from '../wallet/walletManager';
import { defaultFeeOracle } from '../fees/feeOracle';
import { FeeCollector, prepareFeeTransfers } from '../fees/feeCollector';
import { Scheduler, defaultScheduler } from '../scheduler/scheduler';
import { TokenInfo } from '../tokens/tokenInfo';
import { DetailedTransferOp, OperationResult, RunSummary, TransferOp } from '../models/types';
import { SOLANA_RPC_URL_DEVNET, SERVICE_WALLET_ADDRESS } from '../config';
import { 
  createAndStoreMotherWallet, 
  generateAndStoreChildWallets,
  importMotherWalletFromStorage,
  loadChildWallets,
  loadMotherWallet
} from './walletStorage';
import { LAMPORTS_PER_SOL, PublicKey } from '@solana/web3.js';
import { BalanceResponse, isBalanceResponse } from '../utils/rpcTypes';

/**
 * IntegrationManager handles the complete workflow of wallet creation, 
 * funding, scheduling transfers, and executing transactions.
 */
export class IntegrationManager {
  private rpcClient = createSolanaRpcClient(SOLANA_RPC_URL_DEVNET);
  private txExecutor = defaultTxExecutor;
  private scheduler = defaultScheduler;
  private feeOracle = defaultFeeOracle;
  private tokenInfo = new TokenInfo();
  
  /**
   * Initializes the system by creating a mother wallet and child wallets
   * 
   * @param childCount - Number of child wallets to create
   * @returns Object containing created wallets information
   */
  async initializeSystem(childCount: number): Promise<{ 
    motherWallet: any, 
    childWallets: any[] 
  }> {
    // Create mother wallet
    console.log('Creating mother wallet...');
    const motherWallet = await createAndStoreMotherWallet();
    console.log(`Mother wallet created: ${motherWallet.publicKey}`);
    
    // Create child wallets
    console.log(`Generating ${childCount} child wallets...`);
    const childWallets = await generateAndStoreChildWallets(childCount);
    console.log(`${childCount} child wallets generated.`);
    
    return { motherWallet, childWallets };
  }
  
  /**
   * Funds child wallets from the mother wallet
   * 
   * @param amountSolPerChild - Amount of SOL to fund each child wallet with
   * @returns Array of funding operation results
   */
  async fundChildWallets(amountSolPerChild: number): Promise<OperationResult[]> {
    // Load mother wallet
    const motherWallet = loadMotherWallet();
    if (!motherWallet) {
      throw new Error('Mother wallet not found. Call initializeSystem first.');
    }
    
    // Import mother wallet
    const motherSigner = await importMotherWalletFromStorage();
    if (!motherSigner) {
      throw new Error('Failed to import mother wallet from storage.');
    }
    
    // Load child wallets
    const childWallets = loadChildWallets();
    if (childWallets.length === 0) {
      throw new Error('No child wallets found. Call initializeSystem first.');
    }
    
    console.log(`Funding ${childWallets.length} child wallets with ${amountSolPerChild} SOL each...`);
    
    // Create funding operations - use a special case for the mother wallet
    const fundingOperations: DetailedTransferOp[] = childWallets.map((child, index) => ({
      sourceIndex: -1, // Negative index indicates mother wallet
      destinationAddress: child.publicKey,
      amount: BigInt(Math.floor(amountSolPerChild * LAMPORTS_PER_SOL)),
      isFee: false
    }));
    
    // Create transaction executor with our RPC client
    const results: OperationResult[] = [];
    
    // Override getWalletFromIndex to handle mother wallet
    const originalGetWallet = getWalletFromIndex;
    
    // Process each funding operation
    for (const op of fundingOperations) {
      console.log(`Funding child wallet ${op.destinationAddress} with ${Number(op.amount) / LAMPORTS_PER_SOL} SOL...`);
      
      // For negative index, use the mother wallet
      if (op.sourceIndex === -1) {
        // Override the wallet retrieval function just for this operation
        (global as any).getWalletFromIndex = async (idx: number) => {
          if (idx === -1) return motherSigner;
          return originalGetWallet(idx);
        };
      }
      
      // Execute the transfer with the appropriate wallet source
      const result = await this.txExecutor.executeSolTransfer(op, {
        skipPreflight: false,
        maxRetries: 3,
        confirmationTimeoutMs: 60000,
        checkFeeSpikeThreshold: true
      });
      
      results.push(result);
      console.log(`Funding result: ${result.status}${result.error ? ` - Error: ${result.error}` : ''}`);
    }
    
    // Restore original function
    (global as any).getWalletFromIndex = originalGetWallet;
    
    return results;
  }
  
  /**
   * Generates a schedule for transfers between child wallets
   * 
   * @param totalVolumeSol - Total volume of SOL to transfer
   * @param tokenMint - Optional token mint address for token transfers
   * @returns Object containing schedule and fee information
   */
  async generateTransferSchedule(totalVolumeSol: number, tokenMint?: string): Promise<{
    schedule: DetailedTransferOp[],
    totalAmount: bigint,
    totalFees: bigint
  }> {
    // Load child wallets
    const childWallets = loadChildWallets();
    if (childWallets.length < 2) {
      throw new Error('Need at least 2 child wallets. Call initializeSystem with childCount >= 2.');
    }
    
    // Convert SOL to lamports
    const totalVolumeLamports = BigInt(Math.floor(totalVolumeSol * LAMPORTS_PER_SOL));
    
    // Get token decimals if a token mint is provided
    let tokenDecimals = 9; // Default for SOL
    if (tokenMint) {
      try {
        const tokenData = await this.tokenInfo.getTokenData(tokenMint);
        tokenDecimals = tokenData.decimals;
      } catch (error) {
        throw new Error(`Failed to get token data: ${error instanceof Error ? error.message : String(error)}`);
      }
    }
    
    // Generate the transfer schedule
    const n = childWallets.length;
    const transferOps: TransferOp[] = this.scheduler.generateSchedule(n, totalVolumeLamports, tokenDecimals);
    
    // Convert to DetailedTransferOp with wallet addresses
    const transferOpsWithAddresses: DetailedTransferOp[] = transferOps.map(op => ({
      sourceIndex: op.sourceIndex,
      destinationAddress: childWallets[op.destinationIndex].publicKey,
      amount: op.amount,
      isFee: false
    }));
    
    // Add fees
    const { allTransfers, totalAmount, totalFee } = prepareFeeTransfers(
      transferOpsWithAddresses, 
      tokenDecimals,
      SERVICE_WALLET_ADDRESS
    );
    
    return { schedule: allTransfers, totalAmount, totalFees: totalFee };
  }
  
  /**
   * Executes a transfer schedule
   * 
   * @param schedule - The schedule of transfers to execute
   * @param tokenMint - Optional token mint address for token transfers
   * @returns Summary of the execution run
   */
  async executeTransferSchedule(schedule: DetailedTransferOp[], tokenMint?: string): Promise<RunSummary> {
    // Track run metrics
    const startTime = Date.now();
    let confirmedOps = 0;
    let failedOps = 0;
    let skippedOps = 0;
    let totalConfirmationTime = 0;
    let totalAmount = 0n;
    let totalFees = 0n;
    
    // Execute each operation
    const results: OperationResult[] = [];
    
    for (let i = 0; i < schedule.length; i++) {
      const op = schedule[i];
      const destAddress = op.destinationAddress?.toString() || '[unknown]';
      console.log(`Executing transfer ${i + 1}/${schedule.length}: ${op.amount} lamports from wallet ${op.sourceIndex} to ${destAddress.substring(0, 8)}...`);
      
      let result: OperationResult;
      
      if (tokenMint) {
        // Token transfer
        result = await this.txExecutor.executeTokenTransfer(op, tokenMint, {
          skipPreflight: false,
          maxRetries: 3,
          confirmationTimeoutMs: 60000,
          checkFeeSpikeThreshold: true
        });
      } else {
        // SOL transfer
        result = await this.txExecutor.executeSolTransfer(op, {
          skipPreflight: false,
          maxRetries: 3,
          confirmationTimeoutMs: 60000,
          checkFeeSpikeThreshold: true
        });
      }
      
      results.push(result);
      
      // Update metrics
      if (result.status === 'confirmed') {
        confirmedOps++;
        if (result.confirmationTime) {
          totalConfirmationTime += result.confirmationTime;
        }
        
        if (op.isFee) {
          totalFees += op.amount;
        } else {
          totalAmount += op.amount;
        }
      } else if (result.status === 'failed') {
        failedOps++;
        console.error(`Transfer failed: ${result.error}`);
      } else if (result.status === 'skipped') {
        skippedOps++;
        console.warn(`Transfer skipped: ${result.error}`);
      }
    }
    
    // Calculate run summary
    const endTime = Date.now();
    const averageConfirmationTimeMs = confirmedOps > 0 
      ? Math.floor(totalConfirmationTime / confirmedOps) 
      : 0;
    
    const summary: RunSummary = {
      networkType: 'devnet',
      totalOperations: schedule.length,
      confirmedOperations: confirmedOps,
      failedOperations: failedOps,
      skippedOperations: skippedOps,
      totalAmount: totalAmount,
      totalFees: totalFees,
      feesCollected: totalFees,
      averageConfirmationTimeMs,
      startTime,
      endTime,
      results
    };
    
    return summary;
  }
  
  /**
   * Checks the SOL balance of an address
   * 
   * @param address - The address to check balance for
   * @returns Balance in SOL
   */
  async checkBalance(address: string): Promise<number> {
    try {
      const balance = await this.rpcClient.connection.getBalance(
        new PublicKey(address),
        'confirmed'
      );
      
      return balance / LAMPORTS_PER_SOL;
    } catch (error) {
      console.error('Error checking balance:', error);
      throw new Error(`Failed to check balance: ${error instanceof Error ? error.message : String(error)}`);
    }
  }
  
  /**
   * Runs the complete workflow: initialize, fund, generate schedule, execute
   * 
   * @param childCount - Number of child wallets to create
   * @param fundingAmountSol - Amount of SOL to fund each child with
   * @param totalVolumeSol - Total volume of SOL to transfer
   * @param tokenMint - Optional token mint address for token transfers
   * @returns Summary of the execution run
   */
  async runCompleteWorkflow(
    childCount: number,
    fundingAmountSol: number,
    totalVolumeSol: number,
    tokenMint?: string
  ): Promise<RunSummary> {
    console.log('Starting complete workflow execution...');
    
    // Step 1: Initialize system (create wallets)
    console.log('Step 1: Initializing system...');
    await this.initializeSystem(childCount);
    
    // Step 2: Fund child wallets
    console.log('Step 2: Funding child wallets...');
    await this.fundChildWallets(fundingAmountSol);
    
    // Step 3: Generate transfer schedule
    console.log('Step 3: Generating transfer schedule...');
    const { schedule } = await this.generateTransferSchedule(totalVolumeSol, tokenMint);
    
    // Step 4: Execute transfer schedule
    console.log('Step 4: Executing transfer schedule...');
    const summary = await this.executeTransferSchedule(schedule, tokenMint);
    
    console.log('Workflow completed successfully!');
    return summary;
  }
}

/**
 * Create and export a default instance of IntegrationManager
 */
export const defaultIntegrationManager = new IntegrationManager();

/**
 * Convenience function to create a new IntegrationManager instance
 */
export function createIntegrationManager(): IntegrationManager {
  return new IntegrationManager();
} 