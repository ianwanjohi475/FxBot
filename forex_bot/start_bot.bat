@echo off
title FxBot Live Trading
color 0A

echo ============================================
echo   FxBot - Live Trading Startup
echo ============================================
echo.

:: Move to the forex_bot folder (wherever this bat file lives)
cd /d "%~dp0"

:: Activate virtual environment
echo [1/3] Activating virtual environment...
call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo ERROR: Could not activate .venv
    echo Make sure .venv exists in %~dp0
    pause
    exit /b 1
)

:: Pull latest code
echo [2/3] Pulling latest code from GitHub...
git pull origin claude/forex-trading-bot-GZN5q
echo.

:: Start the bot
echo [3/3] Starting FxBot in LIVE mode...
echo Make sure MetaTrader 5 is open and Algo Trading is ON (green)
echo.
python main.py --live

:: If bot crashes, pause so you can read the error
echo.
echo Bot stopped. Press any key to close.
pause
