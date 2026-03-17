@echo off
echo ========================================
echo SmartSafe V27 - Starting All Services
echo ========================================
echo.

echo Starting WhatsApp Server...
start "WhatsApp Server" cmd /k "cd whatsapp-server && npm start"

timeout /t 5 /nobreak >nul

echo Starting Main GUI...
start "" python main.py

echo.
echo ========================================
echo SmartSafe V27 is running!
echo - GUI: Opens automatically
echo - WhatsApp Server: http://localhost:4000
echo ========================================
echo.
echo Press any key to exit this window...
pause >nul
