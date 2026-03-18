@echo off
echo ========================================
echo SmartSafe V27 - Stopping Services
echo ========================================
echo.
taskkill /F /IM python.exe 2>nul
taskkill /F /IM node.exe 2>nul
echo All services stopped!
pause
