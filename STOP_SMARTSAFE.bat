@echo off
title Stop SmartSafe V27
color 0C

echo.
echo ========================================
echo      Stop SmartSafe V27
echo ========================================
echo.

echo [INFO] Attempting to gracefully stop SmartSafe V27 processes by window title...
echo [INFO] This will not affect other applications.
echo.

REM Stop the main Python GUI application by its window title
echo [1/2] Stopping SmartSafe V27 main application...
taskkill /fi "WINDOWTITLE eq SmartSafe V27*" /f /t >nul 2>&1

REM Stop the Node.js backend server by its window title.
REM This matches titles set by ONE_CLICK_SETUP_AND_RUN.bat and START_SMARTSAFE_ONE_CLICK.bat
echo [2/2] Stopping Node.js backend server...
taskkill /fi "WINDOWTITLE eq SmartSafe*Server*" /f /t >nul 2>&1

echo.
echo [INFO] SmartSafe V27 stop sequence completed.
echo        Any related processes should now be terminated.
timeout /t 2 /nobreak >nul
