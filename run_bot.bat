@echo off
setlocal
title Woeyyy Discord Voice Bot (CLI Mode)
cd /d "%~dp0"

echo ============================================================
echo      Woeyyy Discord Voice Bot - Lightweight CLI Mode
echo ============================================================

:: 1. Verify Python installation
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo [ERROR] Python was not found on your system!
    echo Please install Python from https://www.python.org/downloads/
    pause
    exit /b 1
)

:: 2. Activate virtual environment if present
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

:: 3. Launch the Headless Discord Bot
python bot_cli.py

if errorlevel 1 (
    echo.
    echo [NOTICE] Bot process ended with an error code.
    pause
)
