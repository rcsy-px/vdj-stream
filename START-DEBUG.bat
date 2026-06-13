@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup-and-start.ps1" -SetupOnly
if errorlevel 1 (
  echo.
  echo Setup failed. See the error above.
  pause
  exit /b 1
)
call "%~dp0scripts\run-backend.bat"
