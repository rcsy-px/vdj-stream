@echo off
setlocal
set "PROJECT_ROOT=%~dp0.."
cd /d "%PROJECT_ROOT%"
set "PATH=%PROJECT_ROOT%\tools\uv;%PROJECT_ROOT%\tools\yt-dlp;%PROJECT_ROOT%\tools\ffmpeg\bin;%PATH%"
set "UV_CACHE_DIR=%PROJECT_ROOT%\.cache\uv"
set "UV_PYTHON_INSTALL_DIR=%PROJECT_ROOT%\tools\python"
set "PLAYWRIGHT_BROWSERS_PATH=%PROJECT_ROOT%\tools\playwright-browsers"
rem Do not use --reload on Windows: Uvicorn's reload process selects an event
rem loop that cannot launch the Playwright and yt-dlp subprocesses.
powershell -NoProfile -ExecutionPolicy Bypass -File "%PROJECT_ROOT%\scripts\stop-backend.ps1" -Port 8765
if errorlevel 1 (
  echo Backend startup cancelled because port 8765 is occupied.
  pause
  exit /b 1
)
uv run uvicorn backend.app.main:app --host 127.0.0.1 --port 8765
pause
