#!/bin/bash
echo "=================================================="
echo "     Scientific Speed Reader - Updater"
echo "=================================================="
echo

echo "[INFO] Pulling latest changes from GitHub..."
git pull origin master

if [ $? -eq 0 ]; then
    echo
    echo "[SUCCESS] Updated successfully!"
    echo
else
    echo
    echo "[ERROR] Update failed."
    echo "Make sure git is installed."
    echo
fi
