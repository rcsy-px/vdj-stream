@echo off
setlocal
set "PROJECT_ROOT=%~dp0.."
cd /d "%PROJECT_ROOT%"
set "PATH=%PROJECT_ROOT%\tools\uv;%PROJECT_ROOT%\tools\yt-dlp;%PROJECT_ROOT%\tools\ffmpeg\bin;%PATH%"
set "UV_CACHE_DIR=%PROJECT_ROOT%\.cache\uv"
set "UV_PYTHON_INSTALL_DIR=%PROJECT_ROOT%\tools\python"
set "PLAYWRIGHT_BROWSERS_PATH=%PROJECT_ROOT%\tools\playwright-browsers"
if not exist "tools\uv\uv.exe" (
  echo uv is missing. Run powershell -ExecutionPolicy Bypass -File scripts\bootstrap-tools.ps1
  exit /b 1
)
uv python install 3.12 || exit /b 1
uv venv || exit /b 1
uv sync || exit /b 1
uv run python -m playwright install chromium || exit /b 1
echo Playwright Chromium installed under tools\playwright-browsers.
