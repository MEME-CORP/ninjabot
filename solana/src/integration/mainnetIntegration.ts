/**
 * MainnetIntegration module
 * 
 * This module provides functionality for running operations on the Solana mainnet.
 * It is designed to be used with caution as it deals with real SOL and tokens.
 */

import * as path from 'path';
import * as fs from 'fs';
import { Connection, Keypair, LAMPORTS_PER_SOL, PublicKey, SystemProgram, Transaction } from '@solana/web3.js';
import { 
  createAndStoreMotherWallet, 
  loadMotherWallet,
  importMotherWalletFromStorage,
  loadChildWallets,
  generateAndStoreChildWallets
} from './walletStorage';
import { WalletFunder } from '../funding/walletFunder';
import { Scheduler, defaultScheduler } from '../scheduler/scheduler';
import { TxExecutor } from '../transactions/txExecutor';
import { TransferOp, OperationResult, OperationStatus } from '../models/types';
import { SOLANA_RPC_URL_MAINNET } from '../config';
import { createSolanaRpcClient } from '../utils/solanaRpcClient';

// Define additional types needed for the mainnet integration
enum TransferMode {
  RETURN_FUNDS = 'return_funds',
  TOKEN_SWAP = 'token_swap'
}

interface TransferOperation {
  from: PublicKey;
  to: PublicKey;
  amount: bigint;
}

interface IntegrationSummary {
  networkType: 'devnet' | 'mainnet';
  startTime: number;
  endTime: number;
  totalOperations: number;
  confirmedOperations: number;
  failedOperations: number;
  skippedOperations: number;
  totalAmount: bigint;
  feesCollected: bigint;
  averageConfirmationTimeMs: number;
  error?: string;
}

/**
 * MainnetIntegration class - handles all mainnet integration workflows
 */
export class MainnetIntegration {
  private connection: Connection;
  private rpcClient: any;
  private walletFunder: WalletFunder;
  private scheduler: Scheduler;
  private txExecutor: TxExecutor;
  private walletStoragePath: string;

  /**
   * Constructor for MainnetIntegration
   * @param walletStoragePath Path to store wallet files (defaults to a mainnet subfolder)
   */
  constructor(walletStoragePath?: string) {
    // Set up mainnet connection
    this.connection = new Connection(SOLANA_RPC_URL_MAINNET);
    this.rpcClient = createSolanaRpcClient(SOLANA_RPC_URL_MAINNET);
    
    // Set up wallet storage path
    if (walletStoragePath) {
      this.walletStoragePath = walletStoragePath;
    } else {
      // Default to a 'mainnet' subdirectory of the wallet-storage directory
      const baseDir = path.resolve(process.cwd(), 'wallet-storage');
      this.walletStoragePath = path.join(baseDir, 'mainnet');
      
      // Ensure directory exists
      if (!fs.existsSync(this.walletStoragePath)) {
        fs.mkdirSync(this.walletStoragePath, { recursive: true });
      }
    }
    
    // Initialize components
    this.walletFunder = new WalletFunder(this.rpcClient);
    this.scheduler = defaultScheduler;
    this.txExecutor = new TxExecutor(this.rpcClient);
    
    console.log(`Initialized MainnetIntegration with RPC: ${SOLANA_RPC_URL_MAINNET}`);
    console.log(`Wallet storage path: ${this.walletStoragePath}`);
  }

  /**
   * Runs a complete mainnet workflow
   * @param childCount Number of child wallets to create
   * @param fundingAmountSol Amount of SOL to fund each child wallet
   * @param totalVolumeSol Total volume of SOL to transfer
   * @param tokenMint Optional token mint for token operations
   * @param forceNewMotherWallet Whether to force creation of a new mother wallet
   * @returns Summary of the integration run
   */
  async runCompleteWorkflow(
    childCount: number = 3,
    fundingAmountSol: number = 0.001,
    totalVolumeSol: number = 0.0005,
    tokenMint?: string,
    forceNewMotherWallet: boolean = false
  ): Promise<IntegrationSummary> {
    console.log('Starting Mainnet integration workflow...');
    console.log('⚠️ WARNING: This is running on MAINNET with REAL SOL! ⚠️\n');
    
    const startTime = Date.now();
    let totalOperations = 0;
    let confirmedOperations = 0;
    let failedOperations = 0;
    let skippedOperations = 0;
    let totalAmount = BigInt(0);
    let feesCollected = BigInt(0);
    let confirmationTimes: number[] = [];
    
    try {
      // Step 1: Create or load mother wallet
      console.log('Step 1: Setting up mother wallet...');
      const motherWallet = forceNewMotherWallet
        ? await this.createMotherWallet(true)
        : await this.getOrCreateMotherWallet();
      
      console.log(`Mother wallet: ${motherWallet.publicKey.toBase58()}`);
      
      // Check mother wallet balance
      const motherBalance = await this.connection.getBalance(motherWallet.publicKey);
      console.log(`Mother wallet balance: ${motherBalance / LAMPORTS_PER_SOL} SOL`);
      
      if (motherBalance === 0) {
        throw new Error('Mother wallet has no balance. Please fund it before continuing.');
      }
      
      // Step 2: Create or load child wallets
      console.log('\nStep 2: Setting up child wallets...');
      const childWallets = await this.getOrCreateChildWallets(motherWallet, childCount);
      console.log(`Created/loaded ${childWallets.length} child wallets`);
      
      // Step 3: Fund child wallets if requested
      if (fundingAmountSol > 0) {
        console.log('\nStep 3: Funding child wallets...');
        
        // Check if mother wallet has enough balance
        const fundingLamports = BigInt(Math.floor(fundingAmountSol * LAMPORTS_PER_SOL));
        const totalFundingLamports = fundingLamports * BigInt(childWallets.length);
        const estimatedFeesLamports = BigInt(5000 * childWallets.length); // Rough estimate
        
        if (BigInt(motherBalance) < totalFundingLamports + estimatedFeesLamports) {
          throw new Error(
            `Mother wallet has insufficient balance. ` +
            `Required: ${Number(totalFundingLamports + estimatedFeesLamports) / LAMPORTS_PER_SOL} SOL, ` +
            `Available: ${motherBalance / LAMPORTS_PER_SOL} SOL`
          );
        }
        
        // Fund each child wallet
        for (let i = 0; i < childWallets.length; i++) {
          const wallet = childWallets[i];
          console.log(`Funding wallet ${i + 1}/${childWallets.length}: ${wallet.publicKey.toBase58()}`);
          
          try {
            const signature = await this.fundWallet(
              motherWallet,
              wallet.publicKey,
              fundingLamports
            );
            
            console.log(`Funding transaction sent: ${signature}`);
            totalOperations++;
            
            // Wait for confirmation
            const confirmation = await this.connection.confirmTransaction(signature);
            
            if (confirmation.value.err) {
              console.error(`Funding failed: ${confirmation.value.err}`);
              failedOperations++;
            } else {
              console.log('Funding confirmed successfully!');
              confirmedOperations++;
              totalAmount += fundingLamports;
            }
          } catch (error) {
            console.error(`Error funding wallet ${i + 1}:`, error);
            failedOperations++;
          }
        }
      } else {
        console.log('\nStep 3: Skipping funding (amount set to 0)');
      }
      
      // Step 4: Generate transfer schedule
      console.log('\nStep 4: Generating transfer schedule...');
      
      let transferMode = tokenMint ? TransferMode.TOKEN_SWAP : TransferMode.RETURN_FUNDS;
      
      if (tokenMint) {
        console.log(`Using token swap mode with mint: ${tokenMint}`);
      } else {
        console.log('Using return funds mode (SOL only)');
      }
      
      // For simplicity, we'll use 9 decimals for SOL
      const tokenDecimals = 9;
      const scheduleInputs = childWallets.length;
      const transferOps = this.scheduler.generateSchedule(scheduleInputs, BigInt(Math.floor(totalVolumeSol * LAMPORTS_PER_SOL)), tokenDecimals);
      
      // Convert from TransferOp to our internal TransferOperation format
      const operations: TransferOperation[] = transferOps.map(op => ({
        from: childWallets[op.sourceIndex].publicKey,
        to: childWallets[op.destinationIndex].publicKey,
        amount: op.amount
      }));
      
      console.log(`Generated ${operations.length} operations`);
      
      // Step 5: Execute transfer schedule
      if (operations.length > 0) {
        console.log('\nStep 5: Executing operations...');
        
        const results = await this.executeTransferSchedule(childWallets, operations);
        
        // Update counters
        totalOperations += operations.length;
        confirmedOperations += results.filter(r => r.status === OperationStatus.CONFIRMED).length;
        failedOperations += results.filter(r => r.status === OperationStatus.FAILED).length;
        skippedOperations += results.filter(r => r.status === OperationStatus.SKIPPED).length;
        
        // Calculate confirmation times
        confirmationTimes = results
          .filter(r => r.status === OperationStatus.CONFIRMED && r.confirmationTime)
          .map(r => r.confirmationTime!);
        
        // Sum up total amount
        for (const op of operations) {
          if (results.find(r => 
            r.status === OperationStatus.CONFIRMED && 
            r.signature && 
            r.opIndex === operations.indexOf(op)
          )) {
            totalAmount += op.amount;
          }
        }
      } else {
        console.log('No operations to execute.');
      }
      
      // Build and return summary
      const endTime = Date.now();
      const averageConfirmationTimeMs = confirmationTimes.length > 0
        ? confirmationTimes.reduce((sum, time) => sum + time, 0) / confirmationTimes.length
        : 0;
      
      const summary: IntegrationSummary = {
        networkType: 'mainnet',
        startTime,
        endTime,
        totalOperations,
        confirmedOperations,
        failedOperations,
        skippedOperations,
        totalAmount,
        feesCollected,
        averageConfirmationTimeMs
      };
      
      console.log('\nMainnet integration workflow completed!');
      return summary;
      
    } catch (error) {
      console.error('Error during mainnet integration workflow:', error);
      
      // Build error summary
      const endTime = Date.now();
      const averageConfirmationTimeMs = confirmationTimes.length > 0
        ? confirmationTimes.reduce((sum, time) => sum + time, 0) / confirmationTimes.length
        : 0;
      
      const summary: IntegrationSummary = {
        networkType: 'mainnet',
        startTime,
        endTime,
        totalOperations,
        confirmedOperations,
        failedOperations,
        skippedOperations,
        totalAmount,
        feesCollected,
        averageConfirmationTimeMs,
        error: error instanceof Error ? error.message : String(error)
      };
      
      return summary;
    }
  }

  /**
   * Create a new mother wallet
   * @param force Whether to force creation even if a wallet already exists
   * @returns The mother wallet
   */
  private async createMotherWallet(force: boolean = false): Promise<Keypair> {
    // Use a custom file path for the mainnet mother wallet
    const motherWalletPath = path.join(this.walletStoragePath, 'mother-wallet.json');
    
    // Check if the wallet already exists
    if (!force && fs.existsSync(motherWalletPath)) {
      throw new Error('Mother wallet already exists. Use force=true to overwrite.');
    }
    
    // Create a new keypair
    const keypair = Keypair.generate();
    
    // Save the keypair
    fs.writeFileSync(
      motherWalletPath,
      JSON.stringify(Array.from(keypair.secretKey)),
      'utf-8'
    );
    
    console.log(`Mother wallet created and saved to ${motherWalletPath}`);
    return keypair;
  }

  /**
   * Get existing mother wallet or create a new one
   */
  private async getOrCreateMotherWallet(): Promise<Keypair> {
    // Check for existing wallet
    const motherWalletPath = path.join(this.walletStoragePath, 'mother-wallet.json');
    
    if (fs.existsSync(motherWalletPath)) {
      console.log('Using existing mother wallet');
      // Load the wallet
      const secretKeyString = fs.readFileSync(motherWalletPath, 'utf-8');
      const secretKey = Uint8Array.from(JSON.parse(secretKeyString));
      return Keypair.fromSecretKey(secretKey);
    } else {
      console.log('Creating new mother wallet');
      return this.createMotherWallet();
    }
  }

  /**
   * Create child wallets
   * @param motherWallet Mother wallet keypair
   * @param count Number of child wallets to create
   * @returns The child wallet keypairs
   */
  private async createChildWallets(motherWallet: Keypair, count: number): Promise<Keypair[]> {
    // Create a specified number of child wallets
    const childWallets: Keypair[] = [];
    const childWalletsPath = path.join(this.walletStoragePath, 'child-wallets.json');
    
    for (let i = 0; i < count; i++) {
      // Simply generate new keypairs (in a real app, might use derivation paths)
      childWallets.push(Keypair.generate());
    }
    
    // Save the child wallets
    fs.writeFileSync(
      childWalletsPath,
      JSON.stringify(childWallets.map(wallet => Array.from(wallet.secretKey))),
      'utf-8'
    );
    
    console.log(`${count} child wallets created and saved to ${childWalletsPath}`);
    return childWallets;
  }

  /**
   * Get existing child wallets or create new ones
   * @param motherWallet Mother wallet keypair
   * @param count Number of child wallets needed
   */
  private async getOrCreateChildWallets(motherWallet: Keypair, count: number): Promise<Keypair[]> {
    // Check for existing child wallets
    const childWalletsPath = path.join(this.walletStoragePath, 'child-wallets.json');
    
    if (fs.existsSync(childWalletsPath)) {
      // Load existing wallets
      const childWalletsData = fs.readFileSync(childWalletsPath, 'utf-8');
      const childWalletsKeys = JSON.parse(childWalletsData);
      const existingWallets = childWalletsKeys.map((key: number[]) => 
        Keypair.fromSecretKey(Uint8Array.from(key))
      );
      
      // If we have enough, return them
      if (existingWallets.length >= count) {
        console.log(`Using ${count} existing child wallets`);
        return existingWallets.slice(0, count);
      }
      
      // If we need more, create additional ones
      console.log(`Using ${existingWallets.length} existing child wallets and creating ${count - existingWallets.length} new ones`);
      
      const newWallets: Keypair[] = [];
      for (let i = 0; i < count - existingWallets.length; i++) {
        newWallets.push(Keypair.generate());
      }
      
      // Save all wallets
      fs.writeFileSync(
        childWalletsPath,
        JSON.stringify([...existingWallets, ...newWallets].map(wallet => Array.from(wallet.secretKey))),
        'utf-8'
      );
      
      return [...existingWallets, ...newWallets];
    } else {
      // Create new child wallets
      console.log(`Creating ${count} new child wallets`);
      return this.createChildWallets(motherWallet, count);
    }
  }

  /**
   * Fund a wallet with SOL
   * @param fromWallet Source wallet
   * @param toPublicKey Destination public key
   * @param amount Amount in lamports
   * @returns Transaction signature
   */
  private async fundWallet(
    fromWallet: Keypair,
    toPublicKey: PublicKey,
    amount: bigint
  ): Promise<string> {
    // Create a SOL transfer instruction
    const instruction = SystemProgram.transfer({
      fromPubkey: fromWallet.publicKey,
      toPubkey: toPublicKey,
      lamports: Number(amount)
    });
    
    // Execute the transaction directly using the rpcClient
    const { blockhash, lastValidBlockHeight } = await this.rpcClient.getLatestBlockhash();
    
    const transaction = new Transaction({
      feePayer: fromWallet.publicKey,
      blockhash,
      lastValidBlockHeight: Number(lastValidBlockHeight)
    }).add(instruction);
    
    // Sign the transaction
    transaction.sign(fromWallet);
    
    // Send and confirm the transaction
    const signature = await this.rpcClient.sendTransaction(transaction, {
      skipPreflight: false,
      preflightCommitment: 'confirmed'
    });
    
    await this.rpcClient.confirmTransaction(
      { signature, blockhash, lastValidBlockHeight: Number(lastValidBlockHeight) },
      'confirmed'
    );
    
    return signature;
  }

  /**
   * Execute a schedule of transfer operations
   * @param childWallets Array of child wallet keypairs
   * @param operations Array of transfer operations to execute
   * @returns Results of the operations
   */
  private async executeTransferSchedule(
    childWallets: Keypair[],
    operations: TransferOperation[]
  ): Promise<OperationResult[]> {
    const results: OperationResult[] = [];
    
    // Create a map of public keys to wallet keypairs for quick lookup
    const walletMap = new Map<string, Keypair>();
    childWallets.forEach(wallet => {
      walletMap.set(wallet.publicKey.toBase58(), wallet);
    });
    
    // Execute each operation
    for (let i = 0; i < operations.length; i++) {
      const operation = operations[i];
      console.log(`\nExecuting operation ${i + 1}/${operations.length}:`);
      console.log(`From: ${operation.from.toBase58()}`);
      console.log(`To: ${operation.to.toBase58()}`);
      console.log(`Amount: ${Number(operation.amount) / LAMPORTS_PER_SOL} SOL`);
      
      // Find the wallet keypair for the sender
      const fromWallet = walletMap.get(operation.from.toBase58());
      if (!fromWallet) {
        console.error('Sender wallet not found in available wallets');
        
        results.push({
          opIndex: i,
          status: OperationStatus.SKIPPED,
          error: 'Sender wallet not found'
        });
        
        continue;
      }
      
      // Check if the sender has enough balance
      try {
        const balance = await this.connection.getBalance(operation.from);
        console.log(`Sender balance: ${balance / LAMPORTS_PER_SOL} SOL`);
        
        if (balance < Number(operation.amount) + 5000) { // Add buffer for fees
          console.warn('Insufficient balance for transfer');
          
          results.push({
            opIndex: i,
            status: OperationStatus.SKIPPED,
            error: 'Insufficient balance'
          });
          
          continue;
        }
        
        // Execute the transfer
        const startTime = Date.now();
        let txResult;
        try {
          // Create instruction
          const instruction = SystemProgram.transfer({
            fromPubkey: fromWallet.publicKey,
            toPubkey: operation.to,
            lamports: Number(operation.amount)
          });
          
          // Create transaction
          const { blockhash, lastValidBlockHeight } = await this.rpcClient.getLatestBlockhash();
          
          const transaction = new Transaction({
            feePayer: fromWallet.publicKey,
            blockhash,
            lastValidBlockHeight: Number(lastValidBlockHeight)
          }).add(instruction);
          
          // Sign transaction
          transaction.sign(fromWallet);
          
          // Send transaction
          const signature = await this.rpcClient.sendTransaction(transaction, {
            skipPreflight: false,
            preflightCommitment: 'confirmed'
          });
          
          // Confirm transaction
          await this.rpcClient.confirmTransaction(
            { signature, blockhash, lastValidBlockHeight: Number(lastValidBlockHeight) },
            'confirmed'
          );
          
          // Construct result object
          txResult = {
            signature,
            status: 'confirmed',
            error: undefined
          };
        } catch (error) {
          console.error('Transaction failed:', error);
          txResult = {
            signature: '',
            status: 'failed',
            error: error instanceof Error ? error.message : String(error)
          };
        }
        const endTime = Date.now();
        
        console.log(`Transaction sent: ${txResult.signature}`);
        console.log(`Status: ${txResult.status}`);
        
        // Store result
        results.push({
          opIndex: i,
          status: txResult.status === 'confirmed' ? OperationStatus.CONFIRMED : OperationStatus.FAILED,
          signature: txResult.signature,
          confirmationTime: endTime - startTime,
          error: txResult.error
        });
        
      } catch (error) {
        console.error('Error executing transfer:', error);
        
        results.push({
          opIndex: i,
          status: OperationStatus.FAILED,
          error: error instanceof Error ? error.message : String(error)
        });
      }
    }
    
    return results;
  }
}

// Export a default instance for convenience
export const mainnetIntegration = new MainnetIntegration(); 