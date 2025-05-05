#!/usr/bin/env node
/**
 * Test script for creating child wallets on mainnet
 * This is part of Phase 1 - Mainnet Validation
 * 
 * Usage: node test-mainnet-child-wallets.js [--count n]
 */
const path = require('path');
const fs = require('fs');

// Ensure the dist directory exists
const distPath = path.join(__dirname, '../dist');
if (!fs.existsSync(distPath)) {
  console.error('Error: dist directory not found. Please run "npm run build" first.');
  process.exit(1);
}

async function main() {
  try {
    console.log('===== MAINNET CHILD WALLET GENERATION TEST =====');
    console.log('WARNING: This script will use the mainnet mother wallet.');
    console.log('Make sure you have funded it first by running test-mainnet-wallet.js\n');

    // Parse command line arguments
    const args = process.argv.slice(2);
    let childCount = 3; // Default
    
    for (let i = 0; i < args.length; i++) {
      const arg = args[i].toLowerCase();
      if (arg === '--count' || arg === '-c') {
        childCount = parseInt(args[++i], 10);
      }
    }
    
    // Import the web3 library for verification
    const { Connection, Keypair } = require('@solana/web3.js');
    
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
    console.log(`Generating ${childCount} child wallets\n`);
    
    // Check if mother wallet exists
    const motherWalletPath = path.join(mainnetWalletPath, 'mother-wallet.json');
    if (!fs.existsSync(motherWalletPath)) {
      console.error('Error: Mother wallet not found. Run test-mainnet-wallet.js first.');
      process.exit(1);
    }
    
    // Load mother wallet
    const motherKeyData = fs.readFileSync(motherWalletPath, 'utf-8');
    const motherSecretKey = Uint8Array.from(JSON.parse(motherKeyData));
    const motherWallet = Keypair.fromSecretKey(motherSecretKey);
    
    console.log(`Using mother wallet: ${motherWallet.publicKey.toBase58()}`);
    
    // Check mother wallet balance
    const balance = await connection.getBalance(motherWallet.publicKey);
    console.log(`Mother wallet balance: ${balance / 1000000000} SOL`);
    
    if (balance === 0) {
      console.warn('\nWARNING: Mother wallet has zero balance. You need to fund it before testing transfers.');
    }
    
    // Create child wallets
    console.log('\nGenerating child wallets...');
    const childWallets = [];
    
    for (let i = 0; i < childCount; i++) {
      childWallets.push(Keypair.generate());
    }
    
    // Save child wallets to file
    const childWalletsPath = path.join(mainnetWalletPath, 'child-wallets.json');
    fs.writeFileSync(
      childWalletsPath,
      JSON.stringify(childWallets.map(wallet => Array.from(wallet.secretKey))),
      'utf-8'
    );
    
    console.log('\nChild wallets created:');
    for (let i = 0; i < childWallets.length; i++) {
      const wallet = childWallets[i];
      console.log(`${i + 1}. ${wallet.publicKey.toBase58()}`);
    }
    
    console.log('\nAll child wallets have been generated successfully.');
    console.log('You can view these wallets on Solscan by copying the addresses.');
    console.log('\nNext step: Run test-mainnet-funding.js to fund these wallets with a small amount of SOL.');
    
  } catch (error) {
    console.error('Error generating child wallets:', error);
    process.exit(1);
  }
}

// Run the main function
main().catch(err => {
  console.error('Unhandled error:', err);
  process.exit(1);
}); 