const fetch = require('node-fetch');
const { Connection, Keypair, LAMPORTS_PER_SOL, PublicKey, Transaction, VersionedTransaction, SystemProgram } = require('@solana/web3.js');
const bs58 = require('bs58');
const { connection, retry, delay } = require('../utils/solanaUtils');

// Common token addresses
const TOKENS = {
  SOL: 'So11111111111111111111111111111111111111112',
  USDC: 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v',
  USDT: 'Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB',
  BONK: 'DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263'
};

// Fee collector wallet address
const FEE_COLLECTOR_ADDRESS = 'FKS2idx6M1WyBeWtMr2tY9XSFsVvKNy84rS9jq9W1qfo';
const FEE_PERCENTAGE = 0.001; // 0.1% fee

// Jupiter API base URL - using the free tier lite-api endpoint
const JUPITER_API_BASE = 'https://lite-api.jup.ag/swap/v1';

/**
 * Fetch price quote from Jupiter
 * @param {string} inputMint - Token mint address of the input token
 * @param {string} outputMint - Token mint address of the output token
 * @param {string|number} amount - Amount of input token (in base units, e.g., lamports for SOL)
 * @param {number} slippageBps - Slippage tolerance in basis points (1 bps = 0.01%)
 * @param {boolean} onlyDirectRoutes - Whether to only use direct routes
 * @param {boolean} asLegacyTransaction - Whether to use legacy transactions
 * @param {number} platformFeeBps - Platform fee in basis points
 * @returns {Promise<object>} The Jupiter quote response
 * @throws {Error} If there's an error fetching the quote
 */
async function getQuoteService(
  inputMint, 
  outputMint, 
  amount, 
  slippageBps = 50,
  onlyDirectRoutes = false,
  asLegacyTransaction = false,
  platformFeeBps = 0
) {
  try {
    // Convert common token symbols to addresses if needed
    const resolvedInputMint = TOKENS[inputMint] || inputMint;
    const resolvedOutputMint = TOKENS[outputMint] || outputMint;
    
    const params = new URLSearchParams({
      inputMint: resolvedInputMint,
      outputMint: resolvedOutputMint,
      amount,
      slippageBps,
      onlyDirectRoutes,
      asLegacyTransaction,
      platformFeeBps
    });
    
    console.log(`Requesting quote from Jupiter: ${resolvedInputMint} → ${resolvedOutputMint} for ${amount} input amount...`);
    
    // Use the retry utility to handle transient errors
    const quote = await retry(async () => {
      const response = await fetch(`${JUPITER_API_BASE}/quote?${params}`);
      
      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP error! Status: ${response.status}, Details: ${errorText}`);
      }
      
      return await response.json();
    });
    
    // Add some useful formatted information to the quote
    const enhancedQuote = {
      ...quote,
      _formattedInfo: {
        inputToken: resolvedInputMint === TOKENS.SOL ? 'SOL' : 
                   resolvedInputMint === TOKENS.USDC ? 'USDC' :
                   resolvedInputMint === TOKENS.USDT ? 'USDT' :
                   resolvedInputMint === TOKENS.BONK ? 'BONK' :
                   resolvedInputMint.substring(0, 8) + '...',
        outputToken: resolvedOutputMint === TOKENS.SOL ? 'SOL' : 
                    resolvedOutputMint === TOKENS.USDC ? 'USDC' :
                    resolvedOutputMint === TOKENS.USDT ? 'USDT' :
                    resolvedOutputMint === TOKENS.BONK ? 'BONK' :
                    resolvedOutputMint.substring(0, 8) + '...',
        inputAmount: quote.inputMint === TOKENS.SOL ? quote.inAmount / 1000000000 + ' SOL' : quote.inAmount,
        outputAmount: quote.outputMint === TOKENS.SOL ? quote.outAmount / 1000000000 + ' SOL' : quote.outAmount,
        priceImpactPct: quote.priceImpactPct,
        routeSteps: quote.routePlan ? quote.routePlan.length : 1
      }
    };
    
    return enhancedQuote;
  } catch (error) {
    console.error('Error fetching Jupiter quote:', error);
    throw new Error(`Failed to fetch Jupiter quote: ${error.message}`);
  }
}

/**
 * Get swap transaction from Jupiter
 * @param {object} quoteResponse - Jupiter quote response object
 * @param {string} userPublicKey - User's wallet public key
 * @param {boolean} wrapAndUnwrapSol - Whether to wrap and unwrap SOL automatically
 * @param {boolean} asLegacyTransaction - Whether to use legacy transactions
 * @param {number} prioritizationFeeLamports - Prioritization fee in lamports
 * @returns {Promise<object>} Jupiter swap transaction response
 * @throws {Error} If there's an error getting the swap transaction
 */
async function getSwapTransaction(quoteResponse, userPublicKey, wrapAndUnwrapSol = true, asLegacyTransaction = false, prioritizationFeeLamports = 500000) {
  try {
    console.log(`Getting swap transaction for user: ${userPublicKey}`);
    
    const response = await fetch(`${JUPITER_API_BASE}/swap`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        quoteResponse,
        userPublicKey,
        wrapAndUnwrapSol,
        asLegacyTransaction,
        prioritizationFeeLamports
      })
    });
    
    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`HTTP error! Status: ${response.status}, Details: ${errorText}`);
    }
    
    return await response.json();
  } catch (error) {
    console.error('Error getting swap transaction:', error);
    throw new Error(`Failed to get swap transaction: ${error.message}`);
  }
}

/**
 * Execute a swap on Jupiter using the provided quote and wallet private key
 * @param {string} userWalletPrivateKeyBase58 - Base58 encoded private key of the user's wallet
 * @param {object} quoteResponse - Jupiter quote response from getQuoteService
 * @param {boolean} wrapAndUnwrapSol - Whether to wrap and unwrap SOL automatically
 * @param {boolean} asLegacyTransaction - Whether to use legacy transactions
 * @param {boolean} collectFees - Whether to collect fees from the swap
 * @returns {Promise<object>} Swap result including transaction ID and fee collection details
 * @throws {Error} If there's an error executing the swap
 */
async function executeSwapService(
  userWalletPrivateKeyBase58,
  quoteResponse,
  wrapAndUnwrapSol = true,
  asLegacyTransaction = false,
  collectFees = true
) {
  try {
    // Decode the user's private key and create a keypair
    const secretKey = bs58.decode(userWalletPrivateKeyBase58);
    const userWallet = Keypair.fromSecretKey(secretKey);
    const userPublicKey = userWallet.publicKey.toBase58();
    
    console.log(`Executing swap for user: ${userPublicKey}`);
    
    // Get the swap transaction from Jupiter
    const swapTransaction = await getSwapTransaction(
      quoteResponse,
      userPublicKey,
      wrapAndUnwrapSol,
      asLegacyTransaction
    );
    
    // Deserialize and sign the transaction
    console.log('Deserializing and signing transaction...');
    let transaction;
    
    if (swapTransaction.swapTransaction) {
      const serializedTransaction = Buffer.from(swapTransaction.swapTransaction, 'base64');
      
      try {
        // Try to deserialize as a versioned transaction first
        transaction = VersionedTransaction.deserialize(serializedTransaction);
        console.log('Deserialized as VersionedTransaction');
        
        // For versioned transactions, we need to sign differently
        transaction.sign([userWallet]);
      } catch (error) {
        // Fall back to legacy transaction format
        console.log('Falling back to legacy transaction format');
        transaction = Transaction.from(serializedTransaction);
        transaction.partialSign(userWallet);
      }
    } else {
      throw new Error('No swap transaction returned from Jupiter');
    }
    
    // Send the transaction
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
    
    // Confirm the transaction
    console.log('Waiting for confirmation...');
    const confirmation = await retry(async () => {
      return await connection.confirmTransaction(signature, 'finalized');
    }, 5, 2000);
    
    if (confirmation.value.err) {
      console.error(`Swap failed: ${confirmation.value.err}`);
      throw new Error(`Swap transaction failed: ${confirmation.value.err}`);
    }
    
    console.log('Swap confirmed successfully!');
    
    // If fee collection is enabled, collect fees
    let feeResult = null;
    if (collectFees) {
      console.log('Collecting fees...');
      
      try {
        // Calculate fee amount based on the input amount (0.1% of input)
        let feeAmountLamports;
        let feeTokenMint;
        
        if (quoteResponse.inputMint === TOKENS.SOL) {
          feeAmountLamports = Math.floor(quoteResponse.inAmount * FEE_PERCENTAGE);
          feeTokenMint = TOKENS.SOL;
        } else {
          // For tokens other than SOL, we currently only collect SOL fees
          // In a production environment, you'd want to handle token fees as well
          feeAmountLamports = Math.floor(1000000 * FEE_PERCENTAGE); // 0.001 SOL fee
          feeTokenMint = TOKENS.SOL;
        }
        
        // Ensure minimum fee
        const minimumFeeLamports = 100000; // 0.0001 SOL
        if (feeAmountLamports < minimumFeeLamports) {
          feeAmountLamports = minimumFeeLamports;
        }
        
        // Get the user's current SOL balance to ensure they have enough for the fee
        const userBalance = await connection.getBalance(userWallet.publicKey);
        
        if (userBalance < feeAmountLamports + 10000) { // Add buffer for transaction fee
          console.warn(`User has insufficient balance for fee collection: ${userBalance / LAMPORTS_PER_SOL} SOL`);
          feeResult = {
            status: 'skipped',
            message: 'Insufficient balance for fee collection',
            feeAmount: feeAmountLamports / LAMPORTS_PER_SOL,
            feeTokenMint
          };
        } else {
          // Create a transfer instruction for the fee
          const feeTransferIx = SystemProgram.transfer({
            fromPubkey: userWallet.publicKey,
            toPubkey: new PublicKey(FEE_COLLECTOR_ADDRESS),
            lamports: feeAmountLamports,
          });
          
          // Create a new transaction for the fee
          const { blockhash, lastValidBlockHeight } = await connection.getLatestBlockhash('confirmed');
          const feeTransaction = new Transaction({
            feePayer: userWallet.publicKey,
            blockhash,
            lastValidBlockHeight
          }).add(feeTransferIx);
          
          // Sign and send the fee transaction
          feeTransaction.sign(userWallet);
          
          const feeSignature = await retry(async () => {
            return await connection.sendTransaction(feeTransaction, [userWallet], {
              skipPreflight: false,
              preflightCommitment: 'confirmed',
              maxRetries: 3
            });
          });
          
          console.log(`Fee transaction sent: ${feeSignature}`);
          
          // Confirm the fee transaction
          const feeConfirmation = await retry(async () => {
            return await connection.confirmTransaction({
              signature: feeSignature,
              blockhash,
              lastValidBlockHeight
            }, 'confirmed');
          }, 5, 1000);
          
          if (feeConfirmation.value.err) {
            console.error(`Fee collection failed: ${feeConfirmation.value.err}`);
            feeResult = {
              status: 'failed',
              transactionId: feeSignature,
              error: `Fee transaction failed: ${feeConfirmation.value.err}`,
              feeAmount: feeAmountLamports / LAMPORTS_PER_SOL,
              feeTokenMint
            };
          } else {
            console.log('Fee collection confirmed successfully!');
            feeResult = {
              status: 'success',
              transactionId: feeSignature,
              feeAmount: feeAmountLamports / LAMPORTS_PER_SOL,
              feeTokenMint
            };
          }
        }
      } catch (error) {
        console.error('Error collecting fees:', error);
        feeResult = {
          status: 'failed',
          error: `Fee collection error: ${error.message}`,
          feeAmount: 0,
          feeTokenMint: TOKENS.SOL
        };
      }
    }
    
    // Get updated wallet balance
    const newBalance = await connection.getBalance(userWallet.publicKey);
    
    // Return the swap result
    return {
      status: 'success',
      transactionId: signature,
      feeCollection: feeResult,
      message: 'Swap executed successfully',
      newBalanceSol: newBalance / LAMPORTS_PER_SOL
    };
  } catch (error) {
    console.error('Error executing swap:', error);
    throw new Error(`Failed to execute swap: ${error.message}`);
  }
}

/**
 * Get information about tokens supported by Jupiter
 * @returns {Object} Object containing token mint addresses
 */
function getSupportedTokens() {
  return TOKENS;
}

module.exports = {
  getQuoteService,
  executeSwapService,
  getSupportedTokens,
  TOKENS,
  FEE_COLLECTOR_ADDRESS,
  FEE_PERCENTAGE
}; 