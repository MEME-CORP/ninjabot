@echo off
echo =============================================
echo Starting Solana API Server...
echo =============================================

cd %~dp0
echo Current directory: %CD%

:: Check if node is installed
where node >nul 2>nul
if %ERRORLEVEL% neq 0 (
  echo ERROR: Node.js is not installed or not in PATH
  echo Please install Node.js and try again
  pause
  exit /b 1
)

:: Check if the index.js file exists
if not exist "api\index.js" (
  echo ERROR: api\index.js not found
  echo Make sure you're running this from the solana directory
  pause
  exit /b 1
)

echo Starting server on port 3000...
echo Press Ctrl+C to stop the server
echo =============================================

:: Run the server
node api\index.js

:: Handle server exit
if %ERRORLEVEL% neq 0 (
  echo =============================================
  echo Server exited with error code %ERRORLEVEL%
  echo =============================================
  pause
) else (
  echo =============================================
  echo Server stopped
  echo =============================================
) 