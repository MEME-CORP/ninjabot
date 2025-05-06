# PowerShell script to test the wallet API endpoints

Write-Host "Testing wallet API endpoints..." -ForegroundColor Cyan

# Test creating a new mother wallet
Write-Host "`nCreating a new mother wallet..." -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Method POST -Uri "http://localhost:3000/api/wallets/mother" -ContentType "application/json"
    Write-Host "Response:" -ForegroundColor Green
    $response | ConvertTo-Json -Depth 10
    
    # Save the mother wallet public key and private key for later use
    $motherWalletPublicKey = $response.motherWalletPublicKey
    $motherWalletPrivateKey = $response.motherWalletPrivateKeyBase58
    
    Write-Host "`nMother wallet public key: $motherWalletPublicKey" -ForegroundColor Cyan
} catch {
    Write-Host "Error creating mother wallet: $_" -ForegroundColor Red
}

# Test importing an existing mother wallet using the private key we just obtained
Write-Host "`nImporting the mother wallet we just created..." -ForegroundColor Yellow
$body = @{
    privateKeyBase58 = $motherWalletPrivateKey  # Use the key from the first request
} | ConvertTo-Json

try {
    $importResponse = Invoke-RestMethod -Method POST -Uri "http://localhost:3000/api/wallets/mother" -Body $body -ContentType "application/json"
    Write-Host "Response:" -ForegroundColor Green
    $importResponse | ConvertTo-Json -Depth 10
    
    # Verify that the imported wallet public key matches the original
    if ($importResponse.motherWalletPublicKey -eq $motherWalletPublicKey) {
        Write-Host "`nSUCCESS: Imported wallet public key matches the original." -ForegroundColor Green
    } else {
        Write-Host "`nERROR: Imported wallet public key does NOT match the original!" -ForegroundColor Red
        Write-Host "Original: $motherWalletPublicKey" -ForegroundColor Yellow
        Write-Host "Imported: $($importResponse.motherWalletPublicKey)" -ForegroundColor Yellow
    }
} catch {
    Write-Host "Error importing mother wallet: $_" -ForegroundColor Red
}

# Test getting mother wallet info
Write-Host "`nGetting mother wallet info..." -ForegroundColor Yellow
try {
    $infoResponse = Invoke-RestMethod -Method GET -Uri "http://localhost:3000/api/wallets/mother/$motherWalletPublicKey"
    Write-Host "Response:" -ForegroundColor Green
    $infoResponse | ConvertTo-Json -Depth 10
    
    Write-Host "`nWallet balance: $($infoResponse.balanceSol) SOL ($($infoResponse.balanceLamports) lamports)" -ForegroundColor Cyan
} catch {
    Write-Host "Error getting wallet info: $_" -ForegroundColor Red
}

# Test deriving child wallets
Write-Host "`nDeriving child wallets from mother wallet..." -ForegroundColor Yellow
$childWalletRequest = @{
    motherWalletPublicKey = $motherWalletPublicKey
    count = 3
    saveToFile = $false
} | ConvertTo-Json

try {
    $childWalletResponse = Invoke-RestMethod -Method POST -Uri "http://localhost:3000/api/wallets/children" -Body $childWalletRequest -ContentType "application/json"
    Write-Host "Response:" -ForegroundColor Green
    $childWalletResponse | ConvertTo-Json -Depth 10
    
    # Store child wallet information for later use
    $childWallets = $childWalletResponse.childWallets
    
    Write-Host "`nGenerated $($childWallets.Count) child wallets:" -ForegroundColor Cyan
    $i = 1
    foreach ($wallet in $childWallets) {
        Write-Host "Child Wallet $i - Public Key: $($wallet.publicKey)" -ForegroundColor Cyan
        $i++
    }
    
    # Test the generic wallet balance endpoint with the first child wallet
    if ($childWallets.Count -gt 0) {
        $firstChildPublicKey = $childWallets[0].publicKey
        Write-Host "`nGetting balance of first child wallet ($firstChildPublicKey)..." -ForegroundColor Yellow
        try {
            $childBalanceResponse = Invoke-RestMethod -Method GET -Uri "http://localhost:3000/api/wallets/balance/$firstChildPublicKey"
            Write-Host "Response:" -ForegroundColor Green
            $childBalanceResponse | ConvertTo-Json -Depth 10
            
            Write-Host "`nChild wallet balance: $($childBalanceResponse.balanceSol) SOL ($($childBalanceResponse.balanceLamports) lamports)" -ForegroundColor Cyan
        } catch {
            Write-Host "Error getting child wallet balance: $_" -ForegroundColor Red
        }
    }
} catch {
    Write-Host "Error deriving child wallets: $_" -ForegroundColor Red
}

# Test funding child wallets
# Note: This test is commented out by default as it would use real SOL
# Uncomment and run only if you have a funded mother wallet and want to test funding

<#
Write-Host "`nFunding child wallets from mother wallet..." -ForegroundColor Yellow
# Create a request with just the first child wallet to test funding
$fundRequest = @{
    motherWalletPrivateKeyBase58 = $motherWalletPrivateKey
    childWallets = @(
        @{
            publicKey = $childWallets[0].publicKey
            amountSol = 0.001  # Fund with a small amount, e.g., 0.001 SOL
        }
    )
} | ConvertTo-Json

try {
    Write-Host "WARNING: This will use REAL SOL from the mother wallet!" -ForegroundColor Red
    $confirmation = Read-Host "Do you want to continue? (y/n)"
    
    if ($confirmation.ToLower() -eq "y") {
        $fundResponse = Invoke-RestMethod -Method POST -Uri "http://localhost:3000/api/wallets/fund-children" -Body $fundRequest -ContentType "application/json"
        Write-Host "Response:" -ForegroundColor Green
        $fundResponse | ConvertTo-Json -Depth 10
        
        Write-Host "`nFunding status: $($fundResponse.status)" -ForegroundColor Cyan
        Write-Host "Mother wallet final balance: $($fundResponse.motherWalletFinalBalanceSol) SOL" -ForegroundColor Cyan
        
        $i = 1
        foreach ($result in $fundResponse.results) {
            if ($result.status -eq "funded") {
                Write-Host "Child Wallet $i - Status: FUNDED - New Balance: $($result.newBalanceSol) SOL" -ForegroundColor Green
            } else {
                Write-Host "Child Wallet $i - Status: FAILED - Error: $($result.error)" -ForegroundColor Red
            }
            $i++
        }
    } else {
        Write-Host "Funding test skipped." -ForegroundColor Yellow
    }
} catch {
    Write-Host "Error funding child wallets: $_" -ForegroundColor Red
}
#>

Write-Host "`nAPI testing completed." -ForegroundColor Cyan 