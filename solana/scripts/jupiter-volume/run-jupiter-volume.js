#!/usr/bin/env node
/**
 * Run Jupiter volume test workflow (Phase 3)
 * This script orchestrates the full Jupiter volume testing workflow:
 * 1. Fund child wallets
 * 2. Buy tokens with SOL from child wallets
 * 3. Sell tokens back to SOL
 * 4. Generate report of volume and transactions
 * 
 * Usage: node run-jupiter-volume.js [--amount n] [--wallets 0,1] [--token USDC]
 */
const path = require('path');
const fs = require('fs');
const { execSync } = require('child_process');

// Common token addresses
const TOKENS = {
  SOL: 'So11111111111111111111111111111111111111112',
  USDC: 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v',
  USDT: 'Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB',
  BONK: 'DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263'
};

// Helper function to run a script and return its output
function runScript(scriptPath, args = []) {
  try {
    const command = `node ${scriptPath} ${args.join(' ')}`;
    console.log(`\n👉 Running: ${command}\n`);
    
    // Execute the command synchronously and capture output
    const output = execSync(command, { 
      encoding: 'utf8', 
      stdio: 'inherit'
    });
    
    return { success: true, output };
  } catch (error) {
    console.error(`Error running script ${scriptPath}:`, error.message);
    return { success: false, error: error.message };
  }
}

async function main() {
  try {
    console.log('===== JUPITER VOLUME TEST WORKFLOW =====');
    console.log('WARNING: This script will use REAL SOL and perform REAL swaps on mainnet!');
    console.log('Proceed with caution!\n');
    
    // Parse command line arguments
    const args = process.argv.slice(2);
    let solAmount = 0.002; // Default amount of SOL to use per wallet
    let walletIndices = [0, 1]; // Default wallet indices
    let tokenMint = TOKENS.USDC; // Default token to swap
    
    for (let i = 0; i < args.length; i++) {
      const arg = args[i].toLowerCase();
      if (arg === '--amount' || arg === '-a') {
        if (i + 1 < args.length) {
          const value = parseFloat(args[i + 1]);
          if (!isNaN(value)) {
            solAmount = value;
            i++;
          }
        }
      } else if (arg === '--wallets' || arg === '-w') {
        if (i + 1 < args.length) {
          try {
            walletIndices = args[i + 1].split(',').map(num => parseInt(num.trim(), 10));
            walletIndices = walletIndices.filter(index => !isNaN(index));
            i++;
          } catch (e) {
            console.error('Error parsing wallet indices, using defaults');
            walletIndices = [0, 1];
          }
        }
      } else if (arg === '--token' || arg === '-t') {
        if (i + 1 < args.length) {
          const token = args[i + 1].toUpperCase();
          if (TOKENS[token]) {
            tokenMint = TOKENS[token];
          } else {
            // Check if it's a valid address
            if (args[i + 1].length > 30) {
              tokenMint = args[i + 1];
            } else {
              console.warn(`Warning: Unknown token ${args[i + 1]}, using default`);
            }
          }
          i++;
        }
      }
    }
    
    console.log('Configuration:');
    console.log(`- SOL amount per wallet: ${solAmount} SOL`);
    console.log(`- Wallet indices: ${walletIndices.join(', ')}`);
    console.log(`- Token to swap: ${tokenMint}\n`);
    
    // Create temp directory for results
    const tempDir = path.join(process.cwd(), 'scripts', 'jupiter-volume', 'temp');
    if (!fs.existsSync(tempDir)) {
      fs.mkdirSync(tempDir, { recursive: true });
    }
    
    // Save configuration
    const configFile = path.join(tempDir, 'test-config.json');
    fs.writeFileSync(configFile, JSON.stringify({
      solAmount,
      walletIndices,
      tokenMint,
      timestamp: new Date().toISOString()
    }, null, 2));
    
    console.log('Test configuration saved to:', configFile);
    
    // Step 1: Fund child wallets
    console.log('\n===== STEP 1: FUND CHILD WALLETS =====');
    
    const fundingResult = runScript(
      path.join(process.cwd(), 'scripts', 'jupiter-volume', 'fund-wallets.js'),
      [
        '--amount', solAmount.toString(),
        '--wallets', walletIndices.join(',')
      ]
    );
    
    if (!fundingResult.success) {
      console.error('Funding wallets failed. Stopping test.');
      process.exit(1);
    }
    
    console.log('\n✅ Step 1 completed: Wallets funded successfully');
    
    // Step 2: Buy tokens with each wallet
    console.log('\n===== STEP 2: BUY TOKENS WITH SOL =====');
    
    const buyResults = [];
    
    for (const walletIndex of walletIndices) {
      console.log(`\n----- Buying tokens with wallet ${walletIndex} -----`);
      
      // Calculate buy amount (60% of funded amount to leave some for fees and account creation)
      const buyAmount = solAmount * 0.6;
      
      const buyResult = runScript(
        path.join(process.cwd(), 'scripts', 'jupiter-volume', 'buy-tokens.js'),
        [
          '--amount', buyAmount.toString(),
          '--wallet-index', walletIndex.toString(),
          '--token', tokenMint
        ]
      );
      
      buyResults.push({
        walletIndex,
        success: buyResult.success,
        timestamp: new Date().toISOString()
      });
      
      if (!buyResult.success) {
        console.warn(`⚠️ Buy operation failed for wallet ${walletIndex}`);
      }
    }
    
    // Save buy results
    const buyResultsFile = path.join(tempDir, 'buy-results.json');
    fs.writeFileSync(buyResultsFile, JSON.stringify(buyResults, null, 2));
    
    const successfulBuys = buyResults.filter(r => r.success).length;
    console.log(`\n${successfulBuys}/${walletIndices.length} buy operations completed successfully`);
    
    if (successfulBuys === 0) {
      console.error('All buy operations failed. Stopping test.');
      process.exit(1);
    }
    
    console.log('\n✅ Step 2 completed: Tokens purchased successfully');
    
    // Step 3: Sell tokens with each wallet
    console.log('\n===== STEP 3: SELL TOKENS BACK TO SOL =====');
    
    const sellResults = [];
    
    for (const walletIndex of walletIndices) {
      console.log(`\n----- Selling tokens with wallet ${walletIndex} -----`);
      
      const sellResult = runScript(
        path.join(process.cwd(), 'scripts', 'jupiter-volume', 'sell-tokens.js'),
        [
          '--wallet-index', walletIndex.toString(),
          '--token', tokenMint
        ]
      );
      
      sellResults.push({
        walletIndex,
        success: sellResult.success,
        timestamp: new Date().toISOString()
      });
      
      if (!sellResult.success) {
        console.warn(`⚠️ Sell operation failed for wallet ${walletIndex}`);
      }
    }
    
    // Save sell results
    const sellResultsFile = path.join(tempDir, 'sell-results.json');
    fs.writeFileSync(sellResultsFile, JSON.stringify(sellResults, null, 2));
    
    const successfulSells = sellResults.filter(r => r.success).length;
    console.log(`\n${successfulSells}/${walletIndices.length} sell operations completed successfully`);
    
    console.log('\n✅ Step 3 completed: Tokens sold successfully');
    
    // Step 4: Generate final report
    console.log('\n===== STEP 4: GENERATE JUPITER VOLUME REPORT =====');
    
    // Load all result files from the temp directory
    const buyResultFiles = fs.readdirSync(tempDir)
      .filter(file => file.startsWith('swap-result-'))
      .map(file => JSON.parse(fs.readFileSync(path.join(tempDir, file), 'utf-8')));
    
    const sellResultFiles = fs.readdirSync(tempDir)
      .filter(file => file.startsWith('sell-result-'))
      .map(file => JSON.parse(fs.readFileSync(path.join(tempDir, file), 'utf-8')));
    
    // Calculate total volume
    let totalSolVolume = 0;
    let totalTokenVolume = 0;
    
    buyResultFiles.forEach(result => {
      totalSolVolume += result.inputAmount || 0;
    });
    
    sellResultFiles.forEach(result => {
      totalTokenVolume += result.inputAmountFormatted || 0;
      totalSolVolume += result.expectedOutputAmount || 0;
    });
    
    // Generate report
    const report = {
      testConfig: JSON.parse(fs.readFileSync(configFile, 'utf-8')),
      summary: {
        totalWallets: walletIndices.length,
        successfulBuys,
        successfulSells,
        totalSolVolume,
        totalTokenVolume,
        buyTransactions: buyResultFiles.map(r => r.transactionSignature),
        sellTransactions: sellResultFiles.map(r => r.transactionSignature),
        completedAt: new Date().toISOString()
      }
    };
    
    // Save report
    const reportFile = path.join(process.cwd(), 'jupiter-volume-report.json');
    fs.writeFileSync(reportFile, JSON.stringify(report, null, 2));
    
    console.log('\nJupiter Volume Test Report:');
    console.log(`- Total wallets: ${walletIndices.length}`);
    console.log(`- Successful buys: ${successfulBuys}`);
    console.log(`- Successful sells: ${successfulSells}`);
    console.log(`- Total SOL volume: ${totalSolVolume.toFixed(6)} SOL`);
    console.log(`- Total token volume: ${totalTokenVolume.toFixed(6)}`);
    console.log(`\nFull report saved to: ${reportFile}`);
    
    console.log('\n🎉 Jupiter volume test completed successfully!');
    
  } catch (error) {
    console.error('Error running Jupiter volume test:', error);
    process.exit(1);
  }
}

// Run the main function
main().catch(err => {
  console.error('Unhandled error:', err);
  process.exit(1);
}); 