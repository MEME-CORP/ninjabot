const walletService = require('../services/walletService');

/**
 * Controller to handle the creation or import of a mother wallet.
 */
async function createOrImportMotherWalletController(req, res) {
  try {
    const { privateKeyBase58 } = req.body; // Optional

    const walletData = await walletService.createOrImportMotherWalletService(privateKeyBase58);

    res.status(201).json({
      message: privateKeyBase58 ? 'Mother wallet imported successfully.' : 'Mother wallet created successfully.',
      motherWalletPublicKey: walletData.publicKey,
      motherWalletPrivateKeyBase58: walletData.privateKeyBase58, // Returned for the bot to store
    });
  } catch (error) {
    // Log the detailed error for server-side inspection
    console.error('Error in createOrImportMotherWalletController:', error.message);

    // Send a generic error message to the client
    res.status(500).json({ 
      message: 'Error processing mother wallet request.',
      error: error.message || 'An unexpected error occurred.'
    });
  }
}

/**
 * Controller to handle the retrieval of mother wallet information.
 */
async function getMotherWalletInfoController(req, res) {
  try {
    const { publicKey } = req.params;
    
    if (!publicKey) {
      return res.status(400).json({
        message: 'Missing required parameter: publicKey',
      });
    }

    const walletInfo = await walletService.getWalletInfo(publicKey);
    
    res.status(200).json({
      publicKey: walletInfo.publicKey,
      balanceSol: walletInfo.balanceSol,
      balanceLamports: walletInfo.balanceLamports,
    });
  } catch (error) {
    console.error('Error in getMotherWalletInfoController:', error.message);
    
    // Send appropriate error response
    if (error.message.includes('Invalid public key input')) {
      res.status(400).json({ 
        message: 'Invalid wallet public key format.',
        error: error.message
      });
    } else {
      res.status(500).json({ 
        message: 'Error retrieving wallet information.',
        error: error.message || 'An unexpected error occurred.'
      });
    }
  }
}

/**
 * Controller to handle the derivation of child wallets from a mother wallet.
 */
async function deriveChildWalletsController(req, res) {
  try {
    const { motherWalletPublicKey, count = 3, saveToFile = false } = req.body;
    
    if (!motherWalletPublicKey) {
      return res.status(400).json({
        message: 'Missing required parameter: motherWalletPublicKey',
      });
    }

    // Validate count is a positive integer
    const walletCount = parseInt(count, 10);
    if (isNaN(walletCount) || walletCount <= 0) {
      return res.status(400).json({
        message: 'Invalid count parameter: must be a positive integer',
      });
    }

    const result = await walletService.deriveChildWallets(motherWalletPublicKey, walletCount, saveToFile);
    
    res.status(201).json({
      message: `${result.childWallets.length} child wallets successfully derived.`,
      motherWalletPublicKey: result.motherWalletPublicKey,
      childWallets: result.childWallets.map(wallet => ({
        publicKey: wallet.publicKey,
        privateKeyBase58: wallet.privateKeyBase58,
      })),
    });
  } catch (error) {
    console.error('Error in deriveChildWalletsController:', error.message);
    
    // Send appropriate error response
    if (error.message.includes('Invalid public key input')) {
      res.status(400).json({ 
        message: 'Invalid mother wallet public key format.',
        error: error.message
      });
    } else {
      res.status(500).json({ 
        message: 'Error deriving child wallets.',
        error: error.message || 'An unexpected error occurred.'
      });
    }
  }
}

/**
 * Controller to handle funding child wallets from a mother wallet.
 */
async function fundChildWalletsController(req, res) {
  try {
    const { motherWalletPrivateKeyBase58, childWallets } = req.body;
    
    // Validate required parameters
    if (!motherWalletPrivateKeyBase58) {
      return res.status(400).json({
        message: 'Missing required parameter: motherWalletPrivateKeyBase58',
      });
    }
    
    if (!Array.isArray(childWallets) || childWallets.length === 0) {
      return res.status(400).json({
        message: 'Missing or invalid childWallets parameter: must be a non-empty array',
      });
    }
    
    // Validate each child wallet entry
    for (const wallet of childWallets) {
      if (!wallet.publicKey) {
        return res.status(400).json({
          message: 'Each child wallet must include a publicKey',
        });
      }
      
      if (typeof wallet.amountSol !== 'number' || isNaN(wallet.amountSol) || wallet.amountSol <= 0) {
        return res.status(400).json({
          message: 'Each child wallet must include a positive amountSol value',
        });
      }
    }
    
    // Call the service function to fund child wallets
    const result = await walletService.fundChildWallets(motherWalletPrivateKeyBase58, childWallets);
    
    res.status(200).json({
      status: result.status,
      results: result.results,
      motherWalletFinalBalanceSol: result.motherWalletFinalBalanceSol,
      message: `Child wallet funding completed with status: ${result.status}`,
    });
  } catch (error) {
    console.error('Error in fundChildWalletsController:', error.message);
    
    // Send appropriate error response
    if (error.message.includes('Insufficient funds')) {
      res.status(400).json({ 
        message: 'Insufficient funds in mother wallet.',
        error: error.message
      });
    } else if (error.message.includes('Invalid public key')) {
      res.status(400).json({ 
        message: 'Invalid wallet public key format.',
        error: error.message
      });
    } else {
      res.status(500).json({ 
        message: 'Error funding child wallets.',
        error: error.message || 'An unexpected error occurred.'
      });
    }
  }
}

/**
 * Controller to handle returning funds from a child wallet to a mother wallet.
 */
async function returnFundsController(req, res) {
  try {
    const { childWalletPrivateKeyBase58, motherWalletPublicKey, returnAllFunds = false } = req.body;
    
    // Validate required parameters
    if (!childWalletPrivateKeyBase58) {
      return res.status(400).json({
        message: 'Missing required parameter: childWalletPrivateKeyBase58',
      });
    }
    
    if (!motherWalletPublicKey) {
      return res.status(400).json({
        message: 'Missing required parameter: motherWalletPublicKey',
      });
    }
    
    // Parse boolean parameter
    const parsedReturnAllFunds = typeof returnAllFunds === 'string'
      ? returnAllFunds.toLowerCase() === 'true'
      : Boolean(returnAllFunds);
    
    // Call the service function to return funds
    const result = await walletService.returnFundsToMotherWallet(
      childWalletPrivateKeyBase58,
      motherWalletPublicKey,
      parsedReturnAllFunds
    );
    
    res.status(200).json({
      status: result.status,
      transactionId: result.transactionId,
      amountReturnedSol: result.amountReturnedSol,
      newChildBalanceSol: result.newChildBalanceSol,
      message: result.message,
    });
  } catch (error) {
    console.error('Error in returnFundsController:', error.message);
    
    // Send appropriate error response
    if (error.message.includes('Insufficient funds')) {
      res.status(400).json({ 
        message: 'Insufficient funds in child wallet.',
        error: error.message
      });
    } else if (error.message.includes('Invalid public key') || error.message.includes('Invalid private key')) {
      res.status(400).json({ 
        message: 'Invalid wallet key format.',
        error: error.message
      });
    } else if (error.message.includes('Transaction failed')) {
      res.status(400).json({ 
        message: 'Transaction failed.',
        error: error.message
      });
    } else {
      res.status(500).json({ 
        message: 'Error returning funds to mother wallet.',
        error: error.message || 'An unexpected error occurred.'
      });
    }
  }
}

/**
 * Controller to handle getting the balance of any wallet.
 */
async function getWalletBalanceController(req, res) {
  try {
    const { walletPublicKey } = req.params;
    
    if (!walletPublicKey) {
      return res.status(400).json({
        message: 'Missing required parameter: walletPublicKey',
      });
    }

    const walletInfo = await walletService.getWalletInfo(walletPublicKey);
    
    res.status(200).json({
      publicKey: walletInfo.publicKey,
      balanceSol: walletInfo.balanceSol,
      balanceLamports: walletInfo.balanceLamports,
    });
  } catch (error) {
    console.error('Error in getWalletBalanceController:', error.message);
    
    // Send appropriate error response
    if (error.message.includes('Invalid public key input')) {
      res.status(400).json({ 
        message: 'Invalid wallet public key format.',
        error: error.message
      });
    } else {
      res.status(500).json({ 
        message: 'Error retrieving wallet balance.',
        error: error.message || 'An unexpected error occurred.'
      });
    }
  }
}

module.exports = {
  createOrImportMotherWalletController,
  getMotherWalletInfoController,
  deriveChildWalletsController,
  fundChildWalletsController,
  returnFundsController,
  getWalletBalanceController,
}; 