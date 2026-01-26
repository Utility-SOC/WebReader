@echo off
TITLE Update WebReader
COLOR 0B

echo ==================================================
echo      Scientific Speed Reader - Updater
echo ==================================================
echo.

echo [INFO] Pulling latest changes from GitHub...
git pull origin master

IF %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Update failed.
    echo Make sure you have git installed and this folder is a git repository.
    echo.
) ELSE (
    echo.
    echo [SUCCESS] Updated successfully!
    echo.
)

pause
