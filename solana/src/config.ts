/**
 * Configuration constants for the application
 */

// Network configuration
export const SOLANA_RPC_URL_DEVNET = 'https://api.devnet.solana.com';
export const SOLANA_WSS_URL_DEVNET = 'wss://api.devnet.solana.com';
export const SOLANA_RPC_URL_MAINNET = 'https://api.mainnet-beta.solana.com';
export const SOLANA_WSS_URL_MAINNET = 'wss://api.mainnet-beta.solana.com';

// Fee configuration
export const FEE_RATE_NUMERATOR = 1n;
export const FEE_RATE_DENOMINATOR = 1000n; // 0.1% fee
export const SERVICE_WALLET_ADDRESS = '7fMgRsNxhD7yDASScVNrPGYzymnxuAP6oUcAkYYXwpbS'; // Replace with actual service wallet address

// Network to use (can be toggled between 'devnet' and 'mainnet')
export const NETWORK = 'devnet';

// Get the appropriate RPC and WSS URLs based on the network
export const getRpcUrl = (): string => {
  return NETWORK === 'devnet' ? SOLANA_RPC_URL_DEVNET : SOLANA_RPC_URL_MAINNET;
};

export const getWssUrl = (): string => {
  return NETWORK === 'devnet' ? SOLANA_WSS_URL_DEVNET : SOLANA_WSS_URL_MAINNET;
};

// Transaction parameters
export const MAX_RETRIES = 3;
export const COMPUTE_UNIT_LIMIT_MINIMUM = 1000;
export const COMPUTE_UNIT_BUFFER_MULTIPLIER = 1.1; // 10% buffer

// Add export for getConfig
export function getConfig() {
  return {
    continueOnError: false,
    // Other config values...
  };
} 