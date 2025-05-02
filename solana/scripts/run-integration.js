#!/usr/bin/env node
/**
 * Script to run the integration workflow on Solana devnet
 * 
 * This script demonstrates the complete workflow:
 * 1. Create mother and child wallets
 * 2. Fund child wallets from mother wallet
 * 3. Generate a transfer schedule
 * 4. Execute the transfers
 */
const path = require('path');
const fs = require('fs');

// Ensure the dist directory exists
const distPath = path.join(__dirname, '../dist');
if (!fs.existsSync(distPath)) {
  console.error('Error: dist directory not found. Please run "npm run build" first.');
  process.exit(1);
}

// Dynamic import from the compiled JS files
async function main() {
  try {
    // Import the integration manager
    const { defaultIntegrationManager } = require('../dist/integration/integrationManager');
    
    // Parse command line arguments
    const args = process.argv.slice(2);
    
    // Default parameters
    let childCount = 3;
    let fundingAmountSol = 0.1;
    let totalVolumeSol = 0.05;
    let tokenMint = null;
    let forceNewMotherWallet = false;
    
    // Parse parameters if provided
    for (let i = 0; i < args.length; i++) {
      const arg = args[i].toLowerCase();
      
      if (arg === '--children' || arg === '-c') {
        childCount = parseInt(args[++i], 10);
      } else if (arg === '--funding' || arg === '-f') {
        fundingAmountSol = parseFloat(args[++i]);
      } else if (arg === '--volume' || arg === '-v') {
        totalVolumeSol = parseFloat(args[++i]);
      } else if (arg === '--token' || arg === '-t') {
        tokenMint = args[++i];
      } else if (arg === '--new-wallet' || arg === '-n') {
        forceNewMotherWallet = true;
      } else if (arg === '--help' || arg === '-h') {
        showHelp();
        return;
      }
    }
    
    console.log(`
==============================================
  NinjaBot Solana Integration Test
==============================================
Parameters:
- Child Wallets: ${childCount}
- Funding per Child: ${fundingAmountSol} SOL
- Total Volume: ${totalVolumeSol} SOL
- Token Mint: ${tokenMint || 'None (using SOL)'}
- Force New Mother Wallet: ${forceNewMotherWallet ? 'Yes' : 'No'}
==============================================
${!tokenMint ? '\nNote: Running in devnet test mode - funds will be returned to mother wallet\n' : ''}
`);
    
    console.log('Starting integration workflow...');
    
    // Run the complete workflow
    const summary = await defaultIntegrationManager.runCompleteWorkflow(
      childCount, 
      fundingAmountSol, 
      totalVolumeSol,
      tokenMint,
      forceNewMotherWallet
    );
    
    // Print summary
    console.log('\nExecution Summary:');
    console.log(`- Network: ${summary.networkType}`);
    console.log(`- Total Operations: ${summary.totalOperations}`);
    console.log(`- Confirmed: ${summary.confirmedOperations}`);
    console.log(`- Failed: ${summary.failedOperations}`);
    console.log(`- Skipped: ${summary.skippedOperations}`);
    console.log(`- Total Amount: ${Number(summary.totalAmount) / 1000000000} SOL`);
    console.log(`- Fees Collected: ${Number(summary.feesCollected) / 1000000000} SOL`);
    console.log(`- Average Confirmation Time: ${summary.averageConfirmationTimeMs}ms`);
    console.log(`- Duration: ${(summary.endTime - summary.startTime) / 1000}s`);
    
    // Save summary to file
    const summaryPath = path.join(process.cwd(), 'integration-summary.json');
    fs.writeFileSync(
      summaryPath, 
      JSON.stringify(summary, (key, value) => {
        // Convert BigInts to strings for JSON serialization
        if (typeof value === 'bigint') {
          return value.toString();
        }
        return value;
      }, 2)
    );
    console.log(`Summary saved to ${summaryPath}`);
    
    console.log('\nIntegration test completed successfully!');
  } catch (error) {
    console.error('Error running integration test:', error);
    process.exit(1);
  }
}

function showHelp() {
  console.log(`
Usage: node run-integration.js [options]

Options:
  --children, -c    Number of child wallets to create (default: 3)
  --funding, -f     Amount of SOL to fund each child wallet (default: 0.1)
  --volume, -v      Total volume of SOL to transfer (default: 0.05)
  --token, -t       Token mint address (default: null, uses SOL)
  --new-wallet, -n  Force creation of a new mother wallet (default: false)
  --help, -h        Show this help message
  
Notes:
  - When running on devnet without a token mint (default behavior),
    the script will fund child wallets and then return funds to the
    mother wallet instead of executing transfers between child wallets.
  - For mainnet or when a token mint is provided, the regular transfer
    schedule will be executed between child wallets.
  
Example:
  node run-integration.js -c 5 -f 0.2 -v 0.1 -n
`);
}

// Run the main function
main().catch(err => {
  console.error('Unhandled error:', err);
  process.exit(1);
}); 