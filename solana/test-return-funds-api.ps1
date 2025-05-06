# Test script for Return Funds API
# This script demonstrates how to use the Return Funds API to send funds from child wallets back to mother wallet
# WARNING: This script can execute REAL transactions on Solana mainnet if run with the -ExecuteTransaction flag

param (
    [switch]$ExecuteTransaction = $false
)

# Configuration
$BaseUrl = "http://localhost:3000"
$ReturnFundsEndpoint = "$BaseUrl/api/wallets/return-funds"

# Colors for output
$InfoColor = "Cyan"
$SuccessColor = "Green"
$WarningColor = "Yellow"
$ErrorColor = "Red"

# Function to test the funds return functionality
function Test-ReturnFunds {
    Write-Host "===== RETURN FUNDS API TEST =====" -ForegroundColor $InfoColor
    
    if ($ExecuteTransaction) {
        Write-Host "WARNING: This script will execute REAL transactions on Solana!" -ForegroundColor $ErrorColor
        Write-Host "Press Ctrl+C now to abort if you don't want to proceed." -ForegroundColor $ErrorColor
        Start-Sleep -Seconds 5
        
        # Execute the real transaction
        Execute-ReturnFunds
    } else {
        Write-Host "Running in simulation mode. No real transactions will be executed." -ForegroundColor $WarningColor
        Write-Host "To execute real transactions, run with -ExecuteTransaction flag." -ForegroundColor $WarningColor
        
        # Simulate the transaction
        Simulate-ReturnFunds
    }
    
    Write-Host "===== RETURN FUNDS API TEST COMPLETED =====" -ForegroundColor $InfoColor
}

# Function to execute a return funds transaction
function Execute-ReturnFunds {
    Write-Host "`n[TEST] Executing return funds transaction..." -ForegroundColor $WarningColor
    
    # Here you would need to provide a valid private key and mother wallet public key
    # For security reasons, we'll prompt for them rather than hardcoding
    $childPrivateKey = Read-Host -Prompt "Enter child wallet private key (base58 encoded)" -AsSecureString
    $childPrivateKeyPlain = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto([System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($childPrivateKey))
    
    $motherPublicKey = Read-Host -Prompt "Enter mother wallet public key"
    
    $returnFundsRequest = @{
        childWalletPrivateKeyBase58 = $childPrivateKeyPlain
        motherWalletPublicKey = $motherPublicKey
        returnAllFunds = $true
    } | ConvertTo-Json
    
    try {
        Write-Host "Sending return funds request to API..." -ForegroundColor $InfoColor
        $response = Invoke-RestMethod -Uri $ReturnFundsEndpoint -Method POST -Body $returnFundsRequest -ContentType "application/json" -ErrorVariable RestError -ErrorAction SilentlyContinue
        
        if ($RestError) {
            Write-Host "Error executing return funds: $($RestError.Message)" -ForegroundColor $ErrorColor
            return
        }
        
        Write-Host "Funds returned successfully!" -ForegroundColor $SuccessColor
        Write-Host "  Transaction ID: $($response.transactionId)"
        Write-Host "  Transaction Explorer: https://solscan.io/tx/$($response.transactionId)"
        Write-Host "  Amount Returned: $($response.amountReturnedSol) SOL"
        Write-Host "  New Child Wallet Balance: $($response.newChildBalanceSol) SOL"
        Write-Host "  Status: $($response.status)"
        Write-Host "  Message: $($response.message)"
    }
    catch {
        Write-Host "Error processing return funds request: $_" -ForegroundColor $ErrorColor
    }
    finally {
        # Clear the private key from memory
        $childPrivateKeyPlain = $null
    }
}

# Function to simulate a return funds transaction without executing it
function Simulate-ReturnFunds {
    Write-Host "`n[TEST] Simulating return funds (no transaction will be executed)..." -ForegroundColor $WarningColor
    
    # Mock private key and mother wallet (these are not real keys)
    $mockChildPrivateKey = "4wBqpZMHW5mZ9MK18URDRyJMsnqaYAcz5PVkApMEWoApyZRUNVzdCCKnExGKbcnxZRKJPQhMAcadZYe1wXYm1Gkt"
    $mockMotherPublicKey = "FKS2idx6M1WyBeWtMr2tY9XSFsVvKNy84rS9jq9W1qfo"
    
    $returnFundsRequest = @{
        childWalletPrivateKeyBase58 = $mockChildPrivateKey
        motherWalletPublicKey = $mockMotherPublicKey
        returnAllFunds = $true
    } | ConvertTo-Json
    
    Write-Host "`nReturn Funds Request Sample (with mock private key):" -ForegroundColor $InfoColor
    Write-Host "POST $ReturnFundsEndpoint" -ForegroundColor $InfoColor
    Write-Host "Content-Type: application/json" -ForegroundColor $InfoColor
    Write-Host (ConvertTo-Json @{
        childWalletPrivateKeyBase58 = "YOUR_CHILD_WALLET_PRIVATE_KEY" # Placeholder
        motherWalletPublicKey = $mockMotherPublicKey
        returnAllFunds = $true
    })
    
    Write-Host "`nExpected Response:" -ForegroundColor $InfoColor
    Write-Host (ConvertTo-Json @{
        status = "success"
        transactionId = "2Q1QwHMB7mKKEMrCEmGENTJJrSJYpmg1TQKSqJPysQSP"
        amountReturnedSol = 0.0098
        newChildBalanceSol = 0.000005
        message = "Funds returned to mother wallet successfully"
    })
    
    Write-Host "`nTo execute a real return funds transaction, run this script with the -ExecuteTransaction flag." -ForegroundColor $WarningColor
}

# Execute the test
Test-ReturnFunds 