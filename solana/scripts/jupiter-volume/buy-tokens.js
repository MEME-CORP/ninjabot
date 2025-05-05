#!/usr/bin/env node
/**
 * Buy tokens using Jupiter for SOL-to-token swaps
 * This is part of Phase 3 - Jupiter Volume Integration
 * 
 * Usage: node buy-tokens.js [--amount n] [--wallet-index i] [--token token]
 * 
 * Default token:
 * - USDC: EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v
 */
const path = require('path');
const fs = require('fs');
const fetch = require('node-fetch');
const { Connection, Keypair, LAMPORTS_PER_SOL, PublicKey, Transaction, VersionedTransaction } = require('@solana/web3.js');

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

// Jupiter API base URL
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

// Get swap transaction from Jupiter
async function getSwapTransaction(quoteResponse, userPublicKey) {
  try {
    const response = await fetch(`${JUPITER_API_BASE}/swap`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        quoteResponse,
        userPublicKey,
        wrapAndUnwrapSol: true, // Automatically wrap/unwrap SOL
        prioritizationFeeLamports: 500000 // Add priority fee (0.0005 SOL)
      })
    });
    
    if (!response.ok) {
      throw new Error(`HTTP error! Status: ${response.status}`);
    }
    
    return await response.json();
  } catch (error) {
    console.error('Error getting swap transaction:', error);
    throw error;
  }
}

async function main() {
  try {
    console.log('===== JUPITER BUY TOKENS =====');
    console.log('WARNING: This script will swap REAL SOL for tokens on mainnet!');
    console.log('Proceed with caution!\n');
    
    // Parse command line arguments
    const args = process.argv.slice(2);
    let amountLamports = 1000000; // Default 0.001 SOL in lamports
    let walletIndex = 0; // Default: use the first child wallet
    let outputToken = TOKENS.USDC; // Default: swap SOL for USDC
    
    for (let i = 0; i < args.length; i++) {
      const arg = args[i].toLowerCase();
      if (arg === '--amount' || arg === '-a') {
        if (i + 1 < args.length) {
          const solAmount = parseFloat(args[i + 1]);
          if (!isNaN(solAmount)) {
            amountLamports = Math.floor(solAmount * LAMPORTS_PER_SOL);
            i++;
          }
        }
      } else if (arg === '--wallet-index' || arg === '-w') {
        if (i + 1 < args.length) {
          const index = parseInt(args[i + 1], 10);
          if (!isNaN(index)) {
            walletIndex = index;
            i++;
          }
        }
      } else if (arg === '--token' || arg === '-t') {
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
    
    // Set up mainnet connection and wallet storage path
    const mainnetUrl = 'https://api.mainnet-beta.solana.com';
    const connection = new Connection(mainnetUrl);
    const mainnetWalletPath = path.join(process.cwd(), 'wallet-storage', 'mainnet');
    
    if (!fs.existsSync(mainnetWalletPath)) {
      console.error('Error: Mainnet wallet directory not found. Run test-mainnet-wallet.js first.');
      process.exit(1);
    }
    
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
    
    console.log(`Found ${childWallets.length} child wallets in storage`);
    
    // Validate wallet index
    if (walletIndex < 0 || walletIndex >= childWallets.length) {
      console.error(`Error: Invalid wallet index ${walletIndex}. Only have ${childWallets.length} wallets (0-${childWallets.length - 1}).`);
      process.exit(1);
    }
    
    // Get the wallet to use
    const wallet = childWallets[walletIndex];
    console.log(`Using wallet ${walletIndex}: ${wallet.publicKey.toBase58()}`);
    
    // Get wallet balance
    const balance = await retry(async () => await connection.getBalance(wallet.publicKey));
    const balanceInSol = balance / LAMPORTS_PER_SOL;
    console.log(`Wallet balance: ${balanceInSol} SOL`);
    
    // Check if wallet has enough SOL
    if (balance < amountLamports + 10000000) { // Add buffer for fees and wrapped SOL requirements
      console.error(`Error: Insufficient funds in wallet. Need at least ${(amountLamports + 10000000) / LAMPORTS_PER_SOL} SOL, but only have ${balanceInSol} SOL.`);
      process.exit(1);
    }
    
    console.log('\nSwap configuration:');
    console.log(`- Input: ${amountLamports / LAMPORTS_PER_SOL} SOL`);
    console.log(`- Output token: ${outputToken}`);
    
    // Get quote
    console.log('\nGetting Jupiter quote...');
    const quote = await retry(() => getQuote(TOKENS.SOL, outputToken, amountLamports.toString()));
    
    // Display quote details
    console.log('\nQuote details:');
    console.log(`- Input: ${quote.inAmount / LAMPORTS_PER_SOL} SOL`);
    console.log(`- Expected output: ${quote.outAmount} ${outputToken === TOKENS.USDC ? 'USDC' : outputToken}`);
    console.log(`- Price impact: ${quote.priceImpactPct}%`);
    console.log(`- Minimum output amount with slippage: ${quote.otherAmountThreshold}`);
    
    // Get swap transaction
    console.log('\nGetting swap transaction...');
    const swapTransaction = await retry(() => getSwapTransaction(quote, wallet.publicKey.toBase58()));
    
    // Deserialize and sign transaction
    console.log('Deserializing and signing transaction...');
    
    let transaction;
    if (swapTransaction.swapTransaction) {
      // Deserialize transaction
      const serializedTransaction = Buffer.from(swapTransaction.swapTransaction, 'base64');
      
      try {
        // Try to deserialize as a versioned transaction first
        transaction = VersionedTransaction.deserialize(serializedTransaction);
        console.log('Deserialized as VersionedTransaction');
        
        // For versioned transactions, we need to sign differently
        transaction.sign([wallet]);
      } catch (error) {
        // Fall back to legacy transaction format
        console.log('Falling back to legacy transaction format');
        transaction = Transaction.from(serializedTransaction);
        transaction.partialSign(wallet);
      }
    } else {
      console.error('Error: No swap transaction returned from Jupiter');
      process.exit(1);
    }
    
    // Send transaction
    console.log('Sending transaction...');
    const serializedTransaction = transaction.serialize ? transaction.serialize() : transaction.serialize();
    
    const signature = await retry(async () => {
      return await connection.sendRawTransaction(serializedTransaction, {
        skipPreflight: false,
        preflightCommitment: 'confirmed',
        maxRetries: 5
      });
    });
    
    console.log(`Transaction sent: ${signature}`);
    console.log(`Transaction Explorer: https://solscan.io/tx/${signature}`);
    
    // Confirm transaction
    console.log('Waiting for confirmation...');
    const confirmation = await retry(async () => {
      return await connection.confirmTransaction(signature, 'finalized');
    }, 5, 2000);
    
    if (confirmation.value.err) {
      console.error(`Swap failed: ${confirmation.value.err}`);
    } else {
      console.log('Swap confirmed successfully!');
      
      // Get updated SOL balance
      const newBalance = await retry(async () => await connection.getBalance(wallet.publicKey));
      console.log(`New SOL balance: ${newBalance / LAMPORTS_PER_SOL} SOL`);
      
      // Save swap results to file for future reference
      const tempDir = path.join(process.cwd(), 'scripts', 'jupiter-volume', 'temp');
      if (!fs.existsSync(tempDir)) {
        fs.mkdirSync(tempDir, { recursive: true });
      }
      
      const swapResultsFile = path.join(tempDir, `swap-result-${walletIndex}.json`);
      fs.writeFileSync(swapResultsFile, JSON.stringify({
        wallet: wallet.publicKey.toBase58(),
        inputToken: TOKENS.SOL,
        outputToken,
        inputAmount: amountLamports / LAMPORTS_PER_SOL,
        expectedOutputAmount: quote.outAmount,
        transactionSignature: signature,
        timestamp: new Date().toISOString()
      }, null, 2));
      
      console.log(`\nSwap results saved to: ${swapResultsFile}`);
    }
    
    console.log('\nJupiter buy tokens completed.');
    console.log('Next step: Run sell-tokens.js to swap tokens back to SOL.');
    
  } catch (error) {
    console.error('Error buying tokens:', error);
    process.exit(1);
  }
}

// Run the main function
main().catch(err => {
  console.error('Unhandled error:', err);
  process.exit(1);
}); 