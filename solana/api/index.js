const express = require('express');
const walletRoutes = require('./routes/walletRoutes');
const jupiterRoutes = require('./routes/jupiterRoutes');

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware to parse JSON bodies
app.use(express.json());

// API Routes
app.use('/api/wallets', walletRoutes);
app.use('/api/jupiter', jupiterRoutes);

// Simple root endpoint
app.get('/', (req, res) => {
  res.send('Solana API is running.');
});

// Global error handler (optional basic version)
app.use((err, req, res, next) => {
  console.error('Global error handler caught:', err.stack);
  res.status(500).send('Something broke!');
});

// Start the server
app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
  console.log(`API documentation available at http://localhost:${PORT}/api-docs`);
  console.log(`Wallet母 K API endpoint: POST http://localhost:${PORT}/api/wallets/mother`);
  console.log(`Jupiter Quote API endpoint: POST http://localhost:${PORT}/api/jupiter/quote`);
});

module.exports = app; // For potential testing purposes 