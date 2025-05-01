/**
 * Error classes for utility operations
 */

/**
 * Base error class for utility errors
 */
export class UtilError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'UtilError';
  }
}

/**
 * Error thrown when a network operation fails
 */
export class SolNetworkError extends UtilError {
  constructor(message: string) {
    super(message);
    this.name = 'SolNetworkError';
  }
}

/**
 * Error thrown when a configuration is invalid
 */
export class ConfigurationError extends UtilError {
  constructor(message: string) {
    super(message);
    this.name = 'ConfigurationError';
  }
}

/**
 * Error thrown when a validation fails
 */
export class ValidationError extends UtilError {
  constructor(message: string) {
    super(message);
    this.name = 'ValidationError';
  }
}

/**
 * Error thrown when a serialization or deserialization operation fails
 */
export class SerializationError extends UtilError {
  constructor(message: string) {
    super(message);
    this.name = 'SerializationError';
  }
}

/**
 * Error classes related to Solana network operations
 */

/**
 * Error thrown when a transaction fails to confirm within the expected timeframe
 */
export class TxTimeoutError extends SolNetworkError {
  constructor(message: string) {
    super(message);
    this.name = 'TxTimeoutError';
  }
}

/**
 * Error thrown when a transaction is rejected by the network
 */
export class TxRejectError extends SolNetworkError {
  constructor(message: string) {
    super(message);
    this.name = 'TxRejectError';
  }
}

/**
 * Error thrown when RPC endpoint returns an error
 */
export class RpcError extends SolNetworkError {
  constructor(message: string) {
    super(message);
    this.name = 'RpcError';
  }
}

/**
 * Error thrown when the rate limit is exceeded
 */
export class RateLimitError extends SolNetworkError {
  constructor(message: string) {
    super(message);
    this.name = 'RateLimitError';
  }
}

/**
 * Error classes related to transaction operations
 */

/**
 * Error thrown when an instruction parameter is invalid
 */
export class InvalidInstructionParameterError extends UtilError {
  constructor(message: string) {
    super(message);
    this.name = 'InvalidInstructionParameterError';
  }
}

/**
 * Error thrown when transaction creation fails
 */
export class TransactionCreationError extends UtilError {
  constructor(message: string) {
    super(message);
    this.name = 'TransactionCreationError';
  }
}

/**
 * Error thrown when serialization or format of a transaction is invalid
 */
export class InvalidTransactionFormatError extends UtilError {
  constructor(message: string) {
    super(message);
    this.name = 'InvalidTransactionFormatError';
  }
} 