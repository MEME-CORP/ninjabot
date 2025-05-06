const jupiterService = require('../services/jupiterService');

/**
 * Controller to handle getting a swap quote from Jupiter.
 */
async function getQuoteController(req, res) {
  try {
    const { 
      inputMint, 
      outputMint, 
      amount, 
      slippageBps = 50,
      onlyDirectRoutes = false,
      asLegacyTransaction = false,
      platformFeeBps = 0
    } = req.body;

    // Validate required parameters
    if (!inputMint) {
      return res.status(400).json({
        message: 'Missing required parameter: inputMint',
      });
    }

    if (!outputMint) {
      return res.status(400).json({
        message: 'Missing required parameter: outputMint',
      });
    }

    if (!amount) {
      return res.status(400).json({
        message: 'Missing required parameter: amount',
      });
    }

    // Convert string booleans to actual booleans if needed
    const parsedOnlyDirectRoutes = typeof onlyDirectRoutes === 'string' 
      ? onlyDirectRoutes.toLowerCase() === 'true' 
      : Boolean(onlyDirectRoutes);
    
    const parsedAsLegacyTransaction = typeof asLegacyTransaction === 'string'
      ? asLegacyTransaction.toLowerCase() === 'true'
      : Boolean(asLegacyTransaction);

    // Parse numeric values
    const parsedAmount = parseInt(amount, 10);
    if (isNaN(parsedAmount) || parsedAmount <= 0) {
      return res.status(400).json({
        message: 'Invalid amount parameter: must be a positive number',
      });
    }

    const parsedSlippageBps = parseInt(slippageBps, 10);
    if (isNaN(parsedSlippageBps) || parsedSlippageBps < 0) {
      return res.status(400).json({
        message: 'Invalid slippageBps parameter: must be a non-negative number',
      });
    }

    const parsedPlatformFeeBps = parseInt(platformFeeBps, 10);
    if (isNaN(parsedPlatformFeeBps) || parsedPlatformFeeBps < 0) {
      return res.status(400).json({
        message: 'Invalid platformFeeBps parameter: must be a non-negative number',
      });
    }

    // Call the service function to get a quote
    const quoteResponse = await jupiterService.getQuoteService(
      inputMint,
      outputMint,
      parsedAmount,
      parsedSlippageBps,
      parsedOnlyDirectRoutes,
      parsedAsLegacyTransaction,
      parsedPlatformFeeBps
    );

    res.status(200).json({
      message: 'Jupiter quote retrieved successfully',
      quoteResponse: quoteResponse
    });
  } catch (error) {
    console.error('Error in getQuoteController:', error.message);
    
    // Send appropriate error response
    if (error.message.includes('HTTP error')) {
      res.status(502).json({ 
        message: 'Error retrieving quote from Jupiter API.',
        error: error.message
      });
    } else {
      res.status(500).json({ 
        message: 'Error processing Jupiter quote request.',
        error: error.message || 'An unexpected error occurred.'
      });
    }
  }
}

/**
 * Controller to execute a swap on Jupiter.
 */
async function executeSwapController(req, res) {
  try {
    const { 
      userWalletPrivateKeyBase58, 
      quoteResponse,
      wrapAndUnwrapSol = true,
      asLegacyTransaction = false,
      collectFees = true
    } = req.body;

    // Validate required parameters
    if (!userWalletPrivateKeyBase58) {
      return res.status(400).json({
        message: 'Missing required parameter: userWalletPrivateKeyBase58',
      });
    }

    if (!quoteResponse) {
      return res.status(400).json({
        message: 'Missing required parameter: quoteResponse',
      });
    }

    // Validate quote response structure
    if (!quoteResponse.inputMint || !quoteResponse.outputMint || !quoteResponse.inAmount || !quoteResponse.outAmount) {
      return res.status(400).json({
        message: 'Invalid quoteResponse: missing required fields',
      });
    }

    // Convert string booleans to actual booleans if needed
    const parsedWrapAndUnwrapSol = typeof wrapAndUnwrapSol === 'string' 
      ? wrapAndUnwrapSol.toLowerCase() === 'true' 
      : Boolean(wrapAndUnwrapSol);
    
    const parsedAsLegacyTransaction = typeof asLegacyTransaction === 'string'
      ? asLegacyTransaction.toLowerCase() === 'true'
      : Boolean(asLegacyTransaction);

    const parsedCollectFees = typeof collectFees === 'string'
      ? collectFees.toLowerCase() === 'true'
      : Boolean(collectFees);

    // Call the service function to execute the swap
    const swapResult = await jupiterService.executeSwapService(
      userWalletPrivateKeyBase58,
      quoteResponse,
      parsedWrapAndUnwrapSol,
      parsedAsLegacyTransaction,
      parsedCollectFees
    );

    res.status(200).json({
      message: 'Swap executed successfully',
      ...swapResult
    });
  } catch (error) {
    console.error('Error in executeSwapController:', error.message);
    
    // Send appropriate error response
    if (error.message.includes('HTTP error')) {
      res.status(502).json({ 
        message: 'Error communicating with Jupiter API.',
        error: error.message
      });
    } else if (error.message.includes('transaction failed')) {
      res.status(400).json({ 
        message: 'Swap transaction failed.',
        error: error.message
      });
    } else if (error.message.includes('Invalid public key') || error.message.includes('Invalid private key')) {
      res.status(400).json({ 
        message: 'Invalid wallet key provided.',
        error: error.message
      });
    } else {
      res.status(500).json({ 
        message: 'Error executing Jupiter swap.',
        error: error.message || 'An unexpected error occurred.'
      });
    }
  }
}

/**
 * Controller to get information about supported tokens.
 */
function getSupportedTokensController(req, res) {
  try {
    const tokens = jupiterService.getSupportedTokens();
    
    res.status(200).json({
      message: 'Supported tokens retrieved successfully',
      tokens: tokens
    });
  } catch (error) {
    console.error('Error in getSupportedTokensController:', error.message);
    
    res.status(500).json({ 
      message: 'Error retrieving supported tokens.',
      error: error.message || 'An unexpected error occurred.'
    });
  }
}

module.exports = {
  getQuoteController,
  executeSwapController,
  getSupportedTokensController
}; 