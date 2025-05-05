#!/usr/bin/env node
/**
 * Test script for funding child wallets on mainnet
 * This is part of Phase 1 - Mainnet Validation
 * 
 * Usage: node test-mainnet-funding.js [--amount n]
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
    console.log('===== MAINNET WALLET FUNDING TEST =====');
    console.log('WARNING: This script will use REAL SOL from the mainnet mother wallet!');
    console.log('Proceed with caution!\n');

    // Parse command line arguments
    const args = process.argv.slice(2);
    let fundingAmount = 0.002; // Default to 0.002 SOL for rent exemption
    
    for (let i = 0; i < args.length; i++) {
      const arg = args[i].toLowerCase();
      if (arg === '--amount' || arg === '-a') {
        if (i + 1 < args.length) {
          const value = parseFloat(args[i + 1]);
          if (!isNaN(value)) {
            fundingAmount = value;
            i++; // Skip the next argument as it's the value
          }
        }
      }
    }
    
    // Import the web3 library
    const { Connection, Keypair, Transaction, SystemProgram, LAMPORTS_PER_SOL } = require('@solana/web3.js');
    
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
    console.log(`Funding amount per child wallet: ${fundingAmount} SOL\n`);
    
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
    
    console.log(`Using mother wallet: ${motherWallet.publicKey.toBase58()}`);
    
    // Get mother wallet balance
    const balance = await connection.getBalance(motherWallet.publicKey);
    const balanceInSol = balance / LAMPORTS_PER_SOL;
    console.log(`Mother wallet balance: ${balanceInSol} SOL`);
    
    // Load child wallets
    const childKeysData = fs.readFileSync(childWalletsPath, 'utf-8');
    const childKeys = JSON.parse(childKeysData);
    const childWallets = childKeys.map(keyData => Keypair.fromSecretKey(Uint8Array.from(keyData)));
    
    console.log(`Found ${childWallets.length} child wallets to fund`);
    
    // Check if mother wallet has enough balance
    const totalFundingAmount = fundingAmount * childWallets.length;
    const estimatedFees = 0.000005 * childWallets.length; // Rough estimate of transaction fees
    const totalRequired = totalFundingAmount + estimatedFees;
    
    if (balanceInSol < totalRequired) {
      console.error(`Error: Insufficient funds in mother wallet. Need at least ${totalRequired} SOL, but only have ${balanceInSol} SOL.`);
      process.exit(1);
    }
    
    // Fund each child wallet
    console.log('\nFunding child wallets:');
    for (let i = 0; i < Math.min(2, childWallets.length); i++) { // Only fund the first 2 wallets
      const wallet = childWallets[i];
      console.log(`Funding wallet ${i + 1}/2: ${wallet.publicKey.toBase58()}`);
      
      try {
        // Convert SOL to lamports (1 SOL = 1,000,000,000 lamports)
        const amountLamports = Math.floor(fundingAmount * LAMPORTS_PER_SOL);
        
        // Create a transfer instruction
        const instruction = SystemProgram.transfer({
          fromPubkey: motherWallet.publicKey,
          toPubkey: wallet.publicKey,
          lamports: amountLamports,
        });
        
        // Get recent blockhash with retry logic
        console.log('Getting recent blockhash...');
        const { blockhash, lastValidBlockHeight } = await retry(async () => {
          return await connection.getLatestBlockhash('confirmed');
        });
        
        console.log(`Got blockhash: ${blockhash}`);
        
        // Create transaction
        const transaction = new Transaction({
          feePayer: motherWallet.publicKey,
          blockhash,
          lastValidBlockHeight
        }).add(instruction);
        
        // Sign transaction
        transaction.sign(motherWallet);
        
        // Add delay between transactions to avoid rate limiting
        if (i > 0) {
          console.log('Adding delay before sending transaction...');
          await delay(2000);
        }
        
        // Send transaction with retry
        console.log('Sending transaction...');
        const signature = await retry(async () => {
          return await connection.sendTransaction(transaction, [motherWallet]);
        });
        
        console.log(`Funding transaction sent: ${signature}`);
        console.log(`Transaction Explorer: https://solscan.io/tx/${signature}`);
        
        // Wait for confirmation with retry
        console.log('Waiting for confirmation...');
        const confirmation = await retry(async () => {
          return await connection.confirmTransaction({
            signature,
            blockhash,
            lastValidBlockHeight
          }, 'confirmed');
        });
        
        if (confirmation.value.err) {
          console.error(`Funding failed: ${confirmation.value.err}`);
        } else {
          console.log('Funding confirmed successfully!');
          
          // Get updated balance
          const childBalance = await connection.getBalance(wallet.publicKey);
          console.log(`New balance: ${childBalance / LAMPORTS_PER_SOL} SOL`);
        }
      } catch (error) {
        console.error(`Error funding wallet ${i + 1}:`, error);
      }
    }
    
    // Get final mother wallet balance
    const finalBalance = await connection.getBalance(motherWallet.publicKey);
    console.log(`\nFinal mother wallet balance: ${finalBalance / LAMPORTS_PER_SOL} SOL`);
    
    console.log('\nFunding test completed.');
    console.log('Next step: Run test-mainnet-transfer.js to test transfers between child wallets');
    
  } catch (error) {
    console.error('Error running funding test:', error);
    process.exit(1);
  }
}

// Run the main function
main().catch(err => {
  console.error('Unhandled error:', err);
  process.exit(1);
}); 