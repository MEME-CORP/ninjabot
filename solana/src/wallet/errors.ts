/**
 * Error classes for wallet operations
 */

/**
 * Base wallet error class
 */
export class WalletError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'WalletError';
  }
}

/**
 * Error thrown when wallet derivation fails
 */
export class WalletDerivationError extends WalletError {
  constructor(message: string) {
    super(message);
    this.name = 'WalletDerivationError';
  }
}

/**
 * Error thrown when a wallet is not found
 */
export class WalletNotFoundError extends WalletError {
  constructor(message: string) {
    super(message);
    this.name = 'WalletNotFoundError';
  }
}

/**
 * Error thrown when a wallet signature fails
 */
export class WalletSignatureError extends WalletError {
  constructor(message: string) {
    super(message);
    this.name = 'WalletSignatureError';
  }
}

/**
 * Error thrown when a wallet balance is insufficient
 */
export class InsufficientBalanceError extends WalletError {
  constructor(message: string) {
    super(message);
    this.name = 'InsufficientBalanceError';
  }
}

/**
 * Error thrown when a wallet operation is unauthorized
 */
export class UnauthorizedWalletOperationError extends WalletError {
  constructor(message: string) {
    super(message);
    this.name = 'UnauthorizedWalletOperationError';
  }
}

/**
 * Error thrown when there's an issue with wallet import
 */
export class WalletImportError extends WalletError {
  constructor(message: string) {
    super(message);
    this.name = 'WalletImportError';
  }
} 