@echo off
TITLE Scientific Speed Reader Server
COLOR 0A

echo ==================================================
echo      Scientific Speed Reader - Launcher
echo ==================================================
echo.

:: Check for Python
python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.9+ from python.org and try again.
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b
)

:: Create Virtual Environment if missing
IF NOT EXIST "venv" (
    echo [INFO] Creating Virtual Environment...
    python -m venv venv
    IF %ERRORLEVEL% NEQ 0 (
        echo [ERROR] Failed to create venv.
        pause
        exit /b
    )
)

:: Activate Venv
call venv\Scripts\activate

:: Install Dependencies
echo [INFO] Checking dependencies...
pip install -r requirements.txt >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [INFO] Installing dependencies - first run, this may take a moment
    pip install -r requirements.txt
)

:: Check for Tesseract (Auto-Install via Winget)
where tesseract >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo.
    echo [WARNING] Tesseract OCR is not found.
    echo Attempting to install via Windows Package Manager (winget)...
    
    winget install -e --id UB-Mannheim.TesseractOCR
    IF %ERRORLEVEL% EQ 0 (
        echo [SUCCESS] Tesseract installed! Use default path...
        :: Add default path to session for this run if possible, or warn user to restart
        echo [INFO] You may need to close and reopen this window for PATH changes to take effect.
        pause
    ) ELSE (
        echo [ERROR] Automatic install failed.
        echo Please manually install from: https://github.com/UB-Mannheim/tesseract/wiki
        pause
    )
    echo.
)

:: Configuration
set PORT=8000

:: Launch
echo.
echo [INFO] Starting Server on port %PORT%...
echo [INFO] Your browser should open automatically.
echo.

start "" "http://localhost:%PORT%"
uvicorn backend:app --reload --host 0.0.0.0 --port %PORT%

pause
