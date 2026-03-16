@echo off
setlocal EnableExtensions DisableDelayedExpansion

TITLE SmartSafe V27 - One Click Launcher
COLOR 0A

cd /d "%~dp0"
set "ROOT=%~dp0"

echo.
echo ============================================================
echo   SmartSafe V27 - One Click Launcher
echo   (Install Deps + Start Server + Launch GUI)
echo ============================================================
echo.
echo [INFO] Node server will read .env from project root or whatsapp-server\.env
echo.

:: -----------------------------------------------------------------------------
:: Check Python
:: -----------------------------------------------------------------------------
python --version >NUL 2>&1
IF %ERRORLEVEL% NEQ 0 (
    COLOR 0C
    echo [ERROR] Python is not installed!
    echo        Please install Python 3.10+ from https://python.org
    PAUSE
    EXIT /B 1
)
echo [OK] Python detected

:: -----------------------------------------------------------------------------
:: Check Node.js
:: -----------------------------------------------------------------------------
node --version >NUL 2>&1
IF %ERRORLEVEL% NEQ 0 (
    COLOR 0C
    echo [ERROR] Node.js is not installed!
    echo        Please install Node.js 18+ from https://nodejs.org
    PAUSE
    EXIT /B 1
)
echo [OK] Node.js detected

:: -----------------------------------------------------------------------------
:: Install Python Dependencies
:: -----------------------------------------------------------------------------
echo.
echo ============================================================
echo Step 1: Installing Python Dependencies...
echo ============================================================
echo.

IF NOT EXIST "requirements.txt" (
    COLOR 0C
    echo [ERROR] requirements.txt not found!
    PAUSE
    EXIT /B 1
)

echo Installing Python packages...
pip install -r requirements.txt
IF %ERRORLEVEL% NEQ 0 (
    echo [WARNING] Some packages may have failed to install
) ELSE (
    echo [OK] Python dependencies installed successfully
)

:: -----------------------------------------------------------------------------
:: Install Node.js Dependencies
:: -----------------------------------------------------------------------------
echo.
echo ============================================================
echo Step 2: Installing Node.js Dependencies...
echo ============================================================
echo.

IF NOT EXIST "whatsapp-server" (
    COLOR 0C
    echo [ERROR] whatsapp-server directory not found!
    PAUSE
    EXIT /B 1
)

IF NOT EXIST "whatsapp-server\package.json" (
    COLOR 0C
    echo [ERROR] whatsapp-server\package.json not found!
    PAUSE
    EXIT /B 1
)

PUSHD "whatsapp-server"
IF NOT EXIST "node_modules" (
    echo Installing Node packages...
    call npm install
    IF %ERRORLEVEL% NEQ 0 (
        echo [WARNING] Some Node packages may have failed
    ) ELSE (
        echo [OK] Node dependencies installed successfully
    )
) ELSE (
    echo [OK] Node modules already installed
)
POPD

:: -----------------------------------------------------------------------------
:: Start Backend Server
:: -----------------------------------------------------------------------------
echo.
echo ============================================================
echo Step 3: Starting Backend Server...
echo ============================================================
echo.

IF NOT EXIST "whatsapp-server\index.js" (
    COLOR 0C
    echo [ERROR] whatsapp-server\index.js not found!
    PAUSE
    EXIT /B 1
)

:: Start Node server in background without showing a new window
echo Starting Node server in a separate window...
START "SmartSafe Server" node whatsapp-server\index.js > nul 2>&1

:: Wait for server to initialize and check if it's running
echo Waiting for server to start...
set SERVER_READY=0
for /L %%i in (1,1,30) do (
    ping -n 2 127.0.0.1 > nul
    curl -s http://localhost:4000/health > nul 2>&1
    if !ERRORLEVEL! EQU 0 (
        set SERVER_READY=1
        echo [OK] Backend server is running on port 4000
        goto :server_started
    )
)

:server_started
IF !SERVER_READY! EQU 0 (
    echo [WARNING] Server may not have started properly, but continuing...
) ELSE (
    echo [OK] Backend server started successfully
)

:: -----------------------------------------------------------------------------
:: Launch GUI Application
:: -----------------------------------------------------------------------------
echo.
echo ============================================================
echo Step 4: Launching SmartSafe GUI...
echo ============================================================
echo.

IF NOT EXIST "main.py" (
    COLOR 0C
    echo [ERROR] main.py not found!
    PAUSE
    EXIT /B 1
)

start "" pythonw main.py
echo [OK] GUI launched

:: -----------------------------------------------------------------------------
:: Complete
:: -----------------------------------------------------------------------------
echo.
echo ============================================================
echo   SmartSafe V27 Started Successfully!
echo ============================================================
echo.
echo [INFO] API Server: http://localhost:4000
echo [INFO] GUI: Should open automatically
echo.
echo Press any key to exit this window...
PAUSE >NUL
