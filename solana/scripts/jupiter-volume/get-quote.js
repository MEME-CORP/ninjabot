#!/usr/bin/env node
/**
 * Get a swap quote from Jupiter for token pairs
 * This is part of Phase 3 - Jupiter Volume Integration
 * 
 * Usage: node get-quote.js [--amount n] [--input-token token] [--output-token token]
 * 
 * Default tokens:
 * - SOL: So11111111111111111111111111111111111111112
 * - USDC: EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v
 */
const path = require('path');
const fs = require('fs');
const fetch = require('node-fetch');

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

// Common token addresses
const TOKENS = {
  SOL: 'So11111111111111111111111111111111111111112',
  USDC: 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v',
  USDT: 'Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB',
  BONK: 'DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263'
};

// Jupiter API base URL - using the free tier lite-api endpoint
const JUPITER_API_BASE = 'https://lite-api.jup.ag/swap/v1';

// Fetch price quote from Jupiter
async function getQuote(inputMint, outputMint, amount, slippageBps = 50) {
  try {
    const params = new URLSearchParams({
      inputMint,
      outputMint,
      amount,
      slippageBps,
      // Optional parameters
      onlyDirectRoutes: false,
      asLegacyTransaction: false,
      platformFeeBps: 0
    });
    
    console.log(`Requesting quote from Jupiter: ${inputMint} → ${outputMint} for ${amount} input amount...`);
    
    const response = await fetch(`${JUPITER_API_BASE}/quote?${params}`);
    
    if (!response.ok) {
      throw new Error(`HTTP error! Status: ${response.status}`);
    }
    
    return await response.json();
  } catch (error) {
    console.error('Error fetching Jupiter quote:', error);
    throw error;
  }
}

async function main() {
  try {
    console.log('===== JUPITER QUOTE TEST =====');
    
    // Parse command line arguments
    const args = process.argv.slice(2);
    let amount = '1000000'; // Default - 0.001 SOL in lamports or a small USDC amount (6 decimals)
    let inputToken = TOKENS.SOL;
    let outputToken = TOKENS.USDC;
    
    for (let i = 0; i < args.length; i++) {
      const arg = args[i].toLowerCase();
      if (arg === '--amount' || arg === '-a') {
        if (i + 1 < args.length) {
          amount = args[i + 1];
          i++;
        }
      } else if (arg === '--input-token' || arg === '-i') {
        if (i + 1 < args.length) {
          const token = args[i + 1].toUpperCase();
          if (TOKENS[token]) {
            inputToken = TOKENS[token];
          } else {
            // Check if it's a valid address
            if (args[i + 1].length > 30) {
              inputToken = args[i + 1];
            } else {
              console.warn(`Warning: Unknown token ${args[i + 1]}, using default`);
            }
          }
          i++;
        }
      } else if (arg === '--output-token' || arg === '-o') {
        if (i + 1 < args.length) {
          const token = args[i + 1].toUpperCase();
          if (TOKENS[token]) {
            outputToken = TOKENS[token];
          } else {
            // Check if it's a valid address
            if (args[i + 1].length > 30) {
              outputToken = args[i + 1];
            } else {
              console.warn(`Warning: Unknown token ${args[i + 1]}, using default`);
            }
          }
          i++;
        }
      }
    }
    
    console.log('Configuration:');
    console.log(`- Input token: ${inputToken}`);
    console.log(`- Output token: ${outputToken}`);
    console.log(`- Amount: ${amount}\n`);
    
    // Get quote directly - skip route map check which has issues
    console.log('Fetching Jupiter quote...');
    const quote = await retry(() => getQuote(inputToken, outputToken, amount));
    
    // Display quote details
    console.log('\nQuote details:');
    console.log(`- Input amount: ${quote.inputMint === TOKENS.SOL ? quote.inAmount / 1000000000 + ' SOL' : quote.inAmount} ${quote.inputMint === TOKENS.SOL ? '' : '(' + quote.inputMint + ')'}`);
    console.log(`- Output amount: ${quote.outputMint === TOKENS.SOL ? quote.outAmount / 1000000000 + ' SOL' : quote.outAmount} ${quote.outputMint === TOKENS.SOL ? '' : '(' + quote.outputMint + ')'}`);
    console.log(`- Price impact (%): ${quote.priceImpactPct}`);
    console.log(`- Other fees: ${quote.otherAmountThreshold} (minimum output amount with slippage)`);
    
    // Display route info
    console.log('\nRoute information:');
    if (quote.routePlan && quote.routePlan.length > 0) {
      quote.routePlan.forEach((step, index) => {
        console.log(`- Step ${index + 1}:`);
        
        // Access the correct properties using swapInfo
        if (step.swapInfo) {
          const { ammKey, label, inputMint, outputMint, inAmount, outAmount } = step.swapInfo;
          
          const inputSymbol = inputMint === TOKENS.SOL ? 'SOL' : 
                             inputMint === TOKENS.USDC ? 'USDC' :
                             inputMint === TOKENS.USDT ? 'USDT' :
                             inputMint === TOKENS.BONK ? 'BONK' :
                             inputMint.substring(0, 8) + '...';
                             
          const outputSymbol = outputMint === TOKENS.SOL ? 'SOL' : 
                              outputMint === TOKENS.USDC ? 'USDC' :
                              outputMint === TOKENS.USDT ? 'USDT' :
                              outputMint === TOKENS.BONK ? 'BONK' :
                              outputMint.substring(0, 8) + '...';
          
          console.log(`  - Swap from ${inputSymbol} (${inAmount}) to ${outputSymbol} (${outAmount})`);
          console.log(`  - Using market: ${label || 'Unknown'} (${ammKey.substring(0, 8)}...)`);
        } else {
          console.log(`  - Unknown swap info`);
        }
        
        console.log(`  - Percent of input: ${step.percent || 100}%`);
      });
    } else {
      console.log('Direct swap (no multi-route)');
    }
    
    // Save quote to temporary file for use in swap script
    const tempDir = path.join(process.cwd(), 'scripts', 'jupiter-volume', 'temp');
    if (!fs.existsSync(tempDir)) {
      fs.mkdirSync(tempDir, { recursive: true });
    }
    
    const quoteFile = path.join(tempDir, 'last-quote.json');
    fs.writeFileSync(quoteFile, JSON.stringify(quote, null, 2));
    console.log(`\nQuote saved to: ${quoteFile}`);
    
    console.log('\nJupiter quote test completed.');
    console.log('Next step: Run buy-tokens.js to execute the swap with this quote.');
    
  } catch (error) {
    console.error('Error running Jupiter quote test:', error);
    process.exit(1);
  }
}

// Run the main function
main().catch(err => {
  console.error('Unhandled error:', err);
  process.exit(1);
}); 