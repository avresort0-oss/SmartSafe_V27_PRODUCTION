@echo off
setlocal EnableExtensions

title SmartSafe V27 GUI Launcher
cd /d "%~dp0"

echo.
echo ========================================
echo      Start SmartSafe V27 GUI
echo ========================================
echo.

IF NOT EXIST "main.py" (
    echo [ERROR] main.py not found!
    pause
    exit /b 1
)

echo [INFO] Launching GUI...
start "" pythonw main.py
