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
if (-not (Test-Path "venv")) {
    Write-Host "[INFO] Creating Virtual Environment..." -ForegroundColor Cyan
    python -m venv venv
}

# 3. Dependencies
# Use pip from venv
$pipPath = "venv\Scripts\pip.exe"
if (-not (Test-Path $pipPath)) {
    Write-Host "[ERROR] pip not found in venv. Something went wrong." -ForegroundColor Red
    exit 1
}

Write-Host "[INFO] Checking dependencies..." -ForegroundColor Gray
& $pipPath install -r requirements.txt | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[INFO] Installing dependencies (first run)..." -ForegroundColor Cyan
    & $pipPath install -r requirements.txt
}

# 4. Check/Install Tesseract
try {
    $tess = Get-Command "tesseract" -ErrorAction SilentlyContinue
    if ($null -eq $tess) {
        Write-Host "[WARNING] Tesseract OCR not found." -ForegroundColor Yellow
        Write-Host "Attempting install via Winget..." -ForegroundColor Cyan
        
        winget install -e --id UB-Mannheim.TesseractOCR
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[SUCCESS] Tesseract installed. You may need to restart." -ForegroundColor Green
        }
        else {
            Write-Host "[ERROR] Auto-install failed. Please install manually:" -ForegroundColor Red
            Write-Host "https://github.com/UB-Mannheim/tesseract/wiki"
        }
    }
}
catch {
    Write-Host "[WARN] Could not check for Tesseract."
}

# 5. Launch
Write-Host ""
Write-Host "[INFO] Starting Server on http://localhost:$port" -ForegroundColor Green
Write-Host "[INFO] Browser should open automatically."
Write-Host ""

Start-Process "http://localhost:$port"

# Run Uvicorn from venv
$uvicornPath = "venv\Scripts\uvicorn.exe"
& python -m uvicorn backend:app --reload --host 0.0.0.0 --port $port
