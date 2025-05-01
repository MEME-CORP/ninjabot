import { WalletManager } from '../../src/wallet/walletManager';
import { jest } from '@jest/globals';

// Mock the dependencies
jest.mock('bip39', () => ({
  generateMnemonic: jest.fn().mockReturnValue('test mnemonic'),
  validateMnemonic: jest.fn().mockReturnValue(true),
  mnemonicToSeed: jest.fn().mockResolvedValue(new Uint8Array(32)),
}));

jest.mock('ed25519-hd-key', () => ({
  derivePath: jest.fn().mockReturnValue({ key: new Uint8Array(32) }),
}));

jest.mock('@solana/kit', () => ({
  generateKeyPairSigner: jest.fn().mockResolvedValue({
    address: 'test-address',
    signMessages: jest.fn(),
    signTransactions: jest.fn(),
  }),
  createKeyPairFromBytes: jest.fn(),
  createKeyPairSignerFromBytes: jest.fn().mockResolvedValue({
    address: 'test-address',
    signMessages: jest.fn(),
    signTransactions: jest.fn(),
  }),
}));

describe('WalletManager', () => {
  let walletManager: WalletManager;
  
  beforeEach(() => {
    walletManager = new WalletManager();
  });
  
  test('should create a mother wallet', async () => {
    const result = await walletManager.createMotherWallet();
    expect(result.mnemonic).toBe('test mnemonic');
  });
  
  test('should import a wallet from mnemonic', async () => {
    const result = await walletManager.importMotherWalletFromMnemonic('test mnemonic');
    expect(result.signer).toBeDefined();
  });
  
  test('should import a wallet from private key', async () => {
    const result = await walletManager.importMotherWallet(new Uint8Array(32));
    expect(result).toBeDefined();
  });
  
  test('should derive a child wallet', async () => {
    const result = await walletManager.deriveChildWallet(new Uint8Array(32), 0);
    expect(result).toBeDefined();
  });
  
  test('should get address from signer', () => {
    const mockSigner = { address: 'test-address' };
    const result = walletManager.getAddress(mockSigner as any);
    expect(result).toBe('test-address');
  });
}); 