# WalletFunder Module

The WalletFunder module is responsible for funding child wallets from a mother wallet in the Solana blockchain. It handles chunking transfers to stay within transaction limits, provides comprehensive error handling with retries, and emits events for reporting transaction status.

## Features

- Funds multiple child wallets from a mother wallet
- Chunks transfers to stay within transaction limits
- Verifies mother wallet has sufficient balance before proceeding
- Implements robust error handling with configurable retries
- Emits events for transaction status reporting
- Tracks successful and failed transactions
- Calculates and estimates transaction fees

## Usage

```typescript
import { Keypair } from '@solana/web3.js';
import { WalletFunder, createWalletFunder } from './walletFunder';

// Create a wallet funder instance
const walletFunder = createWalletFunder();

// Set up event listeners
walletFunder.on('funding_started', (data) => {
  console.log('Funding started:', data);
});

walletFunder.on('funding_completed', (result) => {
  console.log('Funding completed:', result);
});

walletFunder.on('transaction_confirmed', (data) => {
  console.log('Transaction confirmed:', data);
});

// Fund child wallets
const motherWallet = // Your mother wallet keypair
const childAddresses = [
  // Array of child wallet addresses
];

const amountPerChild = 100000000n; // 0.1 SOL per child

// Execute funding operation
const result = await walletFunder.fundChildWallets(
  motherWallet,
  childAddresses,
  amountPerChild,
  {
    // Optional configuration
    skipPreflight: false,
    maxRetries: 3, 
    retryDelayMs: 2000,
    confirmationTimeoutMs: 60000,
    priorityFee: 1000n, // In micro-lamports
    maxChildrenPerChunk: 5
  }
);

console.log(`Successfully funded ${result.successfulTransactions} transactions`);
console.log(`Failed ${result.failedTransactions} transactions`);
console.log(`Total funded amount: ${result.totalFundedAmount} lamports`);
console.log(`Total fees paid: ${result.totalFees} lamports`);
```

## Monitoring Events

The WalletFunder emits the following events:

- `funding_started`: Emitted when funding operation starts
- `funding_completed`: Emitted when funding operation completes
- `funding_failed`: Emitted when funding operation fails
- `chunk_started`: Emitted when a chunk of child wallets is about to be funded
- `chunk_completed`: Emitted when a chunk of child wallets has been funded
- `transaction_sent`: Emitted when a transaction is sent
- `transaction_confirmed`: Emitted when a transaction is confirmed
- `transaction_failed`: Emitted when a transaction fails
- `retry_attempt`: Emitted when a retry is attempted

## Error Handling

WalletFunder implements robust error handling:

- Validates inputs before proceeding
- Verifies mother wallet has sufficient balance
- Retries failed transactions with configurable backoff
- Distinguishes between retryable and non-retryable errors
- Reports detailed error information through events

## Integration Testing

To run the integration tests, you need a local Solana test validator running:

1. Start a local validator: `solana-test-validator`
2. Run the integration tests: `npm run test:integration` 