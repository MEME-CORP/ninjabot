import fs from 'fs';
import path from 'path';
import { WalletManager, defaultWalletManager } from '../wallet/walletManager';
import { Keypair } from '@solana/web3.js';

// Define a more specific type for the signer
interface Signer {
  address: string;
  publicKey: { toString: () => string };
  // Other properties would be defined here if needed
}

// Define the storage directory
const WALLET_STORAGE_DIR = path.join(process.cwd(), 'wallet-storage');
const MOTHER_WALLET_FILE = path.join(WALLET_STORAGE_DIR, 'mother-wallet.json');

/**
 * Securely stores wallet information to a file
 * 
 * @param walletData - The wallet data to store
 * @param filename - The filename to save to
 */
export async function storeWalletData(walletData: any, filename: string): Promise<void> {
  // Ensure the storage directory exists
  if (!fs.existsSync(WALLET_STORAGE_DIR)) {
    fs.mkdirSync(WALLET_STORAGE_DIR, { recursive: true });
  }

  // Convert data to JSON and write to file
  const filePath = path.join(WALLET_STORAGE_DIR, filename);
  
  // Store the data
  fs.writeFileSync(filePath, JSON.stringify(walletData, null, 2));
  console.log(`Wallet data saved to ${filePath}`);
}

/**
 * Loads wallet data from a file
 * 
 * @param filename - The filename to load from
 * @returns The wallet data or null if not found
 */
export function loadWalletData(filename: string): any | null {
  const filePath = path.join(WALLET_STORAGE_DIR, filename);
  
  if (!fs.existsSync(filePath)) {
    return null;
  }
  
  const data = fs.readFileSync(filePath, 'utf8');
  return JSON.parse(data);
}

/**
 * Creates a new mother wallet and saves it to a file
 * 
 * @returns The created mother wallet data
 */
export async function createAndStoreMotherWallet(): Promise<any> {
  // Create a new mother wallet
  const { signer, mnemonic, privateKeyBytes } = await defaultWalletManager.createMotherWallet();
  
  // Convert private key bytes to a format that can be safely stored
  const privateKeyBase64 = Buffer.from(privateKeyBytes).toString('base64');
  
  // Prepare data for storage
  const walletData = {
    publicKey: signer.publicKey.toString(),
    mnemonic,
    privateKeyBase64,
    createdAt: new Date().toISOString(),
    network: 'devnet'
  };
  
  // Store the wallet data
  await storeWalletData(walletData, 'mother-wallet.json');
  
  return walletData;
}

/**
 * Loads the mother wallet
 * 
 * @returns The mother wallet data or null if not found
 */
export function loadMotherWallet(): any | null {
  return loadWalletData('mother-wallet.json');
}

/**
 * Imports the mother wallet from stored data
 * 
 * @returns The mother wallet signer or null if not found
 */
export async function importMotherWalletFromStorage(): Promise<any | null> {
  const walletData = loadMotherWallet();
  
  if (!walletData) {
    return null;
  }
  
  // Convert base64 private key back to bytes
  const privateKeyBytes = Buffer.from(walletData.privateKeyBase64, 'base64');
  
  // Import the wallet using the private key
  return await defaultWalletManager.importMotherWallet(privateKeyBytes);
}

/**
 * Generates and stores child wallets
 * 
 * @param count - Number of child wallets to generate
 * @returns Array of generated child wallet data
 */
export async function generateAndStoreChildWallets(count: number): Promise<any[]> {
  // Load mother wallet
  const motherWalletData = loadMotherWallet();
  
  if (!motherWalletData) {
    throw new Error('Mother wallet not found. Create a mother wallet first.');
  }
  
  // Convert base64 private key back to bytes
  const motherPrivateKeyBytes = Buffer.from(motherWalletData.privateKeyBase64, 'base64');
  
  // Generate child wallets
  const childWallets = [];
  
  for (let i = 0; i < count; i++) {
    const childSigner = await defaultWalletManager.deriveChildWallet(motherPrivateKeyBytes, i);
    
    // Store the private key for the child wallet
    const privateKeyBase64 = Buffer.from(childSigner.secretKey).toString('base64');
    
    const childData = {
      index: i,
      publicKey: childSigner.publicKey.toString(),
      privateKeyBase64: privateKeyBase64, // Add private key
      derivationPath: `m/0/${i}`, // Based on the derivation path in walletManager
      parentPublicKey: motherWalletData.publicKey,
      createdAt: new Date().toISOString(),
      network: 'devnet'
    };
    
    childWallets.push(childData);
  }
  
  // Store all child wallets
  await storeWalletData(childWallets, 'child-wallets.json');
  
  return childWallets;
}

/**
 * Loads the stored child wallets
 * 
 * @returns Array of child wallet data or empty array if none found
 */
export function loadChildWallets(): any[] {
  const childWallets = loadWalletData('child-wallets.json');
  return childWallets || [];
}

/**
 * Clears all stored wallet data
 */
export function clearWalletStorage(): void {
  if (fs.existsSync(WALLET_STORAGE_DIR)) {
    fs.readdirSync(WALLET_STORAGE_DIR).forEach(file => {
      fs.unlinkSync(path.join(WALLET_STORAGE_DIR, file));
    });
  }
} 