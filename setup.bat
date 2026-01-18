@echo off
REM Gemini Business2API Setup Script
REM Handles both installation and updates automatically
REM Usage: setup.bat

setlocal enabledelayedexpansion

echo ==========================================
echo Gemini Business2API Setup Script
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

REM Step 1: Pull latest code from git
echo [STEP] Step 1: Syncing code from repository...
echo [INFO] Fetching latest changes...
git fetch origin

echo [INFO] Pulling latest code...
git pull origin main 2>nul || git pull origin master 2>nul
if %errorlevel% equ 0 (
    echo [SUCCESS] Code synchronized successfully
) else (
    echo [INFO] No remote changes to pull
)
echo.

REM Step 2: Setup .env file if it doesn't exist
echo [STEP] Step 2: Checking configuration...
if exist .env (
    echo [INFO] .env file exists
) else (
    if exist .env.example (
        copy .env.example .env >nul
        echo [SUCCESS] .env file created from .env.example
        echo [INFO] Please edit .env and configure your ADMIN_KEY
    ) else (
        echo [ERROR] .env.example not found
        exit /b 1
    )
)
echo.

REM Step 3: Setup Python virtual environment
echo [STEP] Step 3: Setting up Python environment...
if exist .venv (
    echo [INFO] Virtual environment already exists
) else (
    echo [INFO] Creating virtual environment...
    python -m venv .venv
    echo [SUCCESS] Virtual environment created
)

echo [INFO] Activating virtual environment...
call .venv\Scripts\activate.bat

echo [INFO] Upgrading pip...
python -m pip install --upgrade pip --quiet
echo [SUCCESS] Pip upgraded
echo.

REM Step 4: Install/Update Python dependencies
echo [STEP] Step 4: Installing Python dependencies...
pip install -r requirements.txt --upgrade
echo [SUCCESS] Python dependencies installed
echo.

REM Step 5: Setup frontend
echo [STEP] Step 5: Setting up frontend...
if exist frontend (
    cd frontend

    REM Check if npm is installed
    where npm >nul 2>nul
    if %errorlevel% equ 0 (
        echo [INFO] Installing dependencies...
        call npm install

        echo [INFO] Building frontend...
        call npm run build
        echo [SUCCESS] Frontend built successfully
    ) else (
        echo [ERROR] npm is not installed. Please install Node.js and npm first.
        cd ..
        exit /b 1
    )

    cd ..
) else (
    echo [ERROR] Frontend directory not found. Are you in the project root?
    exit /b 1
)
echo.

REM Step 6: Show completion message
echo ==========================================
echo [SUCCESS] Setup completed successfully!
echo ==========================================
echo.

if exist .env (
    echo [INFO] Next steps:
    echo.
    echo   1. Edit .env file if needed:
    echo      notepad .env
    echo.
    echo   2. Start the service:
    echo      python main.py
    echo.
    echo   3. Access the admin panel:
    echo      http://localhost:7860/
    echo.
    echo [INFO] To activate virtual environment later, run:
    echo   .venv\Scripts\activate.bat
)
echo.

endlocal
