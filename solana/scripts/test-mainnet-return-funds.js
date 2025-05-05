#!/usr/bin/env node
/**
 * Test script for returning funds from child wallets to mother wallet on mainnet
 * This is part of Phase 1 - Mainnet Validation
 * 
 * Usage: node test-mainnet-return-funds.js [--reserve n]
 */
const path = require('path');
const fs = require('fs');

// Ensure the dist directory exists
const distPath = path.join(__dirname, '../dist');
if (!fs.existsSync(distPath)) {
  console.error('Error: dist directory not found. Please run "npm run build" first.');
  process.exit(1);
}

// Helper function to add delay between requests
const delay = (ms) => new Promise(resolve => setTimeout(resolve, ms));

// Helper function to retry operations with exponential backoff
async function retry(fn, maxRetries = 3, initialDelay = 1000) {
  let lastError;
  for (let i = 0; i < maxRetries; i++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;
      const waitTime = initialDelay * Math.pow(2, i);
      console.log(`Attempt ${i + 1} failed. Retrying in ${waitTime}ms...`);
      await delay(waitTime);
    }
  }
  throw lastError;
}

async function main() {
  try {
    console.log('===== MAINNET RETURN FUNDS TEST =====');
    console.log('WARNING: This script will transfer REAL SOL from child wallets back to mother wallet!');
    console.log('Proceed with caution!\n');

    // Parse command line arguments
    const args = process.argv.slice(2);
    let reserveAmount = 0.00005; // Default amount to leave in each wallet for rent exemption (in SOL)
    
    for (let i = 0; i < args.length; i++) {
      const arg = args[i].toLowerCase();
      if (arg === '--reserve' || arg === '-r') {
        if (i + 1 < args.length) {
          const value = parseFloat(args[i + 1]);
          if (!isNaN(value)) {
            reserveAmount = value;
          }
          i++; // Skip the next argument as it's the value
        }
      }
    }
    
    // Import the web3 library
    const { Connection, Keypair, LAMPORTS_PER_SOL, SystemProgram, Transaction } = require('@solana/web3.js');
    
    // Set up mainnet connection and wallet storage path
    const mainnetUrl = 'https://api.mainnet-beta.solana.com';
    const connection = new Connection(mainnetUrl);
    const mainnetWalletPath = path.join(process.cwd(), 'wallet-storage', 'mainnet');
    
    if (!fs.existsSync(mainnetWalletPath)) {
      console.error('Error: Mainnet wallet directory not found. Run test-mainnet-wallet.js first.');
      process.exit(1);
    }
    
    console.log(`Using mainnet URL: ${mainnetUrl}`);
    console.log(`Wallet storage path: ${mainnetWalletPath}`);
    console.log(`Amount to reserve in each wallet: ${reserveAmount} SOL\n`);
    
    // Check if mother wallet exists
    const motherWalletPath = path.join(mainnetWalletPath, 'mother-wallet.json');
    if (!fs.existsSync(motherWalletPath)) {
      console.error('Error: Mother wallet not found. Run test-mainnet-wallet.js first.');
      process.exit(1);
    }
    
    // Check if child wallets exist
    const childWalletsPath = path.join(mainnetWalletPath, 'child-wallets.json');
    if (!fs.existsSync(childWalletsPath)) {
      console.error('Error: Child wallets not found. Run test-mainnet-child-wallets.js first.');
      process.exit(1);
    }
    
    // Load mother wallet
    const motherKeyData = fs.readFileSync(motherWalletPath, 'utf-8');
    const motherSecretKey = Uint8Array.from(JSON.parse(motherKeyData));
    const motherWallet = Keypair.fromSecretKey(motherSecretKey);
    
    console.log(`Mother wallet: ${motherWallet.publicKey.toBase58()}`);
    
    // Load child wallets
    const childKeysData = fs.readFileSync(childWalletsPath, 'utf-8');
    const childKeys = JSON.parse(childKeysData);
    const childWallets = childKeys.map(keyData => Keypair.fromSecretKey(Uint8Array.from(keyData)));
    
    console.log(`Found ${childWallets.length} child wallets\n`);
    
    // Get mother wallet initial balance
    const initialMotherBalance = await retry(async () => await connection.getBalance(motherWallet.publicKey));
    console.log(`Mother wallet initial balance: ${initialMotherBalance / LAMPORTS_PER_SOL} SOL`);
    
    // Calculate reserve amount in lamports
    const reserveLamports = Math.floor(reserveAmount * LAMPORTS_PER_SOL);
    
    // Return funds from each child wallet
    console.log('\nReturning funds from child wallets:');
    let totalReturned = 0;
    let successCount = 0;
    
    // Only process the first 2 child wallets (that we funded)
    for (let i = 0; i < Math.min(2, childWallets.length); i++) {
      const wallet = childWallets[i];
      const walletAddress = wallet.publicKey.toBase58();
      
      console.log(`\n[${i + 1}/2] Processing wallet: ${walletAddress}`);
      
      try {
        // Get wallet balance
        const balance = await retry(async () => await connection.getBalance(wallet.publicKey));
        console.log(`Balance: ${balance / LAMPORTS_PER_SOL} SOL`);
        
        if (balance <= 0) {
          console.log(`Skipping wallet with zero balance.`);
          continue;
        }
        
        // Calculate amount to return (total balance minus fee buffer)
        // We'll return all funds since we want to completely close the account
        const feeBuffer = 5000; // lamports for transaction fee
        const returnAmount = balance - feeBuffer;
        
        if (returnAmount <= 0) {
          console.log(`Skipping wallet with insufficient balance for transfer.`);
          continue;
        }
        
        console.log(`Returning ${returnAmount / LAMPORTS_PER_SOL} SOL to mother wallet...`);
        
        // Create transfer instruction
        const instruction = SystemProgram.transfer({
          fromPubkey: wallet.publicKey,
          toPubkey: motherWallet.publicKey,
          lamports: returnAmount
        });
        
        // Get recent blockhash with retry logic
        console.log('Getting recent blockhash...');
        const { blockhash, lastValidBlockHeight } = await retry(async () => {
          return await connection.getLatestBlockhash('finalized'); // Using finalized commitment for better confirmation
        });
        
        // Create transaction with blockhash
        const transaction = new Transaction({
          feePayer: wallet.publicKey,
          blockhash,
          lastValidBlockHeight
        }).add(instruction);
        
        // Sign the transaction
        transaction.sign(wallet);
        
        // Add delay between transactions to avoid rate limiting
        if (i > 0) {
          console.log('Adding delay before sending transaction...');
          await delay(5000); // Increased delay to 5 seconds
        }
        
        // Send transaction with retry - using confirmed commitment level
        console.log('Sending transaction...');
        const signature = await retry(async () => {
          return await connection.sendTransaction(transaction, [wallet], {
            skipPreflight: false,
            preflightCommitment: 'confirmed',
            maxRetries: 5
          });
        });
        
        console.log(`Transaction sent: ${signature}`);
        console.log(`Transaction Explorer: https://solscan.io/tx/${signature}`);
        
        // Wait for confirmation with retry - using finalized commitment for higher reliability
        console.log('Waiting for confirmation...');
        const result = await retry(async () => {
          return await connection.confirmTransaction({
            signature,
            blockhash,
            lastValidBlockHeight
          }, 'finalized'); // Using finalized commitment for better reliability
        }, 5, 2000); // 5 retries with 2 second initial delay
        
        const status = result.value.err ? 'failed' : 'confirmed';
        console.log(`Status: ${status}`);
        
        // Verify the transfer
        if (status === 'confirmed') {
          console.log(`Successfully returned ${returnAmount / LAMPORTS_PER_SOL} SOL from wallet ${i}`);
          totalReturned += returnAmount;
          successCount++;
        } else {
          console.warn(`Transfer from wallet ${i} may have failed. Please check the transaction on Solscan.`);
        }
      } catch (error) {
        console.error(`Error returning funds from wallet ${i}:`, error);
      }
    }
    
    // Get mother wallet final balance
    const finalMotherBalance = await retry(async () => await connection.getBalance(motherWallet.publicKey));
    const motherBalanceChange = finalMotherBalance - initialMotherBalance;
    
    console.log('\nReturn funds summary:');
    console.log(`Successful transfers: ${successCount}/${childWallets.length}`);
    console.log(`Total amount returned: ${totalReturned / LAMPORTS_PER_SOL} SOL`);
    console.log(`Mother wallet balance change: ${motherBalanceChange / LAMPORTS_PER_SOL} SOL`);
    console.log(`Mother wallet final balance: ${finalMotherBalance / LAMPORTS_PER_SOL} SOL`);
    
    if (Math.abs(motherBalanceChange - totalReturned) > 10) { // Allow for small rounding errors
      console.warn('\nWARNING: The mother wallet balance change does not match the total amount returned.');
      console.warn('Some transactions may have failed or there were concurrent transactions.');
    }
    
    console.log('\nReturn funds test completed.');
    
  } catch (error) {
    console.error('Error running return funds test:', error);
    process.exit(1);
  }
}

// Run the main function
main().catch(err => {
  console.error('Unhandled error:', err);
  process.exit(1);
});