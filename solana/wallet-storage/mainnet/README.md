# Solana Mainnet Wallet Storage

This directory contains wallets for use with the Solana mainnet. These wallets can hold REAL SOL and tokens with actual monetary value.

## ⚠️ IMPORTANT WARNINGS ⚠️

1. **REAL FUNDS**: Wallets in this directory can hold real SOL with actual monetary value.
2. **SECURITY**: Keep this directory secure and never commit wallet files to source control.
3. **BACKUPS**: Consider backing up wallet files, especially the mother wallet.
4. **SMALL AMOUNTS**: Only use small test amounts when working with mainnet wallets.

## Directory Structure

- `mother-wallet.json` - The primary wallet that funds child wallets
- `child-wallets.json` - Child wallets for testing transactions

## Usage Instructions

### Testing Process

Follow this sequence of scripts for safe testing:

1. `npm run test:mainnet-wallet` - Creates a new mother wallet
2. Manually fund the mother wallet with a small amount of SOL (e.g., 0.01 SOL)
3. `npm run test:mainnet-child-wallets` - Creates child wallets
4. `npm run test:mainnet-funding` - Funds child wallets from mother wallet
5. `npm run test:mainnet-transfer` - Tests transfers between child wallets
6. `npm run test:mainnet-return` - Returns funds to mother wallet

### Complete Integration Script

Use `npm run mainnet-integration` to run a complete integration process. This script requires a confirmation before proceeding and uses very small default values.

## Verification

Always verify transactions on [Solscan](https://solscan.io/) by checking wallet addresses and transaction signatures.

## Recovery

If you need to sweep funds from test wallets, use `npm run test:mainnet-return` which will return funds to the mother wallet.

## Safety Guidelines

1. Double-check all transaction amounts before confirming
2. Start with very small amounts (e.g., 0.001 SOL)
3. Monitor transactions on Solscan
4. Backup wallet files securely
5. Never publish or share wallet private keys

## Support

For issues or questions, please contact the development team. 