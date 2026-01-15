@echo off
REM Gemini Business2API Deployment Script for Windows
REM This script automates the initial deployment process

setlocal enabledelayedexpansion

echo ==========================================
echo Gemini Business2API Deployment Script
echo ==========================================
echo.

REM Check if git is installed
where git >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Git is not installed. Please install git first.
    exit /b 1
)

REM Check if python is installed
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed. Please install Python 3.11+ first.
    exit /b 1
)

REM Check if npm is installed
where npm >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] npm is not installed. Please install Node.js and npm first.
    exit /b 1
)

REM Step 1: Build frontend
echo [STEP] Step 1: Building frontend...
if exist "frontend" (
    cd frontend
    echo [INFO] Installing frontend dependencies...
    call npm install
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install frontend dependencies
        exit /b 1
    )

    echo [INFO] Building frontend...
    call npm run build
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to build frontend
        exit /b 1
    )

    echo [SUCCESS] Frontend built successfully
    cd ..
) else (
    echo [ERROR] Frontend directory not found. Are you in the project root?
    exit /b 1
)

REM Step 2: Create virtual environment
echo [STEP] Step 2: Setting up Python virtual environment...
if exist ".venv" (
    echo [INFO] Virtual environment already exists, skipping creation
) else (
    echo [INFO] Creating virtual environment...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment
        exit /b 1
    )
    echo [SUCCESS] Virtual environment created
)

REM Activate virtual environment
echo [INFO] Activating virtual environment...
call .venv\Scripts\activate.bat

REM Step 3: Install Python dependencies
echo [STEP] Step 3: Installing Python dependencies...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install Python dependencies
    exit /b 1
)
echo [SUCCESS] Python dependencies installed

REM Step 4: Setup .env file
echo [STEP] Step 4: Setting up configuration...
if exist ".env" (
    echo [INFO] .env file already exists, skipping
) else (
    if exist ".env.example" (
        copy /Y ".env.example" ".env" >nul
        echo [SUCCESS] .env file created from .env.example
    ) else (
        echo [ERROR] .env.example not found
        exit /b 1
    )
)

REM Step 5: Show completion message
echo.
echo ==========================================
echo [SUCCESS] Deployment completed successfully!
echo ==========================================
echo.
echo [INFO] Next steps:
echo.
echo   1. Edit .env file and set your ADMIN_KEY:
echo      notepad .env
echo.
echo   2. Start the service:
echo      python main.py
echo.
echo   3. Access the admin panel:
echo      http://localhost:7860/
echo.
echo [INFO] Optional: To activate virtual environment later, run:
echo   .venv\Scripts\activate.bat
echo.

endlocal
