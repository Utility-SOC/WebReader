@echo off
TITLE Scientific Speed Reader
cd /d "%~dp0"
PowerShell -NoProfile -ExecutionPolicy Bypass -Command "& './run_windows.ps1'"
pause
