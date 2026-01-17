@echo off
REM Gemini Business2API Unified Setup Script for Windows
REM This script handles both initial deployment and updates
REM Usage:
REM   setup.bat          - Initial deployment
REM   setup.bat --update - Update existing installation

setlocal enabledelayedexpansion

echo ==========================================
echo Gemini Business2API Setup Script
echo ==========================================
echo.

REM Determine mode (initial deployment or update)
set UPDATE_MODE=false
if "%1"=="--update" (
    set UPDATE_MODE=true
    echo [INFO] Running in UPDATE mode
) else (
    echo [INFO] Running in INITIAL DEPLOYMENT mode
)
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

REM Step 1: Backup .env file (update mode only)
if "%UPDATE_MODE%"=="true" (
    echo [STEP] Step 1: Backing up configuration...
    if exist .env (
        copy .env .env.backup >nul
        echo [SUCCESS] .env backed up to .env.backup
    ) else (
        echo [INFO] No .env file found, skipping backup
    )
    echo.
)

REM Step 2: Pull latest code from git (both modes)
echo [STEP] Step 2: Syncing code from repository...
echo [INFO] Fetching latest changes...
git fetch origin

echo [INFO] Pulling latest code...
git pull origin main 2>nul || git pull origin master 2>nul
if %errorlevel% equ 0 (
    echo [SUCCESS] Code synchronized successfully
) else (
    echo [INFO] No remote changes to pull (this is normal for initial deployment)
)
echo.

REM Step 3: Restore .env file (update mode only)
if "%UPDATE_MODE%"=="true" (
    if exist .env.backup (
        echo [STEP] Step 3: Restoring configuration...
        move /y .env.backup .env >nul
        echo [SUCCESS] .env restored
        echo.
    )
)

REM Step 4: Setup .env file (initial deployment only)
if "%UPDATE_MODE%"=="false" (
    echo [STEP] Step 3: Setting up configuration...
    if exist .env (
        echo [INFO] .env file already exists, skipping
    ) else (
        if exist .env.example (
            copy .env.example .env >nul
            echo [SUCCESS] .env file created from .env.example
        ) else (
            echo [ERROR] .env.example not found
            exit /b 1
        )
    )
    echo.
)

REM Step 5: Setup Python virtual environment
echo [STEP] Step 4: Setting up Python environment...
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

REM Step 6: Install/Update Python dependencies
echo [STEP] Step 5: Installing Python dependencies...
if "%UPDATE_MODE%"=="true" (
    pip install -r requirements.txt --upgrade
    echo [SUCCESS] Python dependencies updated
) else (
    pip install -r requirements.txt
    echo [SUCCESS] Python dependencies installed
)
echo.

REM Step 7: Setup frontend
echo [STEP] Step 6: Setting up frontend...
if exist frontend (
    cd frontend

    REM Check if npm is installed
    where npm >nul 2>nul
    if %errorlevel% equ 0 (
        echo [INFO] Installing frontend dependencies...
        call npm install

        echo [INFO] Building frontend...
        call npm run build
        echo [SUCCESS] Frontend built successfully
    ) else (
        if "%UPDATE_MODE%"=="false" (
            echo [ERROR] npm is not installed. Please install Node.js and npm first.
            cd ..
            exit /b 1
        ) else (
            echo [ERROR] npm is not installed. Skipping frontend update.
        )
    )

    cd ..
) else (
    echo [ERROR] Frontend directory not found. Are you in the project root?
    exit /b 1
)
echo.

REM Step 8: Show completion message
echo ==========================================
echo [SUCCESS] Setup completed successfully!
echo ==========================================
echo.

if "%UPDATE_MODE%"=="true" (
    echo [INFO] Update completed. To restart the service:
    echo.
    echo   python main.py
    echo.
) else (
    echo [INFO] Initial deployment completed. Next steps:
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
    echo [INFO] To activate virtual environment later, run:
    echo   .venv\Scripts\activate.bat
)
echo.

endlocal
