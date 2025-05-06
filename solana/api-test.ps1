# Simple test to check if the API is running
try {
    $response = Invoke-RestMethod -Uri "http://localhost:3000" -Method GET -ErrorAction Stop
    Write-Host "API is running. Response: $response" -ForegroundColor Green
} catch {
    Write-Host "API is not running or not accessible: $_" -ForegroundColor Red
} 