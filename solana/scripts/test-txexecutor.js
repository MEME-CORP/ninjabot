/**
 * Script to run TxExecutor tests directly with jest
 * This bypasses the TypeScript type-checking for other modules
 * that are not part of the current task.
 */
const { execSync } = require('child_process');
const path = require('path');

// Path to jest binary
const jestBin = path.resolve(__dirname, '../node_modules/.bin/jest');

// Run just the TxExecutor tests
try {
  execSync(`${jestBin} tests/transactions/txExecutor.test.ts --testEnvironment=node --no-cache --ts-config=tests/tsconfig.json`, {
    stdio: 'inherit'
  });
  console.log('TxExecutor tests completed successfully!');
} catch (error) {
  console.error('Error running TxExecutor tests:', error.message);
  process.exit(1);
} 