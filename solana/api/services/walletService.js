const { Keypair, Connection, PublicKey, Transaction, SystemProgram, LAMPORTS_PER_SOL } = require('@solana/web3.js');
const bs58 = require('bs58');
const path = require('path');
const fs = require('fs');
const { connection, retry, delay } = require('../utils/solanaUtils');

// Define the Solana mainnet RPC endpoint
const MAINNET_URL = 'https://api.mainnet-beta.solana.com';

/**
 * Creates a new mother wallet or imports one from a base58 encoded private key.
 * @param {string} [privateKeyBase58] - Optional base58 encoded private key to import.
 * @returns {Promise<{publicKey: string, privateKeyBase58: string}>} An object containing the public key and base58 encoded private key.
 * @throws {Error} If private key decoding or keypair creation fails.
 */
async function createOrImportMotherWalletService(privateKeyBase58) {
  let keypair;

  if (privateKeyBase58) {
    try {
      const secretKeyBytes = bs58.decode(privateKeyBase58);
      if (secretKeyBytes.length !== 64 && secretKeyBytes.length !== 32) { // 32 for seed, 64 for full secret key
        // For simplicity, we'll assume bs58 encoded secret keys are typically full 64 bytes.
        // Keypair.fromSecretKey expects 64 bytes. If it's a 32-byte seed, it needs different handling
        // which is not typical for direct bs58 encoded private keys.
        // Let's stick to Keypair.fromSecretKey which expects 64 bytes.
        // If you intend to support 32-byte seeds that are bs58 encoded, this logic needs adjustment.
        // For now, we'll assume the input bs58 string decodes to a 64-byte secret key.
        console.warn(`Decoded secret key length is ${secretKeyBytes.length}. Expected 64 bytes for Keypair.fromSecretKey.`);
        // If Keypair.fromSecretKey handles various lengths gracefully, this warning might be for info only.
        // Test with actual key formats intended for use.
      }
      keypair = Keypair.fromSecretKey(secretKeyBytes);
      console.log('Mother wallet imported successfully.');
    } catch (error) {
      console.error('Failed to import mother wallet from private key:', error);
      throw new Error('Invalid private key provided or failed to derive keypair.');
    }
  } else {
    keypair = Keypair.generate();
    console.log('New mother wallet generated successfully.');
  }

  return {
    publicKey: keypair.publicKey.toBase58(),
    privateKeyBase58: bs58.encode(keypair.secretKey),
  };
}

/**
 * Retrieves information about a wallet, including its SOL balance.
 * @param {string} publicKeyStr - The wallet's public key in base58 encoding.
 * @returns {Promise<{publicKey: string, balanceSol: number, balanceLamports: number}>} The wallet's information.
 * @throws {Error} If there's an error retrieving the balance or the public key is invalid.
 */
async function getWalletInfo(publicKeyStr) {
  try {
    // Convert the public key string to a PublicKey object
    const publicKey = new PublicKey(publicKeyStr);
    
    // Get the wallet's SOL balance in lamports
    const balanceLamports = await connection.getBalance(publicKey);
    
    // Convert lamports to SOL (1 SOL = 1,000,000,000 lamports)
    const balanceSol = balanceLamports / 1_000_000_000;
    
    return {
      publicKey: publicKeyStr,
      balanceSol,
      balanceLamports,
    };
  } catch (error) {
    console.error('Error retrieving wallet info:', error);
    throw new Error(`Unable to get wallet info: ${error.message}`);
  }
}

/**
 * Derives child wallets from a mother wallet public key.
 * Note: In this implementation, we're creating new random wallets rather than using
 * hierarchical deterministic derivation, which aligns with the original script's approach.
 * 
 * @param {string} motherWalletPublicKey - The public key of the mother wallet.
 * @param {number} count - The number of child wallets to derive (default: 3).
 * @param {boolean} [saveToFile=false] - Whether to save the wallets to a file.
 * @returns {Promise<{motherWalletPublicKey: string, childWallets: Array<{publicKey: string, privateKeyBase58: string}>}>}
 * @throws {Error} If there's an error generating the child wallets.
 */
async function deriveChildWallets(motherWalletPublicKey, count = 3, saveToFile = false) {
  try {
    console.log(`Generating ${count} child wallets for mother wallet: ${motherWalletPublicKey}`);
    
    // Validate mother wallet public key
    new PublicKey(motherWalletPublicKey); // This will throw if invalid
    
    // Generate child wallets
    const childWallets = [];
    
    for (let i = 0; i < count; i++) {
      const keypair = Keypair.generate();
      childWallets.push({
        publicKey: keypair.publicKey.toBase58(),
        privateKeyBase58: bs58.encode(keypair.secretKey)
      });
    }
    
    // If saveToFile is true, save the wallets to the mainnet wallet storage directory
    if (saveToFile) {
      const mainnetWalletPath = path.join(process.cwd(), 'wallet-storage', 'mainnet');
      if (!fs.existsSync(mainnetWalletPath)) {
        fs.mkdirSync(mainnetWalletPath, { recursive: true });
      }
      
      const childWalletsPath = path.join(mainnetWalletPath, 'child-wallets.json');
      fs.writeFileSync(
        childWalletsPath,
        JSON.stringify(childWallets.map(wallet => {
          return {
            publicKey: wallet.publicKey,
            secretKey: Array.from(bs58.decode(wallet.privateKeyBase58))
          };
        }), null, 2),
        'utf-8'
      );
      console.log(`Child wallets saved to: ${childWalletsPath}`);
    }
    
    return {
      motherWalletPublicKey,
      childWallets
    };
  } catch (error) {
    console.error('Error deriving child wallets:', error);
    throw new Error(`Failed to derive child wallets: ${error.message}`);
  }
}

/**
 * Funds child wallets from a mother wallet.
 * @param {string} motherWalletPrivateKeyBase58 - The mother wallet's private key in base58 encoding.
 * @param {Array<{publicKey: string, amountSol: number}>} childWallets - Array of child wallet public keys and funding amounts.
 * @returns {Promise<{status: string, results: Array<{childPublicKey: string, transactionId: string|null, status: string, error: string|null}>}>}
 * @throws {Error} If there's an error with the mother wallet or insufficient funds.
 */
async function fundChildWallets(motherWalletPrivateKeyBase58, childWallets) {
  try {
    console.log(`Funding ${childWallets.length} child wallets`);
    
    // Decode mother wallet private key
    const motherSecretKey = bs58.decode(motherWalletPrivateKeyBase58);
    const motherWallet = Keypair.fromSecretKey(motherSecretKey);
    
    console.log(`Mother wallet public key: ${motherWallet.publicKey.toBase58()}`);
    
    // Check mother wallet balance
    const motherBalance = await retry(async () => await connection.getBalance(motherWallet.publicKey));
    const motherBalanceInSol = motherBalance / LAMPORTS_PER_SOL;
    console.log(`Mother wallet balance: ${motherBalanceInSol} SOL`);
    
    // Calculate total funding amount and check if mother wallet has enough balance
    const totalFundingAmount = childWallets.reduce((total, wallet) => total + wallet.amountSol, 0);
    const estimatedFees = 0.000005 * childWallets.length; // Rough estimate of transaction fees
    const totalRequired = totalFundingAmount + estimatedFees;
    
    if (motherBalanceInSol < totalRequired) {
      throw new Error(`Insufficient funds in mother wallet. Need at least ${totalRequired} SOL, but only have ${motherBalanceInSol} SOL.`);
    }
    
    // Fund each child wallet
    const results = [];
    
    for (let i = 0; i < childWallets.length; i++) {
      const { publicKey, amountSol } = childWallets[i];
      console.log(`Funding wallet ${i + 1}/${childWallets.length}: ${publicKey} with ${amountSol} SOL`);
      
      try {
        // Convert SOL to lamports
        const amountLamports = Math.floor(amountSol * LAMPORTS_PER_SOL);
        
        // Create and validate child wallet public key
        const childPublicKey = new PublicKey(publicKey);
        
        // Get current balance
        const currentBalance = await retry(async () => await connection.getBalance(childPublicKey));
        console.log(`Current balance: ${currentBalance / LAMPORTS_PER_SOL} SOL`);
        
        // Create a transfer instruction
        const instruction = SystemProgram.transfer({
          fromPubkey: motherWallet.publicKey,
          toPubkey: childPublicKey,
          lamports: amountLamports,
        });
        
        // Get recent blockhash with retry logic
        console.log('Getting recent blockhash...');
        const { blockhash, lastValidBlockHeight } = await retry(async () => {
          return await connection.getLatestBlockhash('confirmed');
        });
        
        // Create transaction
        const transaction = new Transaction({
          feePayer: motherWallet.publicKey,
          blockhash,
          lastValidBlockHeight
        }).add(instruction);
        
        // Sign transaction
        transaction.sign(motherWallet);
        
        // Add delay between transactions to avoid rate limiting
        if (i > 0) {
          console.log('Adding delay before sending transaction...');
          await delay(2000);
        }
        
        // Send transaction with retry
        console.log('Sending transaction...');
        const signature = await retry(async () => {
          return await connection.sendTransaction(transaction, [motherWallet], {
            skipPreflight: false,
            preflightCommitment: 'confirmed',
            maxRetries: 5
          });
        });
        
        console.log(`Funding transaction sent: ${signature}`);
        
        // Wait for confirmation with retry
        console.log('Waiting for confirmation...');
        const confirmation = await retry(async () => {
          return await connection.confirmTransaction({
            signature,
            blockhash,
            lastValidBlockHeight
          }, 'finalized');
        }, 5, 2000);
        
        if (confirmation.value.err) {
          console.error(`Funding failed: ${confirmation.value.err}`);
          results.push({
            childPublicKey: publicKey,
            transactionId: signature,
            status: 'failed',
            error: `Confirmation error: ${confirmation.value.err}`
          });
        } else {
          console.log('Funding confirmed successfully!');
          
          // Get updated balance
          const newBalance = await retry(async () => await connection.getBalance(childPublicKey));
          console.log(`New balance: ${newBalance / LAMPORTS_PER_SOL} SOL`);
          
          results.push({
            childPublicKey: publicKey,
            transactionId: signature,
            status: 'funded',
            error: null,
            newBalanceSol: newBalance / LAMPORTS_PER_SOL
          });
        }
      } catch (error) {
        console.error(`Error funding wallet ${publicKey}:`, error);
        results.push({
          childPublicKey: publicKey,
          transactionId: null,
          status: 'failed',
          error: error.message || 'Unknown error'
        });
      }
    }
    
    // Determine overall status
    const overallStatus = results.every(r => r.status === 'funded') 
      ? 'success' 
      : (results.some(r => r.status === 'funded') ? 'partial' : 'failed');
    
    // Get final mother wallet balance
    const finalBalance = await retry(async () => await connection.getBalance(motherWallet.publicKey));
    console.log(`Final mother wallet balance: ${finalBalance / LAMPORTS_PER_SOL} SOL`);
    
    return {
      status: overallStatus,
      results: results,
      motherWalletFinalBalanceSol: finalBalance / LAMPORTS_PER_SOL
    };
  } catch (error) {
    console.error('Error funding child wallets:', error);
    throw new Error(`Failed to fund child wallets: ${error.message}`);
  }
}

/**
 * Returns funds from a child wallet to a mother wallet.
 * @param {string} childWalletPrivateKeyBase58 - The child wallet's private key in base58 encoding.
 * @param {string} motherWalletPublicKey - The mother wallet's public key in base58 encoding.
 * @param {boolean} returnAllFunds - Whether to return all funds or keep some for transaction fees.
 * @returns {Promise<{status: string, transactionId: string, amountReturnedSol: number, newChildBalanceSol: number}>}
 * @throws {Error} If there's an error returning funds.
 */
async function returnFundsToMotherWallet(childWalletPrivateKeyBase58, motherWalletPublicKey, returnAllFunds = false) {
  try {
    console.log(`Returning funds to mother wallet: ${motherWalletPublicKey}`);
    
    // Decode child wallet private key
    const childSecretKey = bs58.decode(childWalletPrivateKeyBase58);
    const childWallet = Keypair.fromSecretKey(childSecretKey);
    const childPublicKey = childWallet.publicKey.toBase58();
    
    console.log(`Child wallet public key: ${childPublicKey}`);
    
    // Validate mother wallet public key
    const motherPublicKey = new PublicKey(motherWalletPublicKey);
    
    // Check child wallet balance
    const childBalance = await retry(async () => await connection.getBalance(childWallet.publicKey));
    const childBalanceInSol = childBalance / LAMPORTS_PER_SOL;
    console.log(`Child wallet balance: ${childBalanceInSol} SOL`);
    
    // Check if the wallet has enough funds to return
    const minimumTransactionFee = 5000; // 0.000005 SOL for transaction fee
    
    if (childBalance <= minimumTransactionFee) {
      throw new Error(`Insufficient funds in child wallet. Balance (${childBalanceInSol} SOL) is too low to cover transaction fees.`);
    }
    
    // Calculate amount to return, leaving some for transaction fees if returnAllFunds is false
    let amountToReturn;
    if (returnAllFunds) {
      // Return all but leave just enough for the transaction fee
      amountToReturn = childBalance - minimumTransactionFee;
    } else {
      // Return all but leave a small amount for potential future transactions (0.001 SOL)
      const bufferAmount = 1000000; // 0.001 SOL in lamports
      amountToReturn = childBalance - bufferAmount - minimumTransactionFee;
      
      // If the buffer would leave too little, just return all minus the transaction fee
      if (amountToReturn <= 0) {
        amountToReturn = childBalance - minimumTransactionFee;
      }
    }
    
    console.log(`Returning ${amountToReturn / LAMPORTS_PER_SOL} SOL to mother wallet`);
    
    // Create a transfer instruction
    const instruction = SystemProgram.transfer({
      fromPubkey: childWallet.publicKey,
      toPubkey: motherPublicKey,
      lamports: amountToReturn,
    });
    
    // Get recent blockhash with retry logic
    console.log('Getting recent blockhash...');
    const { blockhash, lastValidBlockHeight } = await retry(async () => {
      return await connection.getLatestBlockhash('confirmed');
    });
    
    // Create transaction
    const transaction = new Transaction({
      feePayer: childWallet.publicKey,
      blockhash,
      lastValidBlockHeight
    }).add(instruction);
    
    // Sign transaction
    transaction.sign(childWallet);
    
    // Send transaction with retry
    console.log('Sending transaction...');
    const signature = await retry(async () => {
      return await connection.sendTransaction(transaction, [childWallet], {
        skipPreflight: false,
        preflightCommitment: 'confirmed',
        maxRetries: 5
      });
    });
    
    console.log(`Return funds transaction sent: ${signature}`);
    
    // Wait for confirmation with retry
    console.log('Waiting for confirmation...');
    const confirmation = await retry(async () => {
      return await connection.confirmTransaction({
        signature,
        blockhash,
        lastValidBlockHeight
      }, 'finalized');
    }, 5, 2000);
    
    if (confirmation.value.err) {
      console.error(`Return funds failed: ${confirmation.value.err}`);
      throw new Error(`Transaction failed: ${confirmation.value.err}`);
    }
    
    console.log('Return funds confirmed successfully!');
    
    // Get updated balances
    const newChildBalance = await retry(async () => await connection.getBalance(childWallet.publicKey));
    const newMotherBalance = await retry(async () => await connection.getBalance(motherPublicKey));
    
    console.log(`New child wallet balance: ${newChildBalance / LAMPORTS_PER_SOL} SOL`);
    console.log(`New mother wallet balance: ${newMotherBalance / LAMPORTS_PER_SOL} SOL`);
    
    return {
      status: 'success',
      transactionId: signature,
      amountReturnedSol: amountToReturn / LAMPORTS_PER_SOL,
      newChildBalanceSol: newChildBalance / LAMPORTS_PER_SOL,
      message: 'Funds returned to mother wallet successfully'
    };
  } catch (error) {
    console.error('Error returning funds to mother wallet:', error);
    throw new Error(`Failed to return funds: ${error.message}`);
  }
}

module.exports = {
  createOrImportMotherWalletService,
  getWalletInfo,
  deriveChildWallets,
  fundChildWallets,
  returnFundsToMotherWallet
}; 