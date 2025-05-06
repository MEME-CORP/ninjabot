# Test script for Jupiter API routes
# This script tests the Jupiter Quote API functionality

# Configuration
$BaseUrl = "http://localhost:3000"
$JupiterQuoteEndpoint = "$BaseUrl/api/jupiter/quote"
$JupiterTokensEndpoint = "$BaseUrl/api/jupiter/tokens"

function Invoke-Tests {
    Write-Host "===== JUPITER API TESTING =====" -ForegroundColor Cyan
    
    # Test 1: Get supported tokens
    Try-GetSupportedTokens
    
    # Test 2: Get a quote for SOL to USDC
    Try-GetQuoteSolToUsdc
    
    # Test 3: Get a quote with custom parameters
    Try-GetQuoteWithCustomParams
    
    # Test 4: Test validation errors
    Try-ValidationErrors
    
    Write-Host "===== JUPITER API TESTING COMPLETED =====" -ForegroundColor Cyan
}

function Try-GetSupportedTokens {
    Write-Host "`n[TEST] Getting supported tokens..." -ForegroundColor Yellow
    
    $response = Invoke-RestMethod -Uri $JupiterTokensEndpoint -Method GET -ContentType "application/json" -ErrorVariable RestError -ErrorAction SilentlyContinue
    
    if ($RestError) {
        Write-Host "Error getting supported tokens: $($RestError.Message)" -ForegroundColor Red
        return
    }
    
    Write-Host "Successfully retrieved supported tokens:" -ForegroundColor Green
    $response.tokens | ConvertTo-Json -Depth 3
}

function Try-GetQuoteSolToUsdc {
    Write-Host "`n[TEST] Getting quote for SOL to USDC..." -ForegroundColor Yellow
    
    $body = @{
        inputMint = "SOL"
        outputMint = "USDC"
        amount = 1000000  # 0.001 SOL in lamports
    } | ConvertTo-Json
    
    try {
        $response = Invoke-RestMethod -Uri $JupiterQuoteEndpoint -Method POST -Body $body -ContentType "application/json" -ErrorVariable RestError -ErrorAction SilentlyContinue
        
        if ($RestError) {
            Write-Host "Error getting quote: $($RestError.Message)" -ForegroundColor Red
            return
        }
        
        Write-Host "Successfully retrieved SOL->USDC quote:" -ForegroundColor Green
        Write-Host "  Input: $($response.quoteResponse._formattedInfo.inputToken) ($($response.quoteResponse._formattedInfo.inputAmount))"
        Write-Host "  Output: $($response.quoteResponse._formattedInfo.outputToken) ($($response.quoteResponse._formattedInfo.outputAmount))"
        Write-Host "  Price Impact: $($response.quoteResponse._formattedInfo.priceImpactPct)%"
        Write-Host "  Route Steps: $($response.quoteResponse._formattedInfo.routeSteps)"
    }
    catch {
        Write-Host "Error processing request: $_" -ForegroundColor Red
    }
}

function Try-GetQuoteWithCustomParams {
    Write-Host "`n[TEST] Getting quote with custom parameters..." -ForegroundColor Yellow
    
    $body = @{
        inputMint = "USDC"
        outputMint = "SOL"
        amount = 1000000  # 1 USDC (6 decimals)
        slippageBps = 100
        onlyDirectRoutes = $true
    } | ConvertTo-Json
    
    try {
        $response = Invoke-RestMethod -Uri $JupiterQuoteEndpoint -Method POST -Body $body -ContentType "application/json" -ErrorVariable RestError -ErrorAction SilentlyContinue
        
        if ($RestError) {
            Write-Host "Error getting quote with custom params: $($RestError.Message)" -ForegroundColor Red
            return
        }
        
        Write-Host "Successfully retrieved USDC->SOL quote with custom params:" -ForegroundColor Green
        Write-Host "  Input: $($response.quoteResponse._formattedInfo.inputToken) ($($response.quoteResponse._formattedInfo.inputAmount))"
        Write-Host "  Output: $($response.quoteResponse._formattedInfo.outputToken) ($($response.quoteResponse._formattedInfo.outputAmount))"
        Write-Host "  Price Impact: $($response.quoteResponse._formattedInfo.priceImpactPct)%"
        Write-Host "  Route Steps: $($response.quoteResponse._formattedInfo.routeSteps)"
        Write-Host "  Only Direct Routes: True"
        Write-Host "  Slippage: 1.00%"
    }
    catch {
        Write-Host "Error processing request: $_" -ForegroundColor Red
    }
}

function Try-ValidationErrors {
    Write-Host "`n[TEST] Testing validation errors..." -ForegroundColor Yellow
    
    # Test missing inputMint
    $body = @{
        outputMint = "USDC"
        amount = 1000000
    } | ConvertTo-Json
    
    try {
        $response = Invoke-RestMethod -Uri $JupiterQuoteEndpoint -Method POST -Body $body -ContentType "application/json" -ErrorVariable RestError -ErrorAction SilentlyContinue
        
        if ($RestError) {
            Write-Host "Validation test passed: Missing inputMint error detected" -ForegroundColor Green
        }
        else {
            Write-Host "Validation test failed: Missing inputMint did not trigger error" -ForegroundColor Red
        }
    }
    catch {
        Write-Host "Missing inputMint error: $($_.Exception.Message)" -ForegroundColor Yellow
    }
    
    # Test invalid amount
    $body = @{
        inputMint = "SOL"
        outputMint = "USDC"
        amount = -100
    } | ConvertTo-Json
    
    try {
        $response = Invoke-RestMethod -Uri $JupiterQuoteEndpoint -Method POST -Body $body -ContentType "application/json" -ErrorVariable RestError -ErrorAction SilentlyContinue
        
        if ($RestError) {
            Write-Host "Validation test passed: Invalid amount error detected" -ForegroundColor Green
        }
        else {
            Write-Host "Validation test failed: Invalid amount did not trigger error" -ForegroundColor Red
        }
    }
    catch {
        Write-Host "Invalid amount error: $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

# Run the tests
Invoke-Tests 