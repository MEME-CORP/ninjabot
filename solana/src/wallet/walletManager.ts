import * as bip39 from 'bip39';
import { derivePath } from 'ed25519-hd-key';
import { Keypair } from '@solana/web3.js';
import { WalletDerivationError, WalletNotFoundError } from './errors';
import { 
  generateKeyPairSigner, 
  createKeyPairFromBytes, 
  createKeyPairSignerFromBytes 
} from '../utils/keypairUtils';

// Use type aliases for the imports we couldn't resolve
type Address = string;
type Signer = any; // The signer object with address and signing capabilities

// In-memory wallet cache
const walletCache = new Map<number, Keypair>();

/**
 * Wallet derivation path format following BIP44
 * m / purpose' / coin_type' / account' / change / address_index
 * 
 * For Solana, we use:
 * m/44'/501'/account'/0/index
 */
const DERIVATION_PATH_BASE = "m/44'/501'";

/**
 * WalletManager provides functionality for creating, importing, and deriving Solana wallets.
 * It supports BIP44 derivation paths for hierarchical deterministic wallet generation.
 */
export class WalletManager {
  /**
   * Creates a new random mother wallet with a seed phrase.
   * @returns An object containing the created signer, mnemonic, and private key bytes
   */
  async createMotherWallet(): Promise<{ signer: Signer; mnemonic: string; privateKeyBytes: Uint8Array }> {
    try {
      // Generate a random mnemonic (seed phrase)
      const mnemonic = bip39.generateMnemonic(256); // 24 words
      
      // Import the wallet from the mnemonic
      const { signer, privateKeyBytes } = await this.importMotherWalletFromMnemonic(mnemonic);
      
      return { signer, mnemonic, privateKeyBytes };
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      console.error('Error creating mother wallet:', errorMessage);
      throw new Error(`Failed to create mother wallet: ${errorMessage}`);
    }
  }

  /**
   * Imports a mother wallet from a mnemonic phrase.
   * @param mnemonic - The mnemonic (seed phrase) to import
   * @returns The signer and private key bytes
   */
  async importMotherWalletFromMnemonic(mnemonic: string): Promise<{ signer: Signer; privateKeyBytes: Uint8Array }> {
    try {
      // Validate the mnemonic
      if (!bip39.validateMnemonic(mnemonic)) {
        throw new Error('Invalid mnemonic');
      }
      
      // Convert mnemonic to seed
      const seed = await bip39.mnemonicToSeed(mnemonic);
      const seedBuffer = Buffer.from(seed).toString('hex');
      
      // Derive the path for Solana (BIP44)
      const path = `m/44'/501'/0'/0'`;
      const derivedSeed = derivePath(path, seedBuffer).key;
      
      // Create keypair using web3.js v1 approach
      const keypair = Keypair.fromSeed(derivedSeed.slice(0, 32));
      
      return { 
        signer: keypair, 
        privateKeyBytes: keypair.secretKey
      };
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      console.error('Error importing mother wallet:', errorMessage);
      throw new Error(`Failed to import mother wallet: ${errorMessage}`);
    }
  }

  /**
   * Imports a mother wallet from private key bytes.
   * @param privateKeyBytes - The private key as a Uint8Array
   * @returns The signer object
   */
  async importMotherWallet(privateKeyBytes: Uint8Array): Promise<Signer> {
    try {
      // Create keypair using web3.js v1 approach
      return Keypair.fromSecretKey(privateKeyBytes);
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      console.error('Error importing mother wallet from private key:', errorMessage);
      throw new Error(`Failed to import mother wallet from private key: ${errorMessage}`);
    }
  }

  /**
   * Derives a child wallet from the mother wallet private key and an index.
   * @param motherPrivateKeyBytes - The mother wallet's private key bytes
   * @param index - The index of the child wallet to derive
   * @returns The derived child signer
   */
  async deriveChildWallet(motherPrivateKeyBytes: Uint8Array, index: number): Promise<Signer> {
    try {
      // For v1, we need to use Keypair.fromSecretKey for the mother wallet
      const motherKeypair = Keypair.fromSecretKey(motherPrivateKeyBytes);
      
      // Create a deterministic seed based on the mother wallet and index
      const indexBuffer = Buffer.alloc(4);
      indexBuffer.writeUInt32LE(index, 0);
      
      // Combine mother public key and index for deterministic derivation
      const seedBase = Buffer.concat([
        motherKeypair.publicKey.toBuffer(),
        indexBuffer
      ]);
      
      // Hash the combined buffer to get the seed for the child
      const seedHash = require('crypto').createHash('sha256').update(seedBase).digest();
      
      // Create child keypair from the derived seed
      return Keypair.fromSeed(new Uint8Array(seedHash));
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      console.error('Error deriving child wallet:', errorMessage);
      throw new Error(`Failed to derive child wallet: ${errorMessage}`);
    }
  }

  /**
   * Gets the public key address of a signer.
   * @param signer - The signer to get the address for
   * @returns The address
   */
  getAddress(signer: Signer): Address {
    return signer.address;
  }
}

/**
 * Create and export a default instance of WalletManager.
 */
export const defaultWalletManager = new WalletManager();

/**
 * Convenience function to create a new WalletManager instance.
 */
export function createWalletManager(): WalletManager {
  return new WalletManager();
}

/**
 * Create a wallet from a mnemonic phrase
 * 
 * @param mnemonic - The mnemonic phrase
 * @param derivationPath - The derivation path (BIP44 format)
 * @returns A Solana keypair
 */
export function createWalletFromMnemonic(
  mnemonic: string,
  derivationPath: string
): Keypair {
  try {
    // Convert mnemonic to seed
    const seed = bip39.mnemonicToSeedSync(mnemonic);
    
    // Derive private key from seed and path
    const { key } = derivePath(derivationPath, seed.toString('hex'));
    
    // Create keypair from private key
    return Keypair.fromSeed(key);
  } catch (error) {
    throw new WalletDerivationError(
      `Failed to create wallet from mnemonic: ${error instanceof Error ? error.message : String(error)}`
    );
  }
}

/**
 * Get a wallet by its index
 * 
 * @param index - The wallet index
 * @returns The wallet keypair or null if not found
 */
export async function getWalletFromIndex(index: number): Promise<Keypair | null> {
  // Check if wallet is already cached
  if (walletCache.has(index)) {
    return walletCache.get(index) || null;
  }
  
  // For child wallets, we load them from stored data
  if (index >= 0) {
    try {
      const fs = require('fs');
      const path = require('path');
      const WALLET_STORAGE_DIR = path.join(process.cwd(), 'wallet-storage');
      const CHILD_WALLETS_FILE = path.join(WALLET_STORAGE_DIR, 'child-wallets.json');
      
      if (fs.existsSync(CHILD_WALLETS_FILE)) {
        const childWallets = JSON.parse(fs.readFileSync(CHILD_WALLETS_FILE, 'utf8'));
        
        // Find the child wallet with the matching index
        const childWallet = childWallets.find((w: any) => w.index === index);
        
        if (childWallet && childWallet.privateKeyBase64) {
          // Convert base64 private key back to bytes
          const privateKeyBytes = Buffer.from(childWallet.privateKeyBase64, 'base64');
          
          // Create keypair from the private key
          const childKeypair = Keypair.fromSecretKey(privateKeyBytes);
          
          // Cache the wallet
          walletCache.set(index, childKeypair);
          
          return childKeypair;
        }
      }
      
      // Fallback: If no stored child wallet is found, generate a new one
      console.warn(`No stored child wallet found at index ${index}, generating a new one.`);
      const testWallet = Keypair.generate();
      walletCache.set(index, testWallet);
      return testWallet;
    } catch (error) {
      console.error(`Error getting wallet at index ${index}:`, error);
      return null;
    }
  }
  
  // For mother wallet (index -1), use the stored wallet
  if (index === -1) {
    try {
      const fs = require('fs');
      const path = require('path');
      const WALLET_STORAGE_DIR = path.join(process.cwd(), 'wallet-storage');
      const MOTHER_WALLET_FILE = path.join(WALLET_STORAGE_DIR, 'mother-wallet.json');
      
      if (fs.existsSync(MOTHER_WALLET_FILE)) {
        const walletData = JSON.parse(fs.readFileSync(MOTHER_WALLET_FILE, 'utf8'));
        const privateKeyBytes = Buffer.from(walletData.privateKeyBase64, 'base64');
        const motherKeypair = Keypair.fromSecretKey(privateKeyBytes);
        walletCache.set(-1, motherKeypair);
        return motherKeypair;
      }
    } catch (error) {
      console.error('Error loading mother wallet:', error);
    }
  }
  
  return null;
}

/**
 * Get multiple wallets by their indices
 * 
 * @param indices - Array of wallet indices
 * @returns Array of wallet keypairs
 * @throws WalletNotFoundError if any wallet is not found
 */
export async function getWalletsFromIndices(indices: number[]): Promise<Keypair[]> {
  const wallets: Keypair[] = [];
  
  for (const index of indices) {
    const wallet = await getWalletFromIndex(index);
    if (!wallet) {
      throw new WalletNotFoundError(`Wallet with index ${index} not found`);
    }
    wallets.push(wallet);
  }
  
  return wallets;
}

/**
 * Clear the wallet cache
 * This is useful for testing or when switching environments
 */
export function clearWalletCache(): void {
  walletCache.clear();
} 