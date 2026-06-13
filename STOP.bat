@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop-backend.ps1" -Port 8765
if errorlevel 1 pause
