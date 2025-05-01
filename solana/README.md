# NinjaBot Solana Module

This module provides Solana blockchain integration for the NinjaBot application. It manages wallet creation, token transfers, and fee collection on the Solana blockchain.

## Features

- Wallet management (mother wallet and child wallets)
- Transaction scheduling and execution
- Fee management and collection
- Priority fee optimization
- Transaction retry mechanisms

## Modules

### SolanaRpcClient

A wrapper around the Solana web3.js v2 RPC client, providing a consistent interface for making RPC calls to the Solana blockchain.

### WalletManager

Provides functionality for creating, importing, and managing Solana wallets. Supports:
- Creating new wallets with mnemonic phrases
- Importing wallets from mnemonics or private keys
- Deriving child wallets using BIP44 derivation paths

### Scheduler

Generates transaction schedules for distributing tokens among wallets. Features:
- Creation of randomized, unique amounts that sum to a specified total
- Verification of transfer operations
- Round-robin transfer patterns

### FeeOracle

Provides functionality for determining optimal transaction fees and detecting fee spikes. Features:
- Fetching current network priority fees
- Setting fee thresholds to detect spikes
- Calculating optimal fees for successful transactions

### TokenInfo

Provides functionality for retrieving token information from the Solana blockchain. Features:
- Fetching token decimal places from a mint address
- Validating token mint addresses
- Getting token supply information
- Handling network errors with sensible defaults

## Implementation Status

The project is being implemented in stages:

1. ✅ SolanaRpcClient - Basic RPC wrapper
2. ✅ WalletManager - Wallet creation and derivation
3. ✅ Scheduler - Transaction scheduling
4. ✅ FeeOracle - Fee estimation and spike detection
5. ✅ TokenInfo - Token metadata helper
6. ⬜ FeeCollector - Service fee management
7. ⬜ TxExecutor - Transaction execution with retries
8. ⬜ Integration with database and UI

## Setup

### Prerequisites

- Node.js (LTS version recommended)
- npm or yarn

### Installation

```bash
# Install dependencies
npm install

# Build the project
npm run build

# Run tests
npm test
```

## Development

### Project Structure

- `src/`: Source code
  - `config.ts`: Configuration constants and settings
  - `utils/`: Utility modules
    - `solanaRpcClient.ts`: Solana RPC client for blockchain interaction
  - `wallet/`: Wallet management modules
  - `scheduler/`: Transaction scheduling modules
  - `fees/`: Fee calculation and collection modules
  - `transactions/`: Transaction building and execution modules

### Testing

All modules have corresponding test files in the `tests/` directory. Tests can be run using:

```bash
npm test
```

## Usage

This module will be integrated with the NinjaBot Telegram bot application to provide Solana blockchain functionality.

## Solana Integration for Ninjabot

This module provides the core Solana blockchain integration for Ninjabot, with support for:

- Wallet creation and management
- Transaction scheduling and execution
- Fee management
- Token transfers
- Error handling and retry mechanics

### Getting Started

1. Install dependencies:
```bash
npm install
```

2. Build the project:
```bash
npm run build
```

3. Run tests:
```bash
npm test
```

### Solana Devnet Integration

This module includes a complete integration with Solana's Devnet for testing and demonstration:

1. Create a mother wallet and child wallets
2. Fund child wallets from the mother wallet
3. Schedule transfers between child wallets with fee collection
4. Execute the transfers on Solana devnet

#### Running the Integration

To run the integration test on Solana devnet:

```bash
npm run integration
```

Or with custom parameters:

```bash
npm run integration -- --children 5 --funding 0.2 --volume 0.1
```

Available options:
- `--children` or `-c`: Number of child wallets to create (default: 3)
- `--funding` or `-f`: Amount of SOL to fund each child wallet with (default: 0.1)
- `--volume` or `-v`: Total volume of SOL to transfer (default: 0.05)
- `--token` or `-t`: Token mint address for token transfers (default: null, uses SOL)

#### Integration Tests

The integration module includes tests that connect to Solana devnet:

```bash
npm run test:integration
```

These tests create real wallets on devnet without executing transactions.

### Wallet Storage

Mother and child wallets are stored in the `wallet-storage` directory in JSON format. This allows
for persistence between runs and manual inspection of wallet addresses.

**Warning**: In production, private keys should be stored in a secure environment, not in plain text files.

### Transaction Module

The transaction executor (`txExecutor`) provides:

- SOL transfers between wallets
- SPL token transfers
- Fee spike detection
- Comprehensive error handling
- Retry mechanisms for transient errors

### Integration with Python Bot

The Solana module is designed to be integrated with the Python bot via:

1. Command-line interface: Run operations through scripts
2. API: Add a simple REST API layer on top (future enhancement)
3. Direct integration: Import the compiled JS code from Python using appropriate bindings 