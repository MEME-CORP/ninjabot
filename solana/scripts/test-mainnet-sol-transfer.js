#!/usr/bin/env node
/**
 * Test script for SOL transfers between child wallets on mainnet
 * This is part of Phase 1 - Mainnet Validation
 * 
 * Usage: node test-mainnet-sol-transfer.js [--amount n] [--from i] [--to j]
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
    console.log('===== MAINNET SOL TRANSFER TEST =====');
    console.log('WARNING: This script will transfer REAL SOL between mainnet wallets!');
    console.log('Proceed with caution!\n');

    // Parse command line arguments
    const args = process.argv.slice(2);
    let transferAmount = 0.0001; // Default to a very small amount (in SOL)
    let fromIndex = 0;
    let toIndex = 1;
    
    for (let i = 0; i < args.length; i++) {
      const arg = args[i].toLowerCase();
      if (arg === '--amount' || arg === '-a') {
        transferAmount = parseFloat(args[++i]);
      } else if (arg === '--from' || arg === '-f') {
        fromIndex = parseInt(args[++i], 10);
      } else if (arg === '--to' || arg === '-t') {
        toIndex = parseInt(args[++i], 10);
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
    console.log(`Transfer amount: ${transferAmount} SOL`);
    console.log(`From wallet index: ${fromIndex}`);
    console.log(`To wallet index: ${toIndex}\n`);
    
    // Check if child wallets exist
    const childWalletsPath = path.join(mainnetWalletPath, 'child-wallets.json');
    if (!fs.existsSync(childWalletsPath)) {
      console.error('Error: Child wallets not found. Run test-mainnet-child-wallets.js first.');
      process.exit(1);
    }
    
    // Load child wallets
    const childKeysData = fs.readFileSync(childWalletsPath, 'utf-8');
    const childKeys = JSON.parse(childKeysData);
    const childWallets = childKeys.map(keyData => Keypair.fromSecretKey(Uint8Array.from(keyData)));
    
    if (fromIndex >= childWallets.length || toIndex >= childWallets.length) {
      console.error(`Error: Invalid wallet index. Only have ${childWallets.length} wallets (0-${childWallets.length - 1}).`);
      process.exit(1);
    }
    
    if (fromIndex === toIndex) {
      console.error('Error: From and to wallet indices must be different.');
      process.exit(1);
    }
    
    const fromWallet = childWallets[fromIndex];
    const toWallet = childWallets[toIndex];
    
    console.log(`From wallet: ${fromWallet.publicKey.toBase58()}`);
    console.log(`To wallet: ${toWallet.publicKey.toBase58()}`);
    
    // Check balances
    const fromBalance = await retry(async () => await connection.getBalance(fromWallet.publicKey));
    const toBalance = await retry(async () => await connection.getBalance(toWallet.publicKey));
    
    console.log(`From wallet balance: ${fromBalance / LAMPORTS_PER_SOL} SOL`);
    console.log(`To wallet balance: ${toBalance / LAMPORTS_PER_SOL} SOL`);
    
    // Convert SOL to lamports
    const transferLamports = Math.floor(transferAmount * LAMPORTS_PER_SOL);
    
    if (fromBalance < transferLamports + 5000) { // 5000 lamports for fees
      console.error(`Error: Insufficient funds in source wallet. Need at least ${(transferLamports + 5000) / LAMPORTS_PER_SOL} SOL, but only have ${fromBalance / LAMPORTS_PER_SOL} SOL.`);
      process.exit(1);
    }
    
    // Create transaction
    console.log('\nCreating transfer transaction...');
    const instruction = SystemProgram.transfer({
      fromPubkey: fromWallet.publicKey,
      toPubkey: toWallet.publicKey,
      lamports: transferLamports
    });
    
    // Get recent blockhash with retry logic
    console.log('Getting recent blockhash...');
    const { blockhash, lastValidBlockHeight } = await retry(async () => {
      return await connection.getLatestBlockhash('confirmed');
    });
    
    // Create transaction with blockhash
    const transaction = new Transaction({
      feePayer: fromWallet.publicKey,
      blockhash,
      lastValidBlockHeight
    }).add(instruction);
    
    // Sign the transaction
    transaction.sign(fromWallet);
    
    // Execute transaction
    console.log('Sending transaction...');
    try {
      const startTime = Date.now();
      
      // Send transaction with retry
      const signature = await retry(async () => {
        return await connection.sendTransaction(transaction, [fromWallet]);
      });
      
      console.log(`Transaction sent: ${signature}`);
      console.log(`Transaction Explorer: https://solscan.io/tx/${signature}`);
      
      // Wait for confirmation with retry
      console.log('Waiting for confirmation...');
      const result = await retry(async () => {
        return await connection.confirmTransaction({
          signature,
          blockhash,
          lastValidBlockHeight
        }, 'confirmed');
      });
      
      const endTime = Date.now();
      
      console.log(`Status: ${result.value.err ? 'failed' : 'confirmed'}`);
      console.log(`Processing time: ${endTime - startTime}ms`);
      
      // Check final balances
      console.log('\nVerifying final balances...');
      const finalFromBalance = await retry(async () => await connection.getBalance(fromWallet.publicKey));
      const finalToBalance = await retry(async () => await connection.getBalance(toWallet.publicKey));
      
      console.log(`New from wallet balance: ${finalFromBalance / LAMPORTS_PER_SOL} SOL`);
      console.log(`New to wallet balance: ${finalToBalance / LAMPORTS_PER_SOL} SOL`);
      
      // Calculate balance changes
      const fromBalanceChange = (finalFromBalance - fromBalance) / LAMPORTS_PER_SOL;
      const toBalanceChange = (finalToBalance - toBalance) / LAMPORTS_PER_SOL;
      
      console.log(`From wallet balance change: ${fromBalanceChange} SOL`);
      console.log(`To wallet balance change: ${toBalanceChange} SOL`);
      
      // Verify transfer was successful
      if (finalToBalance > toBalance && Math.abs((finalToBalance - toBalance) - transferLamports) < 10) { // Allow for small rounding errors
        console.log('\nTransfer SUCCESSFUL! ✅');
      } else {
        console.warn('\nTransfer may have failed or had unexpected results. Please check the transaction on Solscan.');
      }
    } catch (error) {
      console.error('Error executing transaction:', error);
    }
    
    console.log('\nTransfer test completed.');
    console.log('Next step: Run test-mainnet-return-funds.js to return funds to the mother wallet.');
    
  } catch (error) {
    console.error('Error running transfer test:', error);
    process.exit(1);
  }
}

// Run the main function
main().catch(err => {
  console.error('Unhandled error:', err);
  process.exit(1);
}); 