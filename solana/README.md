Ninja


# Solana Trading Bot API

A comprehensive API for a Solana trading bot with Jupiter DEX integration. This API provides endpoints for wallet management, Jupiter DEX interaction, and fund management.

## Table of Contents

- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Running the API](#running-the-api)
- [API Endpoints](#api-endpoints)
  - [Wallet Management](#wallet-management)
  - [Jupiter DEX Integration](#jupiter-dex-integration)
- [Testing](#testing)
- [Deployment](#deployment)
- [Architecture](#architecture)
- [Security Considerations](#security-considerations)

## Getting Started

### Prerequisites

- Node.js v16 or higher
- npm v7 or higher
- Access to a Solana RPC endpoint

### Installation

1. Clone the repository
2. Navigate to the `solana` directory
3. Install dependencies:

```bash
npm install
```

4. Verify dependencies with the provided script:

```bash
./check-dependencies.ps1
```

### Running the API

The API provides several methods to start the server:

1. Using the simple starter script:

```bash
./start-api.bat
```

2. Using the robust server starter with error handling:

```bash
./run-api-server.cmd
```

3. Directly using Node.js:

```bash
node api/index.js
```

The API will start on port 3000 by default. You can change this by setting the `PORT` environment variable.

## API Endpoints

The API provides the following categories of endpoints:

### Wallet Management

#### Create/Import Mother Wallet

- **Endpoint**: `POST /api/wallets/mother`
- **Description**: Creates a new mother wallet or imports an existing one from a private key.
- **Request Body**:
  ```json
  {
    "privateKeyBase58": "optional_base58_encoded_private_key"
  }
  ```
- **Response**:
  ```json
  {
    "message": "Mother wallet created/imported successfully.",
    "motherWalletPublicKey": "wallet_public_key",
    "motherWalletPrivateKeyBase58": "wallet_private_key_base58"
  }
  ```

#### Get Mother Wallet Info

- **Endpoint**: `GET /api/wallets/mother/:publicKey`
- **Description**: Gets information about a mother wallet, including its balance.
- **Response**:
  ```json
  {
    "publicKey": "wallet_public_key",
    "balanceSol": 0.0,
    "balanceLamports": 0
  }
  ```

#### Derive Child Wallets

- **Endpoint**: `POST /api/wallets/children`
- **Description**: Derives child wallets from a mother wallet.
- **Request Body**:
  ```json
  {
    "motherWalletPublicKey": "mother_wallet_public_key",
    "count": 3,
    "saveToFile": false
  }
  ```
- **Response**:
  ```json
  {
    "message": "Child wallets derived successfully.",
    "motherWalletPublicKey": "mother_wallet_public_key",
    "childWallets": [
      {
        "publicKey": "child_wallet_public_key",
        "privateKeyBase58": "child_wallet_private_key_base58"
      },
      // More child wallets...
    ]
  }
  ```

#### Fund Child Wallets

- **Endpoint**: `POST /api/wallets/fund-children`
- **Description**: Funds child wallets from a mother wallet.
- **Request Body**:
  ```json
  {
    "motherWalletPrivateKeyBase58": "mother_wallet_private_key_base58",
    "childWallets": [
      {
        "publicKey": "child_wallet_public_key",
        "amountSol": 0.002
      },
      // More child wallets...
    ]
  }
  ```
- **Response**:
  ```json
  {
    "status": "success|partial|failed",
    "results": [
      {
        "childPublicKey": "child_wallet_public_key",
        "transactionId": "transaction_signature",
        "status": "funded|failed",
        "error": "optional_error_message",
        "newBalanceSol": 0.002
      },
      // More results...
    ],
    "motherWalletFinalBalanceSol": 0.998,
    "message": "Child wallets funding completed."
  }
  ```

#### Return Funds to Mother Wallet

- **Endpoint**: `POST /api/wallets/return-funds`
- **Description**: Returns funds from a child wallet to a mother wallet.
- **Request Body**:
  ```json
  {
    "childWalletPrivateKeyBase58": "child_wallet_private_key_base58",
    "motherWalletPublicKey": "mother_wallet_public_key",
    "returnAllFunds": false
  }
  ```
- **Response**:
  ```json
  {
    "status": "success|failed",
    "transactionId": "transaction_signature",
    "amountReturnedSol": 0.0018,
    "childWalletFinalBalanceSol": 0.0002,
    "message": "Funds returned to mother wallet successfully."
  }
  ```

### Jupiter DEX Integration

#### Get Jupiter Swap Quote

- **Endpoint**: `POST /api/jupiter/quote`
- **Description**: Gets a swap quote from Jupiter DEX.
- **Request Body**:
  ```json
  {
    "inputMint": "SOL",
    "outputMint": "USDC",
    "amount": 1000000,
    "slippageBps": 50,
    "onlyDirectRoutes": false,
    "asLegacyTransaction": false,
    "platformFeeBps": 0
  }
  ```
- **Response**:
  ```json
  {
    "message": "Jupiter quote retrieved successfully",
    "quoteResponse": {
      // Full Jupiter quote response
      "inAmount": "1000000",
      "outAmount": "12345678",
      "amount": "1000000",
      "otherAmountThreshold": "12222222",
      // Additional fields...
    }
  }
  ```

#### Execute Jupiter Swap

- **Endpoint**: `POST /api/jupiter/swap`
- **Description**: Executes a swap on Jupiter DEX with optional fee collection.
- **Request Body**:
  ```json
  {
    "userWalletPrivateKeyBase58": "user_wallet_private_key_base58",
    "quoteResponse": {
      // Full Jupiter quote response from /quote endpoint
    },
    "wrapAndUnwrapSol": true,
    "asLegacyTransaction": false,
    "collectFees": true
  }
  ```
- **Response**:
  ```json
  {
    "message": "Swap executed successfully",
    "status": "success",
    "transactionId": "swap_transaction_signature",
    "feeCollection": {
      "status": "success|failed|skipped",
      "transactionId": "fee_transaction_signature",
      "feeAmount": 0.0001,
      "feeTokenMint": "fee_token_mint"
    },
    "newBalanceSol": 0.5123
  }
  ```

#### Get Supported Tokens

- **Endpoint**: `GET /api/jupiter/tokens`
- **Description**: Gets a list of tokens supported by the API for Jupiter swaps.
- **Response**:
  ```json
  {
    "message": "Supported tokens retrieved successfully",
    "tokens": {
      "SOL": "So11111111111111111111111111111111111111112",
      "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
      "USDT": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
      "BONK": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
    }
  }
  ```

## Testing

The API comes with several test scripts to verify its functionality:

1. **API Connectivity Test**:
   ```bash
   ./api-test.ps1
   ```

2. **Wallet API Test**:
   ```bash
   ./test-wallet-api.ps1
   ```

3. **Jupiter Quote API Test**:
   ```bash
   ./test-jupiter-api.ps1
   ```

4. **Jupiter Swap API Test**:
   ```bash
   ./test-jupiter-swap-api.ps1
   ```

5. **Return Funds API Test**:
   ```bash
   ./test-return-funds-api.ps1
   ```

All test scripts include safety features to prevent accidental real transactions on Solana mainnet, with simulation modes enabled by default.

## Deployment

### Deploying to Render

[Render](https://render.com/) is a cloud platform that can host your API with minimal configuration. Here's how to deploy the Solana API to Render:

1. **Create a Git Repository**:
   Ensure your code is pushed to a Git repository (GitHub, GitLab, etc.)

2. **Sign up for Render**:
   Create an account at [render.com](https://render.com/)

3. **Create a New Web Service**:
   - Click "New" and select "Web Service"
   - Connect your Git repository
   - Configure the service:
     - **Name**: `solana-trading-bot-api`
     - **Environment**: `Node`
     - **Build Command**: `cd solana && npm install`
     - **Start Command**: `cd solana && node api/index.js`
     - **Plan**: Select according to your needs (Free tier works for testing)

4. **Set Environment Variables**:
   Navigate to "Environment" tab and add any necessary environment variables:
   - `PORT`: `10000` (Render will provide the PORT, but your code should listen on it)
   - `NODE_ENV`: `production`
   - `SOLANA_RPC_URL`: Your Solana RPC endpoint (e.g., a paid service like QuickNode for production)

5. **Deploy**:
   Render will automatically deploy your API when you push changes to your repository.

### Alternative Deployment Options

1. **Digital Ocean App Platform**:
   Similar to Render, with more advanced options for scaling.

2. **AWS Elastic Beanstalk**:
   A more robust solution for production deployments.

3. **Docker + Kubernetes**:
   For advanced deployment scenarios, you can containerize the API with Docker and deploy it on Kubernetes.

## Architecture

The API follows a classic MVC-like architecture:

- **Routes** (`api/routes/`): Define the API endpoints and handle request routing
- **Controllers** (`api/controllers/`): Handle request processing and response generation
- **Services** (`api/services/`): Contain the core business logic

## Security Considerations

1. **Private Key Handling**:
   - The API does not store private keys long-term
   - Private keys are only used for transaction signing
   - Always transmit private keys over HTTPS

2. **Swap Fee Collection**:
   - The API collects a 0.1% fee on swaps by default
   - Fees are collected in the token being swapped

3. **Production Recommendations**:
   - Use a secure RPC endpoint
   - Set up proper authentication
   - Rate limit API requests
   - Monitor for unusual activity
   - Implement input validation to prevent injection attacks
   - Use HTTPS for all API communication 