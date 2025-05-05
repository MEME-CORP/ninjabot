# Jupiter Volume Testing Scripts

These scripts are part of Phase 3 of the Solana Mainnet Validation plan, focusing on testing token swaps using the Jupiter Aggregator.

## Setup

Before running these scripts, make sure you have:

1. Created a mainnet mother wallet (`npm run test:mainnet-wallet`)
2. Generated child wallets (`npm run test:mainnet-child-wallets`)
3. Installed the required dependencies:
   ```
   npm install --save node-fetch@2 @solana/spl-token-registry
   ```

## Available Scripts

The following scripts are available for Jupiter volume testing:

### 1. Fund Child Wallets

Funds child wallets from the mother wallet with a specified amount of SOL.

```
npm run jupiter:fund -- --amount 0.002 --wallets 0,1
```

Options:
- `--amount` or `-a`: Amount of SOL to send (default: 0.005 SOL)
- `--wallets` or `-w`: Comma-separated list of wallet indices to fund (default: 0,1)

### 2. Get Token Swap Quote

Gets a quote for a token swap from the Jupiter API.

```
npm run jupiter:quote -- --amount 1000000 --input-token SOL --output-token USDC
```

Options:
- `--amount` or `-a`: Amount to swap in smallest units (lamports for SOL, etc.)
- `--input-token` or `-i`: Input token (SOL, USDC, USDT, BONK, or address)
- `--output-token` or `-o`: Output token (SOL, USDC, USDT, BONK, or address)

### 3. Buy Tokens with SOL

Swaps SOL for tokens using the Jupiter Aggregator.

```
npm run jupiter:buy -- --amount 0.001 --wallet-index 0 --token USDC
```

Options:
- `--amount` or `-a`: Amount of SOL to swap (default: 0.001 SOL)
- `--wallet-index` or `-w`: Index of the child wallet to use (default: 0)
- `--token` or `-t`: Token to buy (SOL, USDC, USDT, BONK, or address) (default: USDC)

### 4. Sell Tokens for SOL

Swaps tokens back to SOL using the Jupiter Aggregator.

```
npm run jupiter:sell -- --wallet-index 0 --token USDC
```

Options:
- `--amount` or `-a`: Amount of tokens to swap (default: 90% of balance)
- `--wallet-index` or `-w`: Index of the child wallet to use (default: 0)
- `--token` or `-t`: Token to sell (SOL, USDC, USDT, BONK, or address) (default: USDC)

### 5. Run Complete Volume Test

Runs the full Jupiter volume testing workflow, including funding, buying, selling, and reporting.

```
npm run jupiter:volume -- --amount 0.002 --wallets 0,1 --token USDC
```

Options:
- `--amount` or `-a`: Amount of SOL to use per wallet (default: 0.002 SOL)
- `--wallets` or `-w`: Comma-separated list of wallet indices to use (default: 0,1)
- `--token` or `-t`: Token to use for swaps (SOL, USDC, USDT, BONK, or address) (default: USDC)

## Test Results

The complete volume test will generate a report file `jupiter-volume-report.json` in the project root directory, containing details about:

- Test configuration
- Transaction signatures
- Total volume (SOL and token)
- Success/failure statistics

## Important Notes

- These scripts use REAL SOL and perform REAL transactions on Solana mainnet.
- Always use small amounts for testing (0.001-0.002 SOL recommended per wallet).
- The scripts include retry logic and transaction confirmation handling to ensure reliable operation with Solana mainnet.
- A buffer of approximately 0.01 SOL is needed for fees and rent exemption.
- The scripts automatically create Associated Token Accounts (ATAs) when needed.

## Common Token Addresses

- SOL: `So11111111111111111111111111111111111111112`
- USDC: `EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v`
- USDT: `Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB`
- BONK: `DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263` 