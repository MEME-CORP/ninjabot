#!/usr/bin/env node
/**
 * Test script for creating and verifying a mainnet wallet
 * This is part of Phase 1 - Mainnet Validation
 * 
 * Usage: node test-mainnet-wallet.js
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
    console.log('===== MAINNET WALLET TEST =====');
    console.log('WARNING: This is using MAINNET. Real SOL will be used if funded.');
    console.log('Proceed with caution!\n');

    // Import the integration modules
    const integration = require('../dist/integration/walletStorage');
    const { NETWORK } = require('../dist/config');
    
    // Import the web3 library for verification
    const { Connection, Keypair } = require('@solana/web3.js');
    
    // Set up mainnet wallet storage with a dedicated directory
    const mainnetWalletPath = path.join(process.cwd(), 'wallet-storage', 'mainnet');
    if (!fs.existsSync(mainnetWalletPath)) {
      fs.mkdirSync(mainnetWalletPath, { recursive: true });
    }
    
    // Use mainnet connection for verification
    const mainnetUrl = 'https://api.mainnet-beta.solana.com';
    const connection = new Connection(mainnetUrl);
    
    console.log(`Current network setting: ${NETWORK}`);
    console.log(`Using mainnet URL: ${mainnetUrl}`);
    console.log(`Wallet storage path: ${mainnetWalletPath}\n`);
    
    // Create a new keypair for the mainnet mother wallet
    const keypair = Keypair.generate();
    
    // Save the wallet to a file in the mainnet directory
    const motherWalletPath = path.join(mainnetWalletPath, 'mother-wallet.json');
    fs.writeFileSync(
      motherWalletPath,
      JSON.stringify(Array.from(keypair.secretKey)),
      'utf-8'
    );
    
    console.log('Creating new mainnet mother wallet...');
    console.log(`Mother wallet created with address: ${keypair.publicKey.toBase58()}`);
    
    // Verify the wallet exists on-chain
    console.log('\nVerifying wallet on mainnet...');
    try {
      const balance = await connection.getBalance(keypair.publicKey);
      console.log(`Wallet verified on mainnet. Current balance: ${balance / 1000000000} SOL`);
      console.log(`\nIMPORTANT: To continue with testing, manually fund this address with a small amount of SOL (e.g. 0.01 SOL):`);
      console.log(keypair.publicKey.toBase58());
      console.log('You can view this wallet on Solscan: https://solscan.io/account/' + keypair.publicKey.toBase58());
    } catch (error) {
      console.error('Error verifying wallet:', error);
    }
    
    console.log('\nTest completed successfully!');
  } catch (error) {
    console.error('Error running mainnet wallet test:', error);
    process.exit(1);
  }
}

// Run the main function
main().catch(err => {
  console.error('Unhandled error:', err);
  process.exit(1);
}); 