@echo off
setlocal EnableExtensions

title SmartSafe V27 - Quick Start
cd /d "%~dp0"

echo.
echo ============================================================
echo   SmartSafe V27 - Quick Start (No Install)
echo ============================================================
echo.
echo [INFO] Starts Node server + GUI without installing deps.
echo.

:: Check Python
python --version >NUL 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python is not installed!
    echo        Please install Python 3.10+ from https://python.org
    pause
    exit /b 1
)

:: Check Node.js
node --version >NUL 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Node.js is not installed!
    echo        Please install Node.js 18+ from https://nodejs.org
    pause
    exit /b 1
)

:: Start Node server in a separate window
start "SmartSafe Server" node whatsapp-server\index.js > nul 2>&1

:: Launch GUI
start "" pythonw main.py

echo.
echo [OK] SmartSafe V27 started.
echo [INFO] Use STOP_SMARTSAFE.bat to stop.
echo.
