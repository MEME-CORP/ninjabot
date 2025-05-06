const express = require('express');
const walletController = require('../controllers/walletController');

const router = express.Router();

/**
 * @swagger
 * /api/wallets/mother:
 *   post:
 *     summary: Create a new mother wallet or import one from a private key.
 *     tags: [Wallet]
 *     requestBody:
 *       required: false
 *       content:
 *         application/json:
 *           schema:
 *             type: object
 *             properties:
 *               privateKeyBase58:
 *                 type: string
 *                 description: Optional base58 encoded private key to import.
 *                 example: "yourBase58PrivateKeyHere..."
 *     responses:
 *       201:
 *         description: Mother wallet created or imported successfully.
 *         content:
 *           application/json:
 *             schema:
 *               type: object
 *               properties:
 *                 message:
 *                   type: string
 *                 motherWalletPublicKey:
 *                   type: string
 *                 motherWalletPrivateKeyBase58:
 *                   type: string
 *       500:
 *         description: Error processing mother wallet request.
 */
router.post('/mother', walletController.createOrImportMotherWalletController);

/**
 * @swagger
 * /api/wallets/mother/{publicKey}:
 *   get:
 *     summary: Get information about a mother wallet, including its balance.
 *     tags: [Wallet]
 *     parameters:
 *       - in: path
 *         name: publicKey
 *         schema:
 *           type: string
 *         required: true
 *         description: The public key of the mother wallet.
 *     responses:
 *       200:
 *         description: Successfully retrieved wallet information.
 *         content:
 *           application/json:
 *             schema:
 *               type: object
 *               properties:
 *                 publicKey:
 *                   type: string
 *                 balanceSol:
 *                   type: number
 *                   description: Wallet balance in SOL
 *                 balanceLamports:
 *                   type: number
 *                   description: Wallet balance in lamports (1 SOL = 1,000,000,000 lamports)
 *       400:
 *         description: Invalid public key format.
 *       500:
 *         description: Error retrieving wallet information.
 */
router.get('/mother/:publicKey', walletController.getMotherWalletInfoController);

/**
 * @swagger
 * /api/wallets/children:
 *   post:
 *     summary: Derive child wallets from a mother wallet.
 *     tags: [Wallet]
 *     requestBody:
 *       required: true
 *       content:
 *         application/json:
 *           schema:
 *             type: object
 *             required:
 *               - motherWalletPublicKey
 *             properties:
 *               motherWalletPublicKey:
 *                 type: string
 *                 description: The public key of the mother wallet.
 *                 example: "FKS2idx6M1WyBeWtMr2tY9XSFsVvKNy84rS9jq9W1qfo"
 *               count:
 *                 type: number
 *                 description: The number of child wallets to generate.
 *                 default: 3
 *               saveToFile:
 *                 type: boolean
 *                 description: Whether to save the wallets to the file system.
 *                 default: false
 *     responses:
 *       201:
 *         description: Child wallets derived successfully.
 *         content:
 *           application/json:
 *             schema:
 *               type: object
 *               properties:
 *                 message:
 *                   type: string
 *                 motherWalletPublicKey:
 *                   type: string
 *                 childWallets:
 *                   type: array
 *                   items:
 *                     type: object
 *                     properties:
 *                       publicKey:
 *                         type: string
 *                       privateKeyBase58:
 *                         type: string
 *       400:
 *         description: Invalid request parameters.
 *       500:
 *         description: Error deriving child wallets.
 */
router.post('/children', walletController.deriveChildWalletsController);

/**
 * @swagger
 * /api/wallets/fund-children:
 *   post:
 *     summary: Fund child wallets from a mother wallet.
 *     tags: [Wallet]
 *     requestBody:
 *       required: true
 *       content:
 *         application/json:
 *           schema:
 *             type: object
 *             required:
 *               - motherWalletPrivateKeyBase58
 *               - childWallets
 *             properties:
 *               motherWalletPrivateKeyBase58:
 *                 type: string
 *                 description: The private key of the mother wallet in base58 encoding.
 *                 example: "yourBase58PrivateKeyHere..."
 *               childWallets:
 *                 type: array
 *                 description: Array of child wallets to fund.
 *                 items:
 *                   type: object
 *                   required:
 *                     - publicKey
 *                     - amountSol
 *                   properties:
 *                     publicKey:
 *                       type: string
 *                       description: The public key of the child wallet.
 *                       example: "ChildWalletPublicKeyHere..."
 *                     amountSol:
 *                       type: number
 *                       description: The amount of SOL to send to the child wallet.
 *                       example: 0.002
 *     responses:
 *       200:
 *         description: Child wallets funding completed.
 *         content:
 *           application/json:
 *             schema:
 *               type: object
 *               properties:
 *                 status:
 *                   type: string
 *                   enum: [success, partial, failed]
 *                   description: Overall status of the funding operation.
 *                 results:
 *                   type: array
 *                   items:
 *                     type: object
 *                     properties:
 *                       childPublicKey:
 *                         type: string
 *                       transactionId:
 *                         type: string
 *                         nullable: true
 *                       status:
 *                         type: string
 *                         enum: [funded, failed]
 *                       error:
 *                         type: string
 *                         nullable: true
 *                       newBalanceSol:
 *                         type: number
 *                         description: New balance of the child wallet in SOL (only present if funded).
 *                 motherWalletFinalBalanceSol:
 *                   type: number
 *                   description: Final balance of the mother wallet after all funding operations.
 *                 message:
 *                   type: string
 *       400:
 *         description: Invalid request parameters or insufficient funds.
 *       500:
 *         description: Error funding child wallets.
 */
router.post('/fund-children', walletController.fundChildWalletsController);

/**
 * @swagger
 * /api/wallets/return-funds:
 *   post:
 *     summary: Return funds from a child wallet to a mother wallet.
 *     tags: [Wallet]
 *     requestBody:
 *       required: true
 *       content:
 *         application/json:
 *           schema:
 *             type: object
 *             required:
 *               - childWalletPrivateKeyBase58
 *               - motherWalletPublicKey
 *             properties:
 *               childWalletPrivateKeyBase58:
 *                 type: string
 *                 description: The private key of the child wallet in base58 encoding.
 *                 example: "yourBase58PrivateKeyHere..."
 *               motherWalletPublicKey:
 *                 type: string
 *                 description: The public key of the mother wallet.
 *                 example: "FKS2idx6M1WyBeWtMr2tY9XSFsVvKNy84rS9jq9W1qfo"
 *               returnAllFunds:
 *                 type: boolean
 *                 description: Whether to return all funds or keep some for transaction fees.
 *                 default: false
 *     responses:
 *       200:
 *         description: Funds returned to mother wallet successfully.
 *         content:
 *           application/json:
 *             schema:
 *               type: object
 *               properties:
 *                 status:
 *                   type: string
 *                   enum: [success, failed]
 *                   description: Status of the return operation.
 *                 transactionId:
 *                   type: string
 *                   description: Transaction ID of the return transaction.
 *                 amountReturnedSol:
 *                   type: number
 *                   description: Amount of SOL returned to the mother wallet.
 *                 newChildBalanceSol:
 *                   type: number
 *                   description: New balance of the child wallet in SOL.
 *                 message:
 *                   type: string
 *       400:
 *         description: Invalid request parameters or insufficient funds.
 *       500:
 *         description: Error returning funds to mother wallet.
 */
router.post('/return-funds', walletController.returnFundsController);

/**
 * @swagger
 * /api/wallets/balance/{walletPublicKey}:
 *   get:
 *     summary: Get the balance of any wallet.
 *     tags: [Wallet]
 *     parameters:
 *       - in: path
 *         name: walletPublicKey
 *         schema:
 *           type: string
 *         required: true
 *         description: The public key of the wallet.
 *     responses:
 *       200:
 *         description: Successfully retrieved wallet balance.
 *         content:
 *           application/json:
 *             schema:
 *               type: object
 *               properties:
 *                 publicKey:
 *                   type: string
 *                 balanceSol:
 *                   type: number
 *                   description: Wallet balance in SOL
 *                 balanceLamports:
 *                   type: number
 *                   description: Wallet balance in lamports (1 SOL = 1,000,000,000 lamports)
 *       400:
 *         description: Invalid public key format.
 *       500:
 *         description: Error retrieving wallet balance.
 */
router.get('/balance/:walletPublicKey', walletController.getWalletBalanceController);

module.exports = router; 