@echo off
REM Quick Start Script for Reliable FTP Dashboard

echo.
echo ========================================
echo  Reliable FTP Dashboard - Quick Start
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python is not installed or not in PATH
    pause
    exit /b 1
)

echo Installing dependencies...
pip install -r requirements_dashboard.txt

echo.
echo ========================================
echo  Setup Complete!
echo ========================================
echo.
echo To start the system:
echo.
echo Terminal 1 - Start FTP Server:
echo   python server.py
echo.
echo Terminal 2 - Start Dashboard:
echo   python dashboard.py
echo.
echo Then open your browser to: http://localhost:5000
echo.
pause
