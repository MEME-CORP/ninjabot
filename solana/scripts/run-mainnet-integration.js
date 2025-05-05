#!/usr/bin/env node
/**
 * Script to run the integration workflow on Solana mainnet
 * 
 * WARNING: This script uses REAL SOL on the mainnet. Use with extreme caution.
 * 
 * Usage: node run-mainnet-integration.js [options]
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
    // Import the mainnet integration manager
    const { mainnetIntegration } = require('../dist/integration/mainnetIntegration');
    
    // Parse command line arguments
    const args = process.argv.slice(2);
    
    // Default parameters (very small defaults for mainnet safety)
    let childCount = 3;
    let fundingAmountSol = 0.001; // Minimal amount for mainnet
    let totalVolumeSol = 0.0005; // Minimal amount for mainnet
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
  NinjaBot Solana MAINNET Integration
==============================================
⚠️ WARNING: This is running on MAINNET using REAL SOL! ⚠️

Parameters:
- Child Wallets: ${childCount}
- Funding per Child: ${fundingAmountSol} SOL
- Total Volume: ${totalVolumeSol} SOL
- Token Mint: ${tokenMint || 'None (using SOL)'}
- Force New Mother Wallet: ${forceNewMotherWallet ? 'Yes' : 'No'}
==============================================
`);
    
    // Confirm user wants to proceed
    const readline = require('readline').createInterface({
      input: process.stdin,
      output: process.stdout
    });
    
    readline.question('\nThis will use REAL SOL on the Solana mainnet. Type "CONFIRM" to proceed: ', async (answer) => {
      readline.close();
      
      if (answer.trim() !== 'CONFIRM') {
        console.log('Operation cancelled.');
        return;
      }
      
      console.log('\nProceeding with mainnet integration...');
      
      // Run the complete workflow
      const summary = await mainnetIntegration.runCompleteWorkflow(
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
      
      if (summary.error) {
        console.error(`- Error: ${summary.error}`);
      }
      
      // Save summary to file
      const summaryPath = path.join(process.cwd(), 'mainnet-integration-summary.json');
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
      
      console.log('\nMainnet integration completed.');
    });
    
  } catch (error) {
    console.error('Error running mainnet integration:', error);
    process.exit(1);
  }
}

function showHelp() {
  console.log(`
Usage: node run-mainnet-integration.js [options]

Options:
  --children, -c    Number of child wallets to create (default: 3)
  --funding, -f     Amount of SOL to fund each child wallet (default: 0.001)
  --volume, -v      Total volume of SOL to transfer (default: 0.0005)
  --token, -t       Token mint address (default: null, uses SOL)
  --new-wallet, -n  Force creation of a new mother wallet (default: false)
  --help, -h        Show this help message
  
Notes:
  - This script runs on MAINNET and uses REAL SOL!
  - Use very small amounts for testing.
  - Always verify transactions manually on Solscan.
  
Example:
  node run-mainnet-integration.js -c 2 -f 0.001 -v 0.0005
`);
}

// Run the main function
main().catch(err => {
  console.error('Unhandled error:', err);
  process.exit(1);
}); 