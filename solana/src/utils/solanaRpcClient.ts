import { Connection, PublicKey, Commitment, GetAccountInfoConfig, SendOptions } from '@solana/web3.js';
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
      const response = await this.connection.getLatestBlockhash();
      return {
        blockhash: response.blockhash,
        lastValidBlockHeight: response.lastValidBlockHeight
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
      const balance = await this.connection.getBalance(new PublicKey(address));
      return {
        context: { slot: await this.connection.getSlot() },
        value: balance
      };
    } catch (error) {
      throw new SolNetworkError(`Failed to get balance: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  /**
   * Gets account information
   */
  async getAccountInfo(address: string, encoding = 'base64'): Promise<AccountInfoResponse> {
    try {
      const config: GetAccountInfoConfig = { commitment: 'confirmed' };
      const accountInfo = await this.connection.getAccountInfo(new PublicKey(address), config);
      return {
        context: { slot: await this.connection.getSlot() },
        value: accountInfo ? {
          data: [Buffer.from(accountInfo.data).toString('base64'), encoding],
          executable: accountInfo.executable,
          lamports: accountInfo.lamports,
          owner: accountInfo.owner.toString()
        } : null
      };
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
      const ownerPublicKey = new PublicKey(owner);
      const filterKey = filter.mint 
        ? { mint: new PublicKey(filter.mint) } 
        : { programId: new PublicKey(filter.programId!) };
      
      const accounts = await this.connection.getTokenAccountsByOwner(
        ownerPublicKey,
        filterKey,
        { commitment: 'confirmed' }
      );
      
      return {
        context: { slot: await this.connection.getSlot() },
        value: accounts.value.map(item => ({
          pubkey: item.pubkey.toString(),
          account: {
            data: [Buffer.from(item.account.data).toString('base64'), 'base64'],
            executable: item.account.executable,
            lamports: item.account.lamports,
            owner: item.account.owner.toString()
          }
        }))
      };
    } catch (error) {
      throw new SolNetworkError(`Failed to get token accounts: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  /**
   * Gets recent prioritization fees
   */
  async getRecentPrioritizationFees(): Promise<PrioritizationFeesResponse> {
    try {
      // In web3.js v1 we need to call the RPC method directly since there's no getRecentPrioritizationFees helper
      const response = await this.connection.getRecentPrioritizationFees();
      return { 
        value: response.map(fee => ({
          slot: fee.slot,
          prioritizationFee: fee.prioritizationFee
        })) 
      };
    } catch (error) {
      throw new SolNetworkError(`Failed to get prioritization fees: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  /**
   * Sends a transaction
   */
  async sendTransaction(
    transaction: any, 
    options: { skipPreflight?: boolean; maxRetries?: number; preflightCommitment?: Commitment } = {}
  ): Promise<string> {
    try {
      const sendOptions: SendOptions = {
        skipPreflight: options.skipPreflight,
        maxRetries: options.maxRetries,
        preflightCommitment: options.preflightCommitment
      };
      
      const signature = await this.connection.sendTransaction(
        transaction,
        [],
        sendOptions
      );
      return signature;
    } catch (error) {
      throw new SolNetworkError(`Failed to send transaction: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  /**
   * Confirms a transaction
   */
  async confirmTransaction(
    transaction: { signature: string; blockhash: string; lastValidBlockHeight: number },
    commitment: Commitment = 'confirmed'
  ): Promise<TransactionConfirmationResponse> {
    try {
      const result = await this.connection.confirmTransaction(
        {
          signature: transaction.signature,
          blockhash: transaction.blockhash,
          lastValidBlockHeight: transaction.lastValidBlockHeight
        },
        commitment
      );
      
      return {
        context: { slot: result.context.slot },
        value: {
          err: result.value.err,
          confirmations: null
        }
      };
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