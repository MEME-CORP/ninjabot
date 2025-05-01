/**
 * Utility functions for working with keypairs in Solana
 * This provides compatibility functions that would normally come from @solana/kit in v2
 */

import { Keypair } from '@solana/web3.js';

/**
 * Generate a new keypair
 * @returns A Promise that resolves to the generated keypair
 */
export async function generateKeyPairSigner(): Promise<Keypair> {
  return Keypair.generate();
}

/**
 * Create a keypair from bytes
 * @param bytes The private key bytes
 * @returns A keypair created from the provided bytes
 */
export function createKeyPairFromBytes(bytes: Uint8Array): Keypair {
  return Keypair.fromSecretKey(bytes);
}

/**
 * Create a keypair from bytes
 * @param bytes The private key bytes
 * @returns A Promise that resolves to a keypair created from the provided bytes
 */
export async function createKeyPairSignerFromBytes(bytes: Uint8Array): Promise<Keypair> {
  return Keypair.fromSecretKey(bytes);
}

/**
 * Convert a buffer to base64 string
 * @param buffer The buffer to convert
 * @returns The base64 string representation
 */
export function bufferToBase64(buffer: Uint8Array): string {
  return Buffer.from(buffer).toString('base64');
}

/**
 * Get the base58 encoded version of a keypair's public key
 * @param keypair The keypair
 * @returns The base58 encoded public key
 */
export function getBase58PublicKey(keypair: Keypair): string {
  return keypair.publicKey.toBase58();
} 