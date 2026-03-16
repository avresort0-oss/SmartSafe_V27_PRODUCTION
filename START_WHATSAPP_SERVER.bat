@echo off
setlocal EnableExtensions

title SmartSafe Server
cd /d "%~dp0"

echo.
echo ========================================
echo      Start WhatsApp Server
echo ========================================
echo.

IF NOT EXIST "whatsapp-server\index.js" (
    echo [ERROR] whatsapp-server\index.js not found!
    pause
    exit /b 1
)

echo [INFO] Starting Node.js server...
node whatsapp-server\index.js
