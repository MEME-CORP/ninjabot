# Test script for Jupiter Swap API
# This script demonstrates how to use the Jupiter Swap API endpoint
# WARNING: This script can execute REAL transactions on Solana mainnet if run with the -ExecuteSwap flag

param (
    [switch]$ExecuteSwap = $false
)

# Configuration
$BaseUrl = "http://localhost:3000"
$QuoteEndpoint = "$BaseUrl/api/jupiter/quote"
$SwapEndpoint = "$BaseUrl/api/jupiter/swap"

# Colors for output
$InfoColor = "Cyan"
$SuccessColor = "Green"
$WarningColor = "Yellow"
$ErrorColor = "Red"

# Function to test the full swap flow
function Test-JupiterSwap {
    Write-Host "===== JUPITER SWAP API TEST =====" -ForegroundColor $InfoColor
    
    if ($ExecuteSwap) {
        Write-Host "WARNING: This script will execute REAL transactions on Solana!" -ForegroundColor $ErrorColor
        Write-Host "Press Ctrl+C now to abort if you don't want to proceed." -ForegroundColor $ErrorColor
        Start-Sleep -Seconds 5
    } else {
        Write-Host "Running in simulation mode. No real transactions will be executed." -ForegroundColor $WarningColor
        Write-Host "To execute real transactions, run with -ExecuteSwap flag." -ForegroundColor $WarningColor
    }
    
    # Step 1: Get a quote
    try {
        $quote = Get-JupiterQuote
        if (-not $quote) {
            Write-Host "Failed to get quote. Aborting test." -ForegroundColor $ErrorColor
            return
        }
        
        # Step 2: Execute the swap (or simulate)
        if ($ExecuteSwap) {
            Execute-JupiterSwap -Quote $quote
        } else {
            Simulate-JupiterSwap -Quote $quote
        }
    }
    catch {
        Write-Host "Error in Jupiter Swap test: $_" -ForegroundColor $ErrorColor
    }
    
    Write-Host "===== JUPITER SWAP API TEST COMPLETED =====" -ForegroundColor $InfoColor
}

# Function to get a quote from Jupiter
function Get-JupiterQuote {
    Write-Host "`n[TEST] Getting quote for SOL to USDC..." -ForegroundColor $WarningColor
    
    $quoteRequest = @{
        inputMint = "SOL"
        outputMint = "USDC"
        amount = 1000000  # 0.001 SOL in lamports
        slippageBps = 100  # 1% slippage
    } | ConvertTo-Json
    
    try {
        $response = Invoke-RestMethod -Uri $QuoteEndpoint -Method POST -Body $quoteRequest -ContentType "application/json" -ErrorVariable RestError -ErrorAction SilentlyContinue
        
        if ($RestError) {
            Write-Host "Error getting quote: $($RestError.Message)" -ForegroundColor $ErrorColor
            return $null
        }
        
        Write-Host "Successfully retrieved SOL->USDC quote:" -ForegroundColor $SuccessColor
        Write-Host "  Input: $($response.quoteResponse._formattedInfo.inputToken) ($($response.quoteResponse._formattedInfo.inputAmount))"
        Write-Host "  Output: $($response.quoteResponse._formattedInfo.outputToken) ($($response.quoteResponse._formattedInfo.outputAmount))"
        Write-Host "  Price Impact: $($response.quoteResponse._formattedInfo.priceImpactPct)%"
        Write-Host "  Route Steps: $($response.quoteResponse._formattedInfo.routeSteps)"
        
        return $response.quoteResponse
    }
    catch {
        Write-Host "Error processing quote request: $_" -ForegroundColor $ErrorColor
        return $null
    }
}

# Function to execute a swap on Jupiter
function Execute-JupiterSwap {
    param (
        [Parameter(Mandatory = $true)]
        [object]$Quote
    )
    
    Write-Host "`n[TEST] Executing swap..." -ForegroundColor $WarningColor
    
    # Here you would need to provide a valid private key to execute the swap
    # For security reasons, we'll prompt for it rather than hardcoding it
    $privateKey = Read-Host -Prompt "Enter wallet private key (base58 encoded)" -AsSecureString
    $privateKeyPlain = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto([System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($privateKey))
    
    $swapRequest = @{
        userWalletPrivateKeyBase58 = $privateKeyPlain
        quoteResponse = $Quote
        wrapAndUnwrapSol = $true
        collectFees = $true
    } | ConvertTo-Json -Depth 10
    
    try {
        Write-Host "Sending swap request to API..." -ForegroundColor $InfoColor
        $response = Invoke-RestMethod -Uri $SwapEndpoint -Method POST -Body $swapRequest -ContentType "application/json" -ErrorVariable RestError -ErrorAction SilentlyContinue
        
        if ($RestError) {
            Write-Host "Error executing swap: $($RestError.Message)" -ForegroundColor $ErrorColor
            return
        }
        
        Write-Host "Swap executed successfully!" -ForegroundColor $SuccessColor
        Write-Host "  Transaction ID: $($response.transactionId)"
        Write-Host "  Transaction Explorer: https://solscan.io/tx/$($response.transactionId)"
        Write-Host "  New Balance: $($response.newBalanceSol) SOL"
        
        # Display fee collection details
        if ($response.feeCollection) {
            Write-Host "`nFee Collection:" -ForegroundColor $InfoColor
            Write-Host "  Status: $($response.feeCollection.status)"
            if ($response.feeCollection.status -eq "success") {
                Write-Host "  Transaction ID: $($response.feeCollection.transactionId)"
                Write-Host "  Fee Amount: $($response.feeCollection.feeAmount) $($response.feeCollection.feeTokenMint)"
            } elseif ($response.feeCollection.status -eq "skipped") {
                Write-Host "  Reason: $($response.feeCollection.message)"
            } else {
                Write-Host "  Error: $($response.feeCollection.error)" -ForegroundColor $ErrorColor
            }
        }
    }
    catch {
        Write-Host "Error processing swap request: $_" -ForegroundColor $ErrorColor
    }
    finally {
        # Clear the private key from memory
        $privateKeyPlain = $null
    }
}

# Function to simulate a swap without executing it
function Simulate-JupiterSwap {
    param (
        [Parameter(Mandatory = $true)]
        [object]$Quote
    )
    
    Write-Host "`n[TEST] Simulating swap (no transaction will be executed)..." -ForegroundColor $WarningColor
    
    # Mock private key (this is not a real private key)
    $mockPrivateKey = "4wBqpZMHW5mZ9MK18URDRyJMsnqaYAcz5PVkApMEWoApyZRUNVzdCCKnExGKbcnxZRKJPQhMAcadZYe1wXYm1Gkt"
    
    $swapRequest = @{
        userWalletPrivateKeyBase58 = $mockPrivateKey
        quoteResponse = $Quote
        wrapAndUnwrapSol = $true
        collectFees = $true
    } | ConvertTo-Json -Depth 10
    
    Write-Host "`nSwap Request Sample (with mock private key):" -ForegroundColor $InfoColor
    Write-Host "POST $SwapEndpoint" -ForegroundColor $InfoColor
    Write-Host "Content-Type: application/json" -ForegroundColor $InfoColor
    Write-Host (ConvertTo-Json @{
        userWalletPrivateKeyBase58 = "YOUR_PRIVATE_KEY_HERE" # Placeholder
        quoteResponse = @{
            inputMint = $Quote.inputMint
            outputMint = $Quote.outputMint
            inAmount = $Quote.inAmount
            outAmount = $Quote.outAmount
            # ... other quote fields would be included
        }
        wrapAndUnwrapSol = $true
        collectFees = $true
    } -Depth 3)
    
    Write-Host "`nExpected Response:" -ForegroundColor $InfoColor
    Write-Host (ConvertTo-Json @{
        message = "Swap executed successfully"
        status = "success"
        transactionId = "4eA5mZRCCGP9NW9z3UXg2RR54qZNqPE7HV5CynvihMUJ"
        feeCollection = @{
            status = "success"
            transactionId = "2Q1QwHMB7mKKEMrCEmGENTJJrSJYpmg1TQKSqJPysQSP"
            feeAmount = 0.0001
            feeTokenMint = "So11111111111111111111111111111111111111112"
        }
        newBalanceSol = 0.5123
    } -Depth 3)
    
    Write-Host "`nTo execute a real swap, run this script with the -ExecuteSwap flag." -ForegroundColor $WarningColor
}

# Execute the test
Test-JupiterSwap 