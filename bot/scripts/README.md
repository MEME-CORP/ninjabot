# SPL Token Buy/Sell Script

A comprehensive Python script for buying and selling SPL tokens across multiple wallets using Jupiter DEX. This script provides automated token swapping with advanced features like multiple execution modes, sophisticated amount distribution strategies, comprehensive error handling, and detailed reporting.

## Features

### 🚀 Core Functionality
- **Multi-wallet Operations**: Execute swaps across multiple child wallets simultaneously
- **Jupiter DEX Integration**: Leverage Jupiter's aggregated liquidity for best prices
- **Flexible Amount Strategies**: Fixed amounts, percentage-based, random ranges, or custom per wallet
- **Multiple Execution Modes**: Sequential, parallel, or batched execution with configurable concurrency

### 🛡️ Safety & Reliability
- **Comprehensive Error Handling**: Automatic retries with exponential backoff
- **Balance Validation**: Pre-execution balance checks and validation
- **Slippage Protection**: Configurable slippage tolerance
- **Dry Run Mode**: Test configurations without real transactions
- **Transaction Verification**: Optional verification of swap completion

### 📊 Monitoring & Reporting
- **Real-time Progress**: Live progress updates during execution
- **Detailed Reports**: JSON, CSV, YAML, and HTML report formats
- **Performance Metrics**: Execution times, success rates, price impact analysis
- **Error Classification**: Categorized error analysis for debugging

### 🔧 Configuration Management
- **Template Generation**: Create configuration templates for common scenarios
- **Wallet Selection**: Flexible wallet selection (all, first N, random, custom)
- **Fee Management**: Optional fee collection for platform revenue

## Quick Start

### 1. Installation
```bash
# Navigate to the bot directory
cd ninjabot/bot

# Install dependencies (if not already installed)
pip install -r ../../requirements.txt
```

### 2. Basic Usage

#### Quick Buy Operation
```bash
# Buy USDC with 0.1 SOL from each wallet
python scripts/spl_buy_sell_script.py \
  --operation buy \
  --input-token SOL \
  --output-token USDC \
  --amount 0.1
```

#### Quick Sell Operation
```bash
# Sell USDC for SOL (0.5 SOL worth per wallet)
python scripts/spl_buy_sell_script.py \
  --operation sell \
  --input-token USDC \
  --output-token SOL \
  --amount 50
```

#### Using Configuration Files
```bash
# Use pre-configured settings
python scripts/spl_buy_sell_script.py --config ../../data/configs/example_buy_config.json
```

### 3. Create Template Configuration
```bash
# Generate a buy template
python scripts/spl_buy_sell_script.py --template buy --output my_buy_config.json

# Generate a sell template  
python scripts/spl_buy_sell_script.py --template sell --output my_sell_config.json
```

## Configuration Guide

### Configuration Structure

The script uses JSON configuration files with the following structure:

```json
{
  "operation": "buy|sell",
  "token_config": {
    "input_token": "SOL",
    "output_token": "USDC"
  },
  "amount_config": {
    "strategy": "fixed|percentage|random|custom",
    // Strategy-specific parameters
  },
  "execution_config": {
    "mode": "sequential|parallel|batch",
    "slippage_bps": 100,
    "verify_swaps": true,
    // Additional execution parameters
  },
  // Wallet and reporting settings
}
```

### Amount Strategies

#### Fixed Amount Strategy
Each wallet uses the same fixed amount:
```json
"amount_config": {
  "strategy": "fixed",
  "base_amount": 0.1
}
```

#### Percentage Strategy
Each wallet uses a percentage of its balance:
```json
"amount_config": {
  "strategy": "percentage", 
  "percentage": 0.5
}
```

#### Random Amount Strategy
Each wallet uses a random amount within a range:
```json
"amount_config": {
  "strategy": "random",
  "min_amount": 0.05,
  "max_amount": 0.25
}
```

#### Custom Amount Strategy
Specify exact amounts per wallet:
```json
"amount_config": {
  "strategy": "custom",
  "custom_amounts": [0.1, 0.15, 0.08, 0.2]
}
```

### Execution Modes

#### Sequential Mode
Execute swaps one after another:
```json
"execution_config": {
  "mode": "sequential",
  "delay_between_swaps": 0.5
}
```

#### Parallel Mode
Execute multiple swaps concurrently:
```json
"execution_config": {
  "mode": "parallel",
  "max_concurrent": 5
}
```

#### Batch Mode
Execute swaps in batches with delays:
```json
"execution_config": {
  "mode": "batch",
  "batch_size": 3,
  "delay_between_batches": 2.0
}
```

### Wallet Selection

#### All Wallets
```json
"wallet_selection": "all"
```

#### First N Wallets
```json
"wallet_selection": "first_n",
"wallet_count": 10
```

#### Random Wallets
```json
"wallet_selection": "random",
"wallet_count": 5
```

#### Custom Wallet Indices
```json
"wallet_selection": "custom",
"custom_wallet_indices": [0, 2, 4, 7, 9]
```

## Supported Tokens

The script supports major SPL tokens with automatic symbol resolution:

- **SOL** (`So11111111111111111111111111111111111111112`)
- **USDC** (`EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v`)
- **USDT** (`Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB`)
- **BONK** (`DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263`)

You can also use full mint addresses for any SPL token supported by Jupiter.

## Command Line Options

### Main Modes
- `--config <file>`: Use configuration file
- `--operation <buy|sell>`: Quick operation mode
- `--template <buy|sell>`: Create template configuration

### Quick Operation Parameters
- `--input-token <token>`: Input token symbol or mint
- `--output-token <token>`: Output token symbol or mint
- `--amount <amount>`: Amount per wallet
- `--wallets <count>`: Number of wallets (0 = all)
- `--mode <sequential|parallel|batch>`: Execution mode

### Global Options
- `--mock`: Use mock mode (no real transactions)
- `--no-confirm`: Skip execution confirmation
- `--log-level <DEBUG|INFO|WARNING|ERROR>`: Logging level
- `--report-format <json|csv|yaml>`: Report format

## Examples

### Example 1: Conservative Buy Operation
```bash
python scripts/spl_buy_sell_script.py \
  --operation buy \
  --input-token SOL \
  --output-token USDC \
  --amount 0.05 \
  --mode sequential \
  --wallets 5
```

### Example 2: Aggressive Sell with Parallel Execution
```bash
python scripts/spl_buy_sell_script.py \
  --operation sell \
  --input-token USDC \
  --output-token SOL \
  --amount 100 \
  --mode parallel
```

### Example 3: Random Amount Buy with Batch Execution
Create a config file for random amounts:
```json
{
  "operation": "buy",
  "token_config": {
    "input_token": "SOL",
    "output_token": "BONK"
  },
  "amount_config": {
    "strategy": "random",
    "min_amount": 0.01,
    "max_amount": 0.1
  },
  "execution_config": {
    "mode": "batch",
    "batch_size": 3,
    "delay_between_batches": 5.0,
    "slippage_bps": 300
  }
}
```

Then run:
```bash
python scripts/spl_buy_sell_script.py --config random_bonk_buy.json
```

### Example 4: Test with Mock Mode
```bash
python scripts/spl_buy_sell_script.py \
  --mock \
  --operation buy \
  --input-token SOL \
  --output-token USDC \
  --amount 0.1 \
  --wallets 3
```

## Testing

Run the comprehensive test suite:

```bash
python scripts/test_buy_sell_script.py
```

The test suite includes:
- Configuration validation tests
- Amount calculation strategy tests
- Single wallet execution tests
- Multi-wallet orchestration tests
- Error handling and recovery tests
- Report generation tests

## Report Examples

### Console Report
```
================================================================================
SPL TOKEN BUY EXECUTION REPORT
================================================================================
Generated: 2024-01-15 14:30:25

CONFIGURATION:
  Operation: buy SOL → USDC
  Amount Strategy: fixed
  Execution Mode: sequential
  Slippage Tolerance: 1.00%

EXECUTION SUMMARY:
  Status: COMPLETED
  Duration: 15.23s
  Total Wallets: 5
  Successful Swaps: 4
  Failed Swaps: 1
  Success Rate: 80.0%

VOLUME SUMMARY:
  Total Input Volume: 0.400000 SOL
  Total Output Volume: 384.250000 USDC
  Average Price Impact: 0.85%
  Total Fees Collected: 0.004000 SOL
```

### JSON Report Structure
```json
{
  "metadata": {
    "generated_at": "2024-01-15T14:30:25",
    "report_version": "1.0"
  },
  "configuration": { ... },
  "execution_summary": {
    "status": "completed",
    "success_rate_percent": 80.0,
    "duration_seconds": 15.23
  },
  "volume_summary": { ... },
  "swap_results": [
    {
      "wallet_index": 0,
      "status": "success",
      "transaction_id": "5k7...",
      "input_amount": 0.1,
      "output_amount": 96.12
    }
  ]
}
```

## Error Handling

The script includes comprehensive error handling:

### Error Types
- **Network Errors**: Automatic retries with exponential backoff
- **Insufficient Balance**: Skip wallet and continue with others
- **Slippage Exceeded**: Retry with higher tolerance or skip
- **Quote Failures**: Refresh quotes and retry
- **Transaction Failures**: Classify and retry appropriately

### Error Recovery
1. **Individual Swap Failures**: Continue with remaining wallets
2. **Partial Execution**: Report successful swaps, note failures
3. **System Failures**: Graceful shutdown with state preservation

## Best Practices

### Security
- **Never log private keys**: All logging excludes sensitive data
- **Use minimum required amounts**: Start with small amounts for testing
- **Test with mock mode**: Always test configurations first

### Performance
- **Batch large operations**: Use batch mode for many wallets
- **Adjust concurrency**: Start with low concurrency, increase gradually
- **Monitor slippage**: Use appropriate slippage for token volatility

### Reliability
- **Enable verification**: Always verify swaps in production
- **Use retries**: Enable retry mechanisms for better success rates
- **Monitor reports**: Review execution reports for patterns

## Troubleshooting

### Common Issues

#### "No wallet data available"
- Ensure you have created and saved child wallets first
- Use `--mock` flag for testing without real wallets

#### "Token pair validation failed"
- Check token symbols are correct (SOL, USDC, USDT, BONK)
- Verify token is supported by Jupiter DEX
- Use full mint addresses for unsupported symbols

#### "Insufficient balance" errors
- Check wallet balances before execution
- Reduce amounts or use percentage strategy
- Ensure minimum balance threshold is appropriate

#### High failure rates
- Increase slippage tolerance
- Reduce concurrency (sequential mode)
- Check network connectivity
- Verify token liquidity on Jupiter

#### Slow execution
- Use parallel mode for better performance
- Reduce delays between operations
- Check network latency

### Debug Mode
Enable debug logging for detailed troubleshooting:
```bash
python scripts/spl_buy_sell_script.py \
  --log-level DEBUG \
  --config your_config.json
```

### Mock Mode Testing
Always test configurations in mock mode first:
```bash
python scripts/spl_buy_sell_script.py \
  --mock \
  --config your_config.json
```

## Configuration Templates

### Conservative Trading
- Sequential execution
- Low slippage tolerance (50-100 bps)
- Verification enabled
- Small fixed amounts

### Aggressive Trading
- Parallel execution
- Higher slippage tolerance (200-500 bps)
- Larger amounts or percentage-based
- Batch execution for efficiency

### Testing Configuration
- Mock mode enabled
- Debug logging
- Small amounts
- Single wallet or few wallets

## Support

For issues or questions:
1. Check the troubleshooting section
2. Review execution logs and reports
3. Test with mock mode to isolate issues
4. Ensure all dependencies are installed correctly

## Version History

### v1.0.0
- Initial release with full functionality
- Support for all major execution modes
- Comprehensive error handling and reporting
- Mock mode for safe testing
- Template configuration system 