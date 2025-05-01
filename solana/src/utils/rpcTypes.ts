/**
 * Type definitions for Solana RPC responses
 * These types help with proper typing of the responses from Solana RPC methods
 */

/**
 * Balance response from getBalance RPC method
 */
export interface BalanceResponse {
  context: {
    slot: number;
  };
  value: number | bigint;
}

/**
 * Account info response from getAccountInfo RPC method
 */
export interface AccountInfoResponse {
  context: {
    slot: number;
  };
  value: {
    data: [string, string]; // [encoded data, encoding]
    executable: boolean;
    lamports: number | bigint;
    owner: string;
    rentEpoch?: number;
  } | null;
}

/**
 * Token account response from getTokenAccountsByOwner RPC method
 */
export interface TokenAccountsByOwnerResponse {
  context: {
    slot: number;
  };
  value: Array<{
    pubkey: string;
    account: {
      data: [string, string];
      executable: boolean;
      lamports: number | bigint;
      owner: string;
      rentEpoch?: number;
    };
  }>;
}

/**
 * Prioritization fees response from getRecentPrioritizationFees RPC method
 */
export interface PrioritizationFeesResponse {
  context?: {
    slot: number;
  };
  value: Array<{
    slot: number;
    prioritizationFee: number | bigint;
  }>;
}

/**
 * Transaction confirmation response
 */
export interface TransactionConfirmationResponse {
  context: {
    slot: number;
  };
  value: {
    err: any | null;
    status?: { Ok: null } | { Err: any };
    confirmations?: number | null;
  };
}

/**
 * Type guard to check if a response is a BalanceResponse
 */
export function isBalanceResponse(response: unknown): response is BalanceResponse {
  return (
    response !== null &&
    typeof response === 'object' &&
    'value' in response
  );
}

/**
 * Type guard to check if a response is an AccountInfoResponse
 */
export function isAccountInfoResponse(response: unknown): response is AccountInfoResponse {
  return (
    response !== null &&
    typeof response === 'object' &&
    'value' in response
  );
}

/**
 * Type guard to check if a response is a TokenAccountsByOwnerResponse
 */
export function isTokenAccountsByOwnerResponse(response: unknown): response is TokenAccountsByOwnerResponse {
  return (
    response !== null &&
    typeof response === 'object' &&
    'value' in response &&
    Array.isArray((response as any).value)
  );
}

/**
 * Type guard to check if a response is a PrioritizationFeesResponse
 */
export function isPrioritizationFeesResponse(response: unknown): response is PrioritizationFeesResponse {
  return (
    response !== null &&
    typeof response === 'object' &&
    'value' in response &&
    Array.isArray((response as any).value)
  );
}

/**
 * Type guard to check if a response is a TransactionConfirmationResponse
 */
export function isTransactionConfirmationResponse(response: unknown): response is TransactionConfirmationResponse {
  return (
    response !== null &&
    typeof response === 'object' &&
    'value' in response &&
    typeof (response as any).value === 'object'
  );
} 