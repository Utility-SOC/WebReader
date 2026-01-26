#!/bin/bash

# Configuration
PORT=8182
VENV_DIR="."
PYTHON="$VENV_DIR/bin/python3"
PIP="$VENV_DIR/bin/pip"
UVICORN="$VENV_DIR/bin/uvicorn"

echo "=================================================="
echo "     Scientific Speed Reader - Launcher"
echo "=================================================="
echo

# 1. Check for Python
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] python3 could not be found."
    echo "Please install Python 3 (sudo apt install python3 python3-venv)"
    exit 1
fi

# 2. Create Venv
if [ ! -d "$VENV_DIR" ]; then
    echo "[INFO] Creating Virtual Environment..."
    python3 -m venv "$VENV_DIR"
fi

# 3. Install Deps
echo "[INFO] Checking dependencies..."
"$PIP" install -r requirements.txt > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "[INFO] Installing dependencies..."
    "$PIP" install -r requirements.txt
fi

# 4. Check for System Dependencies (espeak, tesseract)
MISSING=""
if ! command -v tesseract &> /dev/null; then
    MISSING="$MISSING tesseract-ocr"
fi
if ! command -v espeak &> /dev/null; then
    MISSING="$MISSING espeak"
fi

if [ ! -z "$MISSING" ]; then
    echo
    echo "[WARNING] Missing System Dependencies:$MISSING"
    echo "Attempting to install via sudo apt-get (Debian/Ubuntu)..."
    echo "You may be prompted for your password."
    
    if command -v apt-get &> /dev/null; then
        sudo apt-get update && sudo apt-get install -y $MISSING
    else
        echo "[ERROR] 'apt-get' not found. Please install manually:$MISSING"
    fi
    echo
fi

# 5. Launch
echo "[INFO] Starting Server on port $PORT..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    open "http://localhost:$PORT"
else
    xdg-open "http://localhost:$PORT" &> /dev/null &
fi

# Run using explicit python path to module
"$PYTHON" -m uvicorn backend:app --reload --host 0.0.0.0 --port $PORT
