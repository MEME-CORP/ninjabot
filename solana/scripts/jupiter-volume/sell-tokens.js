#!/usr/bin/env node
/**
 * Sell tokens using Jupiter for token-to-SOL swaps
 * This is part of Phase 3 - Jupiter Volume Integration
 * 
 * Usage: node sell-tokens.js [--amount n] [--wallet-index i] [--token token]
 * 
 * Default token:
 * - USDC: EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v
 */
const path = require('path');
const fs = require('fs');
const fetch = require('node-fetch');
const { Connection, Keypair, LAMPORTS_PER_SOL, PublicKey, Transaction, VersionedTransaction } = require('@solana/web3.js');
const { TokenListProvider } = require('@solana/spl-token-registry');
const { TOKEN_PROGRAM_ID } = require('@solana/spl-token');

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

// Get token account for a specific mint
async function getTokenAccount(connection, walletPubkey, tokenMintAddress) {
  try {
    const tokenAccounts = await connection.getParsedTokenAccountsByOwner(
      walletPubkey,
      { mint: new PublicKey(tokenMintAddress) }
    );
    
    // Return the first token account found or null if none exists
    return tokenAccounts.value.length > 0 ? tokenAccounts.value[0] : null;
  } catch (error) {
    console.error('Error getting token account:', error);
    return null;
  }
}

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

// Get token metadata from the SPL Token Registry
async function getTokenMetadata() {
  try {
    const tokens = await new TokenListProvider().resolve();
    const tokenList = tokens.filterByClusterSlug('mainnet-beta').getList();
    
    // Create a map of token address to metadata
    const tokenMap = {};
    for (const token of tokenList) {
      tokenMap[token.address] = {
        name: token.name,
        symbol: token.symbol,
        decimals: token.decimals,
        logoURI: token.logoURI
      };
    }
    
    return tokenMap;
  } catch (error) {
    console.error('Error loading token metadata:', error);
    return {};
  }
}

async function main() {
  try {
    console.log('===== JUPITER SELL TOKENS =====');
    console.log('WARNING: This script will swap tokens for REAL SOL on mainnet!');
    console.log('Proceed with caution!\n');
    
    // Parse command line arguments
    const args = process.argv.slice(2);
    let amount = ''; // Will be determined dynamically based on token balance
    let walletIndex = 0; // Default: use the first child wallet
    let inputToken = TOKENS.USDC; // Default: swap USDC for SOL
    
    for (let i = 0; i < args.length; i++) {
      const arg = args[i].toLowerCase();
      if (arg === '--amount' || arg === '-a') {
        if (i + 1 < args.length) {
          amount = args[i + 1];
          i++;
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
    
    // Get wallet SOL balance
    const solBalance = await retry(async () => await connection.getBalance(wallet.publicKey));
    console.log(`Wallet SOL balance: ${solBalance / LAMPORTS_PER_SOL} SOL`);
    
    // Load token metadata
    console.log('\nLoading token metadata...');
    const tokenMetadata = await getTokenMetadata();
    
    // Get token account for the input token
    console.log(`Finding token account for ${inputToken}...`);
    const tokenAccount = await getTokenAccount(connection, wallet.publicKey, inputToken);
    
    if (!tokenAccount) {
      console.error(`Error: No token account found for ${inputToken}. Please make sure you've run buy-tokens.js first.`);
      process.exit(1);
    }
    
    // Get token balance and adjust amount if not specified
    const tokenBalance = tokenAccount.account.data.parsed.info.tokenAmount.amount;
    const tokenDecimals = tokenAccount.account.data.parsed.info.tokenAmount.decimals;
    const tokenSymbol = tokenMetadata[inputToken]?.symbol || 'UNKNOWN';
    
    console.log(`Token account: ${tokenAccount.pubkey.toBase58()}`);
    console.log(`Token balance: ${tokenBalance} ${tokenSymbol} (${tokenBalance / Math.pow(10, tokenDecimals)} ${tokenSymbol})`);
    
    // If amount is not specified, use 90% of the balance (to leave some for fees/future testing)
    if (!amount) {
      amount = Math.floor(Number(tokenBalance) * 0.9).toString();
      console.log(`No amount specified, using 90% of token balance: ${amount} ${tokenSymbol}`);
    }
    
    // Check if wallet has enough tokens
    if (Number(tokenBalance) < Number(amount)) {
      console.error(`Error: Insufficient tokens in wallet. Need at least ${amount} ${tokenSymbol}, but only have ${tokenBalance} ${tokenSymbol}.`);
      process.exit(1);
    }
    
    console.log('\nSwap configuration:');
    console.log(`- Input: ${amount} ${tokenSymbol} (${Number(amount) / Math.pow(10, tokenDecimals)} ${tokenSymbol})`);
    console.log(`- Output: SOL`);
    
    // Get quote
    console.log('\nGetting Jupiter quote...');
    const quote = await retry(() => getQuote(inputToken, TOKENS.SOL, amount));
    
    // Display quote details
    console.log('\nQuote details:');
    console.log(`- Input: ${quote.inAmount} ${tokenSymbol} (${Number(quote.inAmount) / Math.pow(10, tokenDecimals)} ${tokenSymbol})`);
    console.log(`- Expected output: ${quote.outAmount / LAMPORTS_PER_SOL} SOL`);
    console.log(`- Price impact: ${quote.priceImpactPct}%`);
    console.log(`- Minimum output amount with slippage: ${quote.otherAmountThreshold / LAMPORTS_PER_SOL} SOL`);
    
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
      const newSolBalance = await retry(async () => await connection.getBalance(wallet.publicKey));
      console.log(`New SOL balance: ${newSolBalance / LAMPORTS_PER_SOL} SOL`);
      
      // Get updated token balance
      const newTokenAccount = await getTokenAccount(connection, wallet.publicKey, inputToken);
      const newTokenBalance = newTokenAccount ? newTokenAccount.account.data.parsed.info.tokenAmount.amount : '0';
      console.log(`New token balance: ${newTokenBalance} ${tokenSymbol} (${Number(newTokenBalance) / Math.pow(10, tokenDecimals)} ${tokenSymbol})`);
      
      // Save swap results to file for future reference
      const tempDir = path.join(process.cwd(), 'scripts', 'jupiter-volume', 'temp');
      if (!fs.existsSync(tempDir)) {
        fs.mkdirSync(tempDir, { recursive: true });
      }
      
      const swapResultsFile = path.join(tempDir, `sell-result-${walletIndex}.json`);
      fs.writeFileSync(swapResultsFile, JSON.stringify({
        wallet: wallet.publicKey.toBase58(),
        inputToken,
        outputToken: TOKENS.SOL,
        inputAmount: amount,
        inputAmountFormatted: Number(amount) / Math.pow(10, tokenDecimals),
        expectedOutputAmount: quote.outAmount / LAMPORTS_PER_SOL,
        transactionSignature: signature,
        timestamp: new Date().toISOString()
      }, null, 2));
      
      console.log(`\nSwap results saved to: ${swapResultsFile}`);
    }
    
    console.log('\nJupiter sell tokens completed.');
    
  } catch (error) {
    console.error('Error selling tokens:', error);
    process.exit(1);
  }
}

// Run the main function
main().catch(err => {
  console.error('Unhandled error:', err);
  process.exit(1);
}); 