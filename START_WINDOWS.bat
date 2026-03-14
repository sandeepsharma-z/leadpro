@echo off
title LeadPro - Lead Generation Engine
echo.
echo  ==========================================
echo   LeadPro - Lead Generation Engine v1.0
echo  ==========================================
echo.

:: Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found! Install Python 3.10+ from python.org
    pause
    exit
)

:: Install dependencies
echo [1/3] Installing dependencies...
pip install flask requests beautifulsoup4 lxml pypdf python-docx openpyxl -q

:: Create data folder
if not exist "data" mkdir data

echo [2/3] Starting LeadPro server...
echo.
echo  Open your browser at: http://localhost:5000
echo  Press Ctrl+C to stop
echo.

:: Open browser automatically after 2 seconds
start /b cmd /c "timeout /t 2 >nul && start http://localhost:5000"

:: Run the app
python app.py

pause

