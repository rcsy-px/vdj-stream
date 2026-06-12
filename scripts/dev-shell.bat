@echo off
setlocal
set "PROJECT_ROOT=%~dp0.."
cd /d "%PROJECT_ROOT%"
set "PATH=%PROJECT_ROOT%\tools\uv;%PROJECT_ROOT%\tools\yt-dlp;%PROJECT_ROOT%\tools\ffmpeg\bin;%PATH%"
set "UV_CACHE_DIR=%PROJECT_ROOT%\.cache\uv"
set "UV_PYTHON_INSTALL_DIR=%PROJECT_ROOT%\tools\python"
set "PLAYWRIGHT_BROWSERS_PATH=%PROJECT_ROOT%\tools\playwright-browsers"
echo Project-local development shell ready.
cmd /k
