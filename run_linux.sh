#!/bin/bash

echo "=================================================="
echo "     Scientific Speed Reader - Launcher"
echo "=================================================="
echo

# Check for Python
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] python3 could not be found."
    echo "Please install Python 3 (sudo apt install python3 python3-venv)"
    exit 1
fi

# Create Venv
if [ ! -d "venv" ]; then
    echo "[INFO] Creating Virtual Environment..."
    python3 -m venv venv
fi

# Activate
source venv/bin/activate

# Install Deps
echo "[INFO] Checking dependencies..."
pip install -r requirements.txt > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "[INFO] Installing dependencies..."
    pip install -r requirements.txt
fi

# Check for Dependencies (espeak, tesseract)
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
        echo "[ERROR] 'apt-get' not found. Please install manualy:$MISSING"
    fi
    echo
fi

# Configuration
PORT=8182

# Launch
echo "[INFO] Starting Server on port $PORT..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    open "http://localhost:$PORT"
else
    xdg-open "http://localhost:$PORT" &> /dev/null &
fi

uvicorn backend:app --reload --host 0.0.0.0 --port $PORT
