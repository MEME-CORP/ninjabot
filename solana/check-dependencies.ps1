# Check if required dependencies are installed for the Solana API
$ErrorActionPreference = "Stop"

Write-Host "Checking dependencies for Solana API..." -ForegroundColor Cyan

# Check if Node.js is installed
try {
    $nodeVersion = node --version
    Write-Host "✓ Node.js is installed: $nodeVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ Node.js is not installed or not in PATH" -ForegroundColor Red
    Write-Host "  Please install Node.js from https://nodejs.org/" -ForegroundColor Yellow
    exit 1
}

# Check if npm is installed
try {
    $npmVersion = npm --version
    Write-Host "✓ npm is installed: $npmVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ npm is not installed or not in PATH" -ForegroundColor Red
    Write-Host "  npm should be installed with Node.js" -ForegroundColor Yellow
    exit 1
}

# Check if required files exist
$requiredFiles = @(
    "api/index.js",
    "api/services/jupiterService.js",
    "api/services/walletService.js"
)

foreach ($file in $requiredFiles) {
    if (Test-Path $file) {
        Write-Host "✓ File exists: $file" -ForegroundColor Green
    } else {
        Write-Host "✗ Missing file: $file" -ForegroundColor Red
        Write-Host "  Please make sure all API files are in place" -ForegroundColor Yellow
        exit 1
    }
}

# Check if package.json exists and contains required dependencies
if (Test-Path "package.json") {
    Write-Host "✓ package.json exists" -ForegroundColor Green
    
    try {
        $packageJson = Get-Content "package.json" -Raw | ConvertFrom-Json
        $requiredDependencies = @(
            "express",
            "@solana/web3.js",
            "bs58",
            "node-fetch"
        )
        
        $missingDependencies = @()
        foreach ($dep in $requiredDependencies) {
            if (-not $packageJson.dependencies.$dep) {
                $missingDependencies += $dep
            }
        }
        
        if ($missingDependencies.Count -eq 0) {
            Write-Host "✓ All required dependencies are in package.json" -ForegroundColor Green
        } else {
            Write-Host "✗ Missing dependencies in package.json: $($missingDependencies -join ', ')" -ForegroundColor Red
            Write-Host "  Run 'npm install $($missingDependencies -join ' ')' to install them" -ForegroundColor Yellow
            exit 1
        }
    } catch {
        Write-Host "✗ Error parsing package.json: $_" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "✗ package.json not found" -ForegroundColor Red
    Write-Host "  Please make sure you're in the correct directory" -ForegroundColor Yellow
    exit 1
}

# Check if node_modules exists and has the required modules
if (Test-Path "node_modules") {
    Write-Host "✓ node_modules directory exists" -ForegroundColor Green
} else {
    Write-Host "✗ node_modules directory not found" -ForegroundColor Red
    Write-Host "  Run 'npm install' to install dependencies" -ForegroundColor Yellow
    exit 1
}

# All checks passed
Write-Host "`nAll dependency checks passed! You can now run the API server." -ForegroundColor Green
Write-Host "To start the server, run: .\run-api-server.cmd" -ForegroundColor Cyan 