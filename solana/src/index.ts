/**
 * Main entry point for the Solana library
 */

// Export configuration
export * from './config';

// Export utility modules
export { 
  SolanaRpcClient, 
  defaultSolanaRpcClient,
  createSolanaRpcClient
} from './utils/solanaRpcClient';

// Export events module
export * from './utils/events';

// Export wallet module
export * from './wallet';

// Export scheduler module
export * from './scheduler';

// Export tokens module
export * from './tokens';

// Export common types and models
export * from './models/types';

// Export fee modules
export * from './fees/feeOracle';
export * from './fees/feeCollector';

// Export transaction modules
export * from './transactions';

// Export integration modules
export * from './integration'; 