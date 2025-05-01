import { Connection } from '@solana/web3.js';
import { SolNetworkError } from './errors';
import { 
  BalanceResponse, 
  AccountInfoResponse, 
  TokenAccountsByOwnerResponse,
  PrioritizationFeesResponse,
  TransactionConfirmationResponse
} from './rpcTypes';

/**
 * Extended RPC client that provides type-safe methods
 */
export class SolanaRpcClient {
  public rpc: any;
  public connection: Connection;

  constructor(endpoint: string) {
    this.connection = new Connection(endpoint);
    this.rpc = this.connection;
  }

  /**
   * Gets the latest blockhash and last valid block height
   */
  async getLatestBlockhash(): Promise<{ blockhash: string; lastValidBlockHeight: number }> {
    try {
      const { value } = await this.rpc.getLatestBlockhash().send();
      return {
        blockhash: value.blockhash,
        lastValidBlockHeight: value.lastValidBlockHeight
      };
    } catch (error) {
      throw new SolNetworkError(`Failed to get latest blockhash: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  /**
   * Gets the balance of an account
   */
  async getBalance(address: string): Promise<BalanceResponse> {
    try {
      const response = await this.rpc.getBalance(address).send();
      return response as BalanceResponse;
    } catch (error) {
      throw new SolNetworkError(`Failed to get balance: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  /**
   * Gets account information
   */
  async getAccountInfo(address: string, encoding = 'base64'): Promise<AccountInfoResponse> {
    try {
      const response = await this.rpc.getAccountInfo(address, { encoding }).send();
      return response as AccountInfoResponse;
    } catch (error) {
      throw new SolNetworkError(`Failed to get account info: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  /**
   * Gets token accounts by owner
   */
  async getTokenAccountsByOwner(
    owner: string, 
    filter: { mint?: string; programId?: string }, 
    config: { encoding?: string } = { encoding: 'jsonParsed' }
  ): Promise<TokenAccountsByOwnerResponse> {
    try {
      const response = await this.rpc.getTokenAccountsByOwner(owner, filter, config).send();
      return response as TokenAccountsByOwnerResponse;
    } catch (error) {
      throw new SolNetworkError(`Failed to get token accounts: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  /**
   * Gets recent prioritization fees
   */
  async getRecentPrioritizationFees(): Promise<PrioritizationFeesResponse> {
    try {
      const response = await this.rpc.getRecentPrioritizationFees().send();
      return response as PrioritizationFeesResponse;
    } catch (error) {
      throw new SolNetworkError(`Failed to get prioritization fees: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  /**
   * Sends a transaction
   */
  async sendTransaction(
    transaction: any, 
    options: { skipPreflight?: boolean; maxRetries?: number; preflightCommitment?: string } = {}
  ): Promise<string> {
    try {
      const response = await this.rpc.sendTransaction(transaction, options).send();
      return response as string;
    } catch (error) {
      throw new SolNetworkError(`Failed to send transaction: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  /**
   * Confirms a transaction
   */
  async confirmTransaction(
    transaction: { signature: string; blockhash: string; lastValidBlockHeight: number },
    commitment = 'confirmed'
  ): Promise<TransactionConfirmationResponse> {
    try {
      const response = await this.rpc.confirmTransaction(transaction, commitment).send();
      return response as TransactionConfirmationResponse;
    } catch (error) {
      throw new SolNetworkError(`Failed to confirm transaction: ${error instanceof Error ? error.message : String(error)}`);
    }
  }
}

/**
 * Create and export a default instance of SolanaRpcClient
 */
export const defaultSolanaRpcClient = new SolanaRpcClient(
  process.env.SOLANA_RPC_URL || 'https://api.devnet.solana.com'
);

/**
 * Convenience function to create a new SolanaRpcClient instance
 */
export function createSolanaRpcClient(endpoint: string): SolanaRpcClient {
  return new SolanaRpcClient(endpoint);
} 