const express = require('express');
const jupiterController = require('../controllers/jupiterController');
const router = express.Router();

/**
 * @swagger
 * /api/jupiter/quote:
 *   post:
 *     summary: Get a swap quote from Jupiter
 *     description: Fetches a price quote for swapping one token to another using Jupiter Exchange
 *     tags: [Jupiter]
 *     requestBody:
 *       required: true
 *       content:
 *         application/json:
 *           schema:
 *             type: object
 *             required:
 *               - inputMint
 *               - outputMint
 *               - amount
 *             properties:
 *               inputMint:
 *                 type: string
 *                 description: Token mint address of the input token or token symbol (SOL, USDC, USDT, BONK)
 *                 example: SOL
 *               outputMint:
 *                 type: string
 *                 description: Token mint address of the output token or token symbol (SOL, USDC, USDT, BONK)
 *                 example: USDC
 *               amount:
 *                 type: number
 *                 description: Amount of input token in base units (e.g., lamports for SOL)
 *                 example: 1000000
 *               slippageBps:
 *                 type: number
 *                 description: Slippage tolerance in basis points (1 bps = 0.01%)
 *                 default: 50
 *                 example: 50
 *               onlyDirectRoutes:
 *                 type: boolean
 *                 description: Whether to only use direct swap routes
 *                 default: false
 *                 example: false
 *               asLegacyTransaction:
 *                 type: boolean
 *                 description: Whether to use legacy transactions
 *                 default: false
 *                 example: false
 *               platformFeeBps:
 *                 type: number
 *                 description: Platform fee in basis points
 *                 default: 0
 *                 example: 0
 *     responses:
 *       200:
 *         description: Jupiter quote successfully retrieved
 *         content:
 *           application/json:
 *             schema:
 *               type: object
 *               properties:
 *                 message:
 *                   type: string
 *                   example: Jupiter quote retrieved successfully
 *                 quoteResponse:
 *                   type: object
 *                   description: The Jupiter quote response with additional formatted info
 *       400:
 *         description: Invalid parameters
 *       500:
 *         description: Server error
 *       502:
 *         description: Error from Jupiter API
 */
router.post('/quote', jupiterController.getQuoteController);

/**
 * @swagger
 * /api/jupiter/swap:
 *   post:
 *     summary: Execute a swap on Jupiter with fee collection
 *     description: Executes a token swap using Jupiter Exchange and collects a 0.1% fee
 *     tags: [Jupiter]
 *     requestBody:
 *       required: true
 *       content:
 *         application/json:
 *           schema:
 *             type: object
 *             required:
 *               - userWalletPrivateKeyBase58
 *               - quoteResponse
 *             properties:
 *               userWalletPrivateKeyBase58:
 *                 type: string
 *                 description: The private key of the user's wallet in base58 encoding
 *                 example: "4wBqpZM..."
 *               quoteResponse:
 *                 type: object
 *                 description: The Jupiter quote response object from the /quote endpoint
 *               wrapAndUnwrapSol:
 *                 type: boolean
 *                 description: Whether to automatically wrap and unwrap SOL
 *                 default: true
 *                 example: true
 *               asLegacyTransaction:
 *                 type: boolean
 *                 description: Whether to use legacy transactions
 *                 default: false
 *                 example: false
 *               collectFees:
 *                 type: boolean
 *                 description: Whether to collect fees from the swap (0.1% of input amount)
 *                 default: true
 *                 example: true
 *     responses:
 *       200:
 *         description: Swap executed successfully
 *         content:
 *           application/json:
 *             schema:
 *               type: object
 *               properties:
 *                 message:
 *                   type: string
 *                   example: Swap executed successfully
 *                 status:
 *                   type: string
 *                   example: success
 *                 transactionId:
 *                   type: string
 *                   example: "4eA5mZRCCGP..."
 *                 feeCollection:
 *                   type: object
 *                   properties:
 *                     status:
 *                       type: string
 *                       enum: [success, failed, skipped]
 *                       example: success
 *                     transactionId:
 *                       type: string
 *                       example: "2Q1QwHMB7m..."
 *                     feeAmount:
 *                       type: number
 *                       example: 0.0001
 *                     feeTokenMint:
 *                       type: string
 *                       example: "So111..."
 *                 newBalanceSol:
 *                   type: number
 *                   description: New SOL balance of the user's wallet
 *                   example: 0.5123
 *       400:
 *         description: Invalid parameters or transaction failed
 *       500:
 *         description: Server error
 *       502:
 *         description: Error from Jupiter API
 */
router.post('/swap', jupiterController.executeSwapController);

/**
 * @swagger
 * /api/jupiter/tokens:
 *   get:
 *     summary: Get supported tokens
 *     description: Returns a list of tokens supported by the API for Jupiter swaps
 *     tags: [Jupiter]
 *     responses:
 *       200:
 *         description: List of supported tokens
 *         content:
 *           application/json:
 *             schema:
 *               type: object
 *               properties:
 *                 message:
 *                   type: string
 *                   example: Supported tokens retrieved successfully
 *                 tokens:
 *                   type: object
 *                   properties:
 *                     SOL:
 *                       type: string
 *                       example: So11111111111111111111111111111111111111112
 *                     USDC:
 *                       type: string
 *                       example: EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v
 *       500:
 *         description: Server error
 */
router.get('/tokens', jupiterController.getSupportedTokensController);

module.exports = router; 