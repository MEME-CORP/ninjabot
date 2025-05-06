# Deployment Guide for Solana Trading Bot API

This guide provides detailed instructions for deploying the Solana Trading Bot API to various cloud platforms.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Deployment Options](#deployment-options)
  - [Render](#render)
  - [Digital Ocean](#digital-ocean)
  - [AWS](#aws)
  - [Self-hosted](#self-hosted)
- [Environment Variables](#environment-variables)
- [Security Considerations](#security-considerations)
- [Monitoring and Maintenance](#monitoring-and-maintenance)

## Prerequisites

Before deploying the API, ensure you have:

1. A complete and tested API implementation
2. A Git repository containing your code
3. A Solana RPC endpoint (preferably a paid service for production)
4. Node.js 16+ and npm 7+ installed on your local machine

## Deployment Options

### Render

[Render](https://render.com/) is recommended for its simplicity and ease of use.

#### Steps:

1. **Push your code to a Git repository** (GitHub, GitLab, etc.)

2. **Sign up for Render** at [render.com](https://render.com/)

3. **Create a new Web Service**:
   - Click "New" and select "Web Service"
   - Connect your Git repository
   - Configure the service:
     - **Name**: `solana-trading-bot-api`
     - **Environment**: `Node`
     - **Build Command**: `cd solana && npm install`
     - **Start Command**: `cd solana && node api/index.js`
     - **Plan**: Select according to your needs (Free tier works for testing)

4. **Set Environment Variables** in the Render dashboard:
   - `PORT`: `10000` (Render will provide the PORT)
   - `NODE_ENV`: `production`
   - `SOLANA_NETWORK`: `mainnet-beta` (or `devnet` for testing)
   - `SOLANA_RPC_URL`: Your Solana RPC endpoint
   - `FEE_COLLECTOR_PUBKEY`: Your fee collector wallet address
   - `DEFAULT_FEE_BPS`: `10` (0.1%)
   - `CORS_ORIGIN`: Your frontend domain or `*` (not recommended for production)
   - `LOG_LEVEL`: `info`

5. **Deploy**:
   - Render will automatically deploy your API when you push changes to your repository

#### Using render.yaml:

Alternatively, you can use the `render.yaml` file provided in the repository:

1. Ensure the `render.yaml` file is in the root of your repository
2. In the Render dashboard, click "New" and select "Blueprint"
3. Connect your Git repository
4. Render will automatically detect the `render.yaml` file and create the necessary services

### Digital Ocean

Digital Ocean's App Platform provides similar ease of use to Render with more advanced options.

#### Steps:

1. **Sign up for Digital Ocean** at [digitalocean.com](https://www.digitalocean.com/)

2. **Create a new App**:
   - Go to the App Platform section
   - Click "Create App"
   - Connect your Git repository
   - Configure the app:
     - **Environment**: `Node.js`
     - **Build Command**: `cd solana && npm install`
     - **Run Command**: `cd solana && node api/index.js`
     - **HTTP Port**: `3000`

3. **Set Environment Variables** in the Digital Ocean dashboard (similar to Render)

4. **Deploy**:
   - Digital Ocean will automatically deploy your API when you push changes to your repository

### AWS

For more advanced deployment scenarios, AWS provides numerous options:

#### Option 1: AWS Elastic Beanstalk

1. **Install the EB CLI**:
   ```bash
   pip install awsebcli
   ```

2. **Initialize your EB environment**:
   ```bash
   cd solana
   eb init
   ```

3. **Create a Procfile** in the `solana` directory:
   ```
   web: node api/index.js
   ```

4. **Create a `.ebextensions/nodecommand.config`** file:
   ```yaml
   option_settings:
     aws:elasticbeanstalk:container:nodejs:
       NodeCommand: "node api/index.js"
   ```

5. **Deploy**:
   ```bash
   eb create
   ```

6. **Set Environment Variables**:
   ```bash
   eb setenv NODE_ENV=production SOLANA_NETWORK=mainnet-beta SOLANA_RPC_URL=your-rpc-url ...
   ```

#### Option 2: AWS Lambda with API Gateway

For serverless deployment, consider using AWS Lambda with API Gateway:

1. **Install the Serverless Framework**:
   ```bash
   npm install -g serverless
   ```

2. **Create a `serverless.yml`** file in the `solana` directory:
   ```yaml
   service: solana-trading-bot-api

   provider:
     name: aws
     runtime: nodejs16.x
     environment:
       NODE_ENV: production
       SOLANA_NETWORK: mainnet-beta
       SOLANA_RPC_URL: ${param:rpcUrl}
       # Add other environment variables...

   functions:
     api:
       handler: api/lambda.handler
       events:
         - http:
             path: /{proxy+}
             method: any
             cors: true
   ```

3. **Create a `api/lambda.js`** file as a wrapper for your Express app:
   ```javascript
   const serverless = require('serverless-http');
   const app = require('./index');

   module.exports.handler = serverless(app);
   ```

4. **Install the Serverless HTTP adapter**:
   ```bash
   npm install --save serverless-http
   ```

5. **Deploy**:
   ```bash
   serverless deploy --param="rpcUrl=your-rpc-url"
   ```

### Self-hosted

If you prefer to self-host the API on a VPS or dedicated server:

1. **Provision a server** with Ubuntu 20.04 or later

2. **Install Node.js and npm**:
   ```bash
   curl -fsSL https://deb.nodesource.com/setup_16.x | sudo -E bash -
   sudo apt-get install -y nodejs
   ```

3. **Clone your repository**:
   ```bash
   git clone your-repo-url
   cd your-repo-directory/solana
   ```

4. **Install dependencies**:
   ```bash
   npm install
   ```

5. **Set up environment variables**:
   ```bash
   cp .env.example .env
   nano .env  # Edit with your values
   ```

6. **Install PM2 for process management**:
   ```bash
   npm install -g pm2
   ```

7. **Start the API with PM2**:
   ```bash
   pm2 start api/index.js --name "solana-api"
   ```

8. **Set up PM2 to start on boot**:
   ```bash
   pm2 startup
   pm2 save
   ```

9. **Set up Nginx as a reverse proxy** (optional but recommended):
   ```bash
   sudo apt-get install -y nginx
   sudo nano /etc/nginx/sites-available/solana-api
   ```

   Add the following to the Nginx config:
   ```nginx
   server {
       listen 80;
       server_name your-domain.com;

       location / {
           proxy_pass http://localhost:3000;
           proxy_http_version 1.1;
           proxy_set_header Upgrade $http_upgrade;
           proxy_set_header Connection 'upgrade';
           proxy_set_header Host $host;
           proxy_cache_bypass $http_upgrade;
       }
   }
   ```

   Enable the site:
   ```bash
   sudo ln -s /etc/nginx/sites-available/solana-api /etc/nginx/sites-enabled/
   sudo nginx -t
   sudo systemctl restart nginx
   ```

10. **Set up SSL with Let's Encrypt** (highly recommended):
    ```bash
    sudo apt-get install -y certbot python3-certbot-nginx
    sudo certbot --nginx -d your-domain.com
    ```

## Environment Variables

For all deployment options, ensure you set the following environment variables:

| Variable | Description | Example |
|----------|-------------|---------|
| `PORT` | Port for the API server | `3000` |
| `NODE_ENV` | Environment mode | `production` |
| `SOLANA_NETWORK` | Solana network to use | `mainnet-beta` |
| `SOLANA_RPC_URL` | Solana RPC endpoint | `https://api.mainnet-beta.solana.com` |
| `FEE_COLLECTOR_PUBKEY` | Public key of the fee collector wallet | `FKS2idx6M1WyBeWtMr2tY9XSFsVvKNy84rS9jq9W1qfo` |
| `DEFAULT_FEE_BPS` | Default fee in basis points | `10` (0.1%) |
| `CORS_ORIGIN` | CORS origin for API requests | `https://your-frontend.com` |
| `LOG_LEVEL` | Logging level | `info` |

## Security Considerations

1. **Never commit sensitive information** to your repository:
   - Private keys
   - RPC URLs with API keys
   - Other credentials

2. **Use HTTPS** for all API communication

3. **Implement proper authentication** for production deployments:
   - Consider using API keys
   - JWT tokens
   - OAuth2

4. **Rate limiting** to prevent abuse:
   - Most cloud platforms provide this feature
   - For self-hosted, consider using Nginx rate limiting or Express middleware

5. **Regularly update dependencies**:
   ```bash
   npm audit
   npm update
   ```

## Monitoring and Maintenance

1. **Set up monitoring**:
   - Cloud platforms typically provide basic monitoring
   - Consider services like [Sentry](https://sentry.io/) for error tracking
   - [DataDog](https://www.datadoghq.com/) or [New Relic](https://newrelic.com/) for performance monitoring

2. **Logging**:
   - Ensure all critical operations are logged
   - Use a log aggregation service for production

3. **Regular backups**:
   - If your API stores critical data, implement regular backups

4. **Update strategy**:
   - Plan for how to deploy updates with minimal downtime
   - Consider using a Blue/Green deployment strategy

5. **Documentation**:
   - Keep your API documentation up-to-date
   - Document any changes to the deployment process 