@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup-and-start.ps1"
if errorlevel 1 (
  echo.
  echo Setup or startup failed. See the error above.
  pause
)
