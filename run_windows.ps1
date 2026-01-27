# Scientific Speed Reader - Launcher
$ErrorActionPreference = "Stop"

# --- CONFIGURATION ---
$port = 8182
# ---------------------

Write-Host "==================================================" -ForegroundColor Green
Write-Host "     Scientific Speed Reader - Launcher"
Write-Host "=================================================="
Write-Host ""

# 1. Check Python
try {
    $pyVersion = python --version 2>&1
    Write-Host "[INFO] Python found: $pyVersion" -ForegroundColor Gray
}
catch {
    Write-Host "[ERROR] Python not found or not in PATH." -ForegroundColor Red
    Write-Host "Please install Python 3.9+ from python.org and check 'Add to PATH'."
    Read-Host "Press Enter to exit..."
    exit 1
}

# 2. Virtual Environment
# User requested root-level venv (Scripts folder in current dir)
if (-not (Test-Path "Scripts")) {
    Write-Host "[INFO] Creating Virtual Environment in current folder..." -ForegroundColor Cyan
    python -m venv .
}

# 3. Dependencies
# Use pip from local Scripts folder
$pipPath = ".\Scripts\pip.exe"
if (-not (Test-Path $pipPath)) {
    Write-Host "[ERROR] pip not found in Scripts folder. Venv creation might have failed." -ForegroundColor Red
    exit 1
}

Write-Host "[INFO] Checking dependencies..." -ForegroundColor Gray
& $pipPath install -r requirements.txt | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[INFO] Installing dependencies (first run)..." -ForegroundColor Cyan
    & $pipPath install -r requirements.txt
}

# 4. Check/Install Tesseract
$tess = Get-Command "tesseract" -ErrorAction SilentlyContinue
    
# Check common location if not in PATH
$tessPathDefault = "C:\Program Files\Tesseract-OCR\tesseract.exe"
if ($null -eq $tess -and (Test-Path $tessPathDefault)) {
    Write-Host "[INFO] Tesseract found in Program Files but not in PATH." -ForegroundColor Yellow
         
    # 1. Add to Current Session PATH immediately so app works NOW
    $env:Path += ";C:\Program Files\Tesseract-OCR"
    Write-Host "[INFO] Added to current session PATH." -ForegroundColor Gray
         
    # 2. Trigger UAC to add to System PATH permanently
    Write-Host "[INFO] Requesting Admin privileges to add to System PATH permanently..." -ForegroundColor Cyan
    $proc = Start-Process powershell -ArgumentList "-NoProfile -Command `"[Environment]::SetEnvironmentVariable('Path', [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';C:\Program Files\Tesseract-OCR', 'Machine')`"" -Verb RunAs -PassThru
    $proc.WaitForExit()
    Write-Host "[SUCCESS] Added to System PATH." -ForegroundColor Green
         
    # Re-check
    $tess = Get-Command "tesseract" -ErrorAction SilentlyContinue
}

if ($null -eq $tess) {
    Write-Host "[WARNING] Tesseract OCR not found." -ForegroundColor Yellow
    Write-Host "Attempting install via Winget..." -ForegroundColor Cyan
        
    winget install -e --id UB-Mannheim.TesseractOCR
        
    # Refresh env logic for current session
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
        
    # Check if installed (regardless of winget exit code)
    if (Get-Command "tesseract" -ErrorAction SilentlyContinue) {
        Write-Host "[SUCCESS] Tesseract is installed." -ForegroundColor Green
    }
    elseif (Test-Path "C:\Program Files\Tesseract-OCR\tesseract.exe") {
        Write-Host "[SUCCESS] Tesseract found in Program Files." -ForegroundColor Green
        # Try UAC mechanism again if it was just installed
        try {
            Start-Process powershell -ArgumentList "-NoProfile -Command `"[Environment]::SetEnvironmentVariable('Path', [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';C:\Program Files\Tesseract-OCR', 'Machine')`"" -Verb RunAs -Wait
            $env:Path += ";C:\Program Files\Tesseract-OCR"
        }
        catch {
            Write-Host "[WARN] Could not auto-add to PATH (UAC cancelled?)." -ForegroundColor Yellow
        }
    }
    else {
        Write-Host "[WARNING] Auto-install finished but 'tesseract' not found in PATH." -ForegroundColor Yellow
        Write-Host "You may need to restart your computer."
    }
}
}
catch {
    Write-Host "[WARN] Tesseract check encountered an error: $_"
}

# 5. Launch
Write-Host ""
Write-Host "[INFO] Starting Server on http://localhost:$port" -ForegroundColor Green
Write-Host "[INFO] Browser should open automatically."
Write-Host ""

Start-Process "http://localhost:$port"

# Run Uvicorn from venv
$uvicornPath = ".\Scripts\uvicorn.exe"
& $uvicornPath backend:app --reload --host 0.0.0.0 --port $port
