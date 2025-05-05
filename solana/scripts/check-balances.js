#!/usr/bin/env node
/**
 * Check the balances of wallets used in the mainnet tests
 */
const { Connection, PublicKey, LAMPORTS_PER_SOL } = require('@solana/web3.js');
const fs = require('fs');
const path = require('path');

async function main() {
  try {
    console.log('===== CHECKING WALLET BALANCES =====');
    
    // Set up mainnet connection
    const mainnetUrl = 'https://api.mainnet-beta.solana.com';
    const connection = new Connection(mainnetUrl);
    console.log(`Using mainnet URL: ${mainnetUrl}`);
    
    // Set wallet storage path
    const mainnetWalletPath = path.join(process.cwd(), 'wallet-storage', 'mainnet');
    console.log(`Wallet storage path: ${mainnetWalletPath}\n`);
    
    // Load wallets
    let motherAddress = '';
    let childAddresses = [];
    
    // Check for mother wallet
    const motherWalletPath = path.join(mainnetWalletPath, 'mother-wallet.json');
    if (fs.existsSync(motherWalletPath)) {
      const motherKeyData = fs.readFileSync(motherWalletPath, 'utf-8');
      const motherSecretKey = Uint8Array.from(JSON.parse(motherKeyData));
      const motherWallet = { publicKey: new PublicKey(motherSecretKey.slice(32, 64)) };
      motherAddress = motherWallet.publicKey.toBase58();
    }
    
    // Check for child wallets
    const childWalletsPath = path.join(mainnetWalletPath, 'child-wallets.json');
    if (fs.existsSync(childWalletsPath)) {
      const childKeysData = fs.readFileSync(childWalletsPath, 'utf-8');
      const childKeys = JSON.parse(childKeysData);
      childAddresses = childKeys.map(keyData => {
        const childSecretKey = Uint8Array.from(keyData);
        return new PublicKey(childSecretKey.slice(32, 64)).toBase58();
      });
    }
    
    // Check balances
    console.log('Mother wallet:');
    if (motherAddress) {
      try {
        const balance = await connection.getBalance(new PublicKey(motherAddress));
        console.log(`  ${motherAddress}: ${balance / LAMPORTS_PER_SOL} SOL`);
      } catch (error) {
        console.error(`  Error getting balance for mother wallet: ${error.message}`);
      }
    } else {
      console.log('  No mother wallet found');
    }
    
    console.log('\nChild wallets:');
    if (childAddresses.length > 0) {
      for (let i = 0; i < childAddresses.length; i++) {
        try {
          const balance = await connection.getBalance(new PublicKey(childAddresses[i]));
          console.log(`  Child ${i + 1}: ${childAddresses[i]}: ${balance / LAMPORTS_PER_SOL} SOL`);
        } catch (error) {
          console.error(`  Error getting balance for child wallet ${i + 1}: ${error.message}`);
        }
      }
    } else {
      console.log('  No child wallets found');
    }
  } catch (error) {
    console.error('Error checking balances:', error);
    process.exit(1);
  }
}

// Run the main function
main().catch(err => {
  console.error('Unhandled error:', err);
  process.exit(1);
}); 