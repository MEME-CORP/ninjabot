#!/usr/bin/env node
/**
 * Script to check a wallet balance on Solana devnet
 * 
 * This is a helper script that can be used to check mother
 * or child wallet balances after running the integration
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
    // Import the integration manager
    const { defaultIntegrationManager, loadMotherWallet, loadChildWallets } = require('../dist/integration');
    
    // Parse command line arguments
    const args = process.argv.slice(2);
    let walletAddress;
    
    // Check for the specified wallet to check
    if (args.length > 0) {
      if (args[0] === '--mother' || args[0] === '-m') {
        // Check mother wallet
        const motherWallet = loadMotherWallet();
        if (!motherWallet) {
          console.error('Mother wallet not found. Please run the integration script first to create wallets.');
          process.exit(1);
        }
        walletAddress = motherWallet.publicKey;
        console.log(`Checking mother wallet: ${walletAddress}`);
      } else if (args[0] === '--child' || args[0] === '-c') {
        // Check specific child wallet by index
        const index = args[1] ? parseInt(args[1], 10) : 0;
        const childWallets = loadChildWallets();
        if (!childWallets || childWallets.length === 0) {
          console.error('No child wallets found. Please run the integration script first to create wallets.');
          process.exit(1);
        }
        if (index < 0 || index >= childWallets.length) {
          console.error(`Invalid child index: ${index}. Available indices are 0-${childWallets.length - 1}`);
          process.exit(1);
        }
        walletAddress = childWallets[index].publicKey;
        console.log(`Checking child wallet ${index}: ${walletAddress}`);
      } else if (args[0] === '--all' || args[0] === '-a') {
        // Check all wallets
        await checkAllWallets(defaultIntegrationManager, loadMotherWallet, loadChildWallets);
        return;
      } else {
        // Use the argument as a direct address
        walletAddress = args[0];
        console.log(`Checking wallet: ${walletAddress}`);
      }
    } else {
      console.log('No wallet specified. Checking all wallets...');
      await checkAllWallets(defaultIntegrationManager, loadMotherWallet, loadChildWallets);
      return;
    }
    
    // Check the balance
    const balance = await defaultIntegrationManager.checkBalance(walletAddress);
    console.log(`Balance: ${balance} SOL`);
    
  } catch (error) {
    console.error('Error checking balance:', error);
    process.exit(1);
  }
}

async function checkAllWallets(integrationManager, loadMotherWallet, loadChildWallets) {
  console.log('=== Wallet Balances ===');
  
  // Check mother wallet balance
  const motherWallet = loadMotherWallet();
  if (motherWallet) {
    const motherBalance = await integrationManager.checkBalance(motherWallet.publicKey);
    console.log(`Mother Wallet: ${motherWallet.publicKey}`);
    console.log(`Balance: ${motherBalance} SOL`);
    console.log('---------------------');
  } else {
    console.log('No mother wallet found');
  }
  
  // Check all child wallets
  const childWallets = loadChildWallets();
  if (childWallets && childWallets.length > 0) {
    console.log(`Child Wallets (${childWallets.length}):`);
    for (let i = 0; i < childWallets.length; i++) {
      const child = childWallets[i];
      const childBalance = await integrationManager.checkBalance(child.publicKey);
      console.log(`Child ${i}: ${child.publicKey}`);
      console.log(`Balance: ${childBalance} SOL`);
      console.log('---------------------');
    }
  } else {
    console.log('No child wallets found');
  }
}

function showHelp() {
  console.log(`
Usage: node check-balance.js [options]

Options:
  --mother, -m       Check mother wallet balance
  --child, -c [n]    Check child wallet balance at index n (default: 0)
  --all, -a          Check all wallet balances
  <address>          Check balance of a specific address
  --help, -h         Show this help message
  
Example:
  node check-balance.js -m          # Check mother wallet
  node check-balance.js -c 2        # Check child wallet at index 2
  node check-balance.js -a          # Check all wallets
  node check-balance.js <address>   # Check specific address
`);
}

// Handle --help flag
if (process.argv.includes('--help') || process.argv.includes('-h')) {
  showHelp();
  process.exit(0);
}

// Run the main function
main().catch(err => {
  console.error('Unhandled error:', err);
  process.exit(1);
}); 