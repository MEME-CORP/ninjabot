import { PublicKey } from '@solana/web3.js';
import { SolanaRpcClient, defaultSolanaRpcClient } from '../utils/solanaRpcClient';
import { AccountInfoResponse, isAccountInfoResponse } from '../utils/rpcTypes';

/**
 * Error thrown when a token is not found
 */
export class TokenNotFoundError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'TokenNotFoundError';
  }
}

/**
 * Token data structure
 */
export interface TokenData {
  mint: string;
  decimals: number;
  supply: bigint;
  name?: string;
  symbol?: string;
  logoUri?: string;
  isNft?: boolean;
}

/**
 * Layout for a Solana SPL Token mint account
 * Based on the mint account structure: https://github.com/solana-labs/solana-program-library/blob/master/token/program/src/state.rs
 */
const SPL_TOKEN_MINT_LAYOUT = {
  mintAuthorityOption: { offset: 0, span: 4 },
  mintAuthority: { offset: 4, span: 32 },
  supply: { offset: 36, span: 8 },
  decimals: { offset: 44, span: 1 },
  isInitialized: { offset: 45, span: 1 },
  freezeAuthorityOption: { offset: 46, span: 4 },
  freezeAuthority: { offset: 50, span: 32 }
};

/**
 * Default value to use when token information cannot be fetched
 */
const DEFAULT_TOKEN_DECIMALS = 9; // Default for SOL

/**
 * TokenInfo provides methods to retrieve token metadata from the Solana network
 */
export class TokenInfo {
  private rpcClient: SolanaRpcClient;
  private tokenCache: Map<string, TokenData> = new Map();
  
  /**
   * Creates a new TokenInfo instance
   * 
   * @param rpcClient - Solana RPC client instance
   */
  constructor(rpcClient: SolanaRpcClient = defaultSolanaRpcClient) {
    this.rpcClient = rpcClient;
  }
  
  /**
   * Get token data for a given mint address
   * 
   * @param mintAddress - The token mint address
   * @returns Token data including decimals and supply
   * @throws TokenNotFoundError if the token is not found
   */
  async getTokenData(mintAddress: string): Promise<TokenData> {
    // Check cache first
    if (this.tokenCache.has(mintAddress)) {
      return this.tokenCache.get(mintAddress)!;
    }
    
    try {
      // Validate the mint address
      new PublicKey(mintAddress);
      
      // Fetch token metadata from the chain
      const response = await this.rpcClient.getAccountInfo(
        mintAddress,
        'jsonParsed'
      );
      
      // Use type guard to validate response format
      if (!isAccountInfoResponse(response) || !response.value) {
        throw new TokenNotFoundError(`Token mint not found: ${mintAddress}`);
      }
      
      // Access the data safely after type verification
      const accountInfo = response.value;
      
      // Check if the account has data and it's in the expected format
      if (!accountInfo.data || !Array.isArray(accountInfo.data) || accountInfo.data.length < 2) {
        throw new TokenNotFoundError(`Invalid token data format for mint: ${mintAddress}`);
      }
      
      // Parse the data based on encoding
      let decimals = DEFAULT_TOKEN_DECIMALS;
      let supply = 0n;
      
      // Handle different response data formats
      if (typeof accountInfo.data[0] === 'object' && 'parsed' in (accountInfo.data[0] as any)) {
        // jsonParsed format
        const parsedData = (accountInfo.data[0] as any).parsed;
        if (parsedData.type === 'mint' && parsedData.info) {
          decimals = parsedData.info.decimals;
          supply = BigInt(parsedData.info.supply);
        }
      } else {
        // Binary data - we would need to manually decode this
        // For now, just fall back to defaults
        console.warn(`Token data for ${mintAddress} is not in parsed format, using defaults`);
      }
      
      const tokenData: TokenData = {
        mint: mintAddress,
        decimals,
        supply
      };
      
      // Store in cache
      this.tokenCache.set(mintAddress, tokenData);
      
      return tokenData;
    } catch (error) {
      if (error instanceof TokenNotFoundError) {
        throw error;
      }
      
      throw new TokenNotFoundError(
        `Failed to fetch token data: ${error instanceof Error ? error.message : String(error)}`
      );
    }
  }
  
  /**
   * Validate a token mint address
   * 
   * @param mintAddress - The token mint address to validate
   * @returns True if the token is valid
   */
  async isValidToken(mintAddress: string): Promise<boolean> {
    try {
      await this.getTokenData(mintAddress);
      return true;
    } catch (error) {
      return false;
    }
  }
  
  /**
   * Clear the token cache
   */
  clearCache(): void {
    this.tokenCache.clear();
  }

  /**
   * Gets the number of decimal places for a given token mint
   * 
   * @param mintAddress - The address of the token mint
   * @returns The number of decimal places the token uses
   */
  async getTokenDecimals(mintAddress: string): Promise<number> {
    try {
      // Attempt to fetch the token mint account data
      // In a real environment, this would query the Solana blockchain
      const accountInfo = await this.fetchMintAccount(mintAddress);
      
      if (!accountInfo) {
        console.warn(`Token mint account not found: ${mintAddress}`);
        return DEFAULT_TOKEN_DECIMALS;
      }
      
      // Read the decimals value from the account data
      const decimals = accountInfo.data.readUInt8(SPL_TOKEN_MINT_LAYOUT.decimals.offset);
      return decimals;
    } catch (error) {
      console.error('Error fetching token decimals:', error);
      return DEFAULT_TOKEN_DECIMALS;
    }
  }

  /**
   * Gets the total supply of a token mint
   * 
   * @param mintAddress - The address of the token mint
   * @returns The total supply (in base units) of the token
   */
  async getTokenSupply(mintAddress: string): Promise<bigint> {
    try {
      const accountInfo = await this.fetchMintAccount(mintAddress);
      
      if (!accountInfo) {
        return 0n;
      }
      
      // Read the 64-bit supply value from the account data
      const supplyLower = accountInfo.data.readUInt32LE(SPL_TOKEN_MINT_LAYOUT.supply.offset);
      const supplyUpper = accountInfo.data.readUInt32LE(SPL_TOKEN_MINT_LAYOUT.supply.offset + 4);
      
      // Combine the two 32-bit values into a single 64-bit BigInt
      const supply = (BigInt(supplyUpper) << 32n) | BigInt(supplyLower);
      return supply;
    } catch (error) {
      console.error('Error fetching token supply:', error);
      return 0n;
    }
  }

  /**
   * Internal helper method to fetch and decode a token mint account
   * 
   * @param mintAddress - The address of the token mint
   * @returns The decoded account info or null if not found
   */
  private async fetchMintAccount(mintAddress: string): Promise<{ data: Buffer } | null> {
    try {
      const response = await this.rpcClient.getAccountInfo(mintAddress, 'base64');
      
      // Use type guard to validate response format
      if (!isAccountInfoResponse(response) || !response.value) {
        return null;
      }
      
      // Access the data safely after type verification
      const accountInfo = response.value;
      
      // Convert base64 data to Buffer
      if (Array.isArray(accountInfo.data) && accountInfo.data.length >= 2) {
        const [base64Data, encoding] = accountInfo.data;
        if (encoding === 'base64' && typeof base64Data === 'string') {
          return {
            data: Buffer.from(base64Data, 'base64')
          };
        }
      }
      
      return null;
    } catch (error) {
      console.error('Error fetching mint account:', error);
      return null;
    }
  }
}

/**
 * Create and export a default instance of TokenInfo
 */
export const defaultTokenInfo = new TokenInfo();

/**
 * Convenience function to create a new TokenInfo instance
 * 
 * @param rpcClient - Solana RPC client instance
 * @returns A new TokenInfo instance
 */
export function createTokenInfo(rpcClient?: SolanaRpcClient): TokenInfo {
  return new TokenInfo(rpcClient);
}

/**
 * Standalone function to get token decimals without creating a TokenInfo instance
 * 
 * @param mintAddress - The address of the token mint
 * @param rpcClient - Optional Solana RPC client instance
 * @returns The number of decimal places the token uses
 */
export async function getTokenDecimals(
  mintAddress: string, 
  rpcClient: SolanaRpcClient = defaultSolanaRpcClient
): Promise<number> {
  const tokenInfo = new TokenInfo(rpcClient);
  return tokenInfo.getTokenDecimals(mintAddress);
} 