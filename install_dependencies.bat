@echo off
echo ========================================
echo SmartSafe V27 - Install Dependencies
echo ========================================
echo.

echo [1/3] Installing Python dependencies...
pip install -r requirements_no_compile.txt
if errorlevel 1 (
    echo ERROR: Python dependencies failed
    pause
    exit /b 1
)
echo.

echo [2/3] Installing Node.js dependencies...
cd whatsapp-server
call npm install
cd ..
echo.

echo [3/3] All dependencies installed!
echo.
echo You can now run start_smartsafe.bat
echo.
pause
