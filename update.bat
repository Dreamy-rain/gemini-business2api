@echo off
REM Gemini Business2API Update Script for Windows
REM This script updates the project to the latest version

setlocal enabledelayedexpansion

echo ==========================================
echo Gemini Business2API Update Script
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

REM Step 1: Backup current .env file
echo [INFO] Backing up .env file...
if exist ".env" (
    copy /Y ".env" ".env.backup" >nul
    echo [SUCCESS] .env backed up to .env.backup
) else (
    echo [INFO] No .env file found, skipping backup
)

REM Step 2: Pull latest code from git
echo [INFO] Pulling latest code from git...
git fetch origin
git pull origin main 2>nul
if %errorlevel% neq 0 (
    git pull origin master 2>nul
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to pull latest code
        exit /b 1
    )
)
echo [SUCCESS] Code updated successfully

REM Step 3: Restore .env file
if exist ".env.backup" (
    echo [INFO] Restoring .env file...
    move /Y ".env.backup" ".env" >nul
    echo [SUCCESS] .env restored
)

REM Step 4: Update Python dependencies
echo [INFO] Updating Python dependencies...

REM Check if virtual environment exists
if exist ".venv\Scripts\activate.bat" (
    echo [INFO] Virtual environment detected, activating...
    call .venv\Scripts\activate.bat
)

python -m pip install -r requirements.txt --upgrade
if %errorlevel% neq 0 (
    echo [ERROR] Failed to update Python dependencies
    exit /b 1
)
echo [SUCCESS] Python dependencies updated

REM Step 5: Update frontend dependencies
if exist "frontend" (
    echo [INFO] Updating frontend dependencies...
    cd frontend

    REM Check if npm is installed
    where npm >nul 2>nul
    if %errorlevel% equ 0 (
        call npm install
        if %errorlevel% equ 0 (
            call npm run build
            if %errorlevel% equ 0 (
                echo [SUCCESS] Frontend dependencies updated and built
            ) else (
                echo [ERROR] Frontend build failed
            )
        ) else (
            echo [ERROR] npm install failed
        )
    ) else (
        echo [WARNING] npm is not installed. Skipping frontend update.
    )

    cd ..
)

REM Step 6: Show completion message
echo.
echo ==========================================
echo [SUCCESS] Update completed successfully!
echo ==========================================
echo.
echo [INFO] To restart the service, run:
echo   python main.py
echo.
echo [INFO] Or if running as a Windows service:
echo   net stop gemini-business2api
echo   net start gemini-business2api
echo.

endlocal
