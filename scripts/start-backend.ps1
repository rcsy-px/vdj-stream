param(
    [int]$Port = 8765,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Url = "http://127.0.0.1:$Port"

$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -First 1
if ($listener) {
    $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)"
    if ($processInfo.CommandLine -notmatch "uvicorn" -or $processInfo.CommandLine -notmatch "backend\.app\.main:app") {
        throw "Port $Port is already used by another application."
    }
    Write-Host "Backend is already running."
    if (-not $NoBrowser) {
        Start-Process $Url
    }
    exit 0
}

if (-not (Test-Path $Python)) {
    throw "Python environment is missing. Run START.bat first."
}

$env:PATH = "$(Join-Path $Root 'tools\uv');$(Join-Path $Root 'tools\yt-dlp');$(Join-Path $Root 'tools\ffmpeg\bin');$env:PATH"
$env:UV_CACHE_DIR = Join-Path $Root ".cache\uv"
$env:UV_PYTHON_INSTALL_DIR = Join-Path $Root "tools\python"
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $Root "tools\playwright-browsers"

$stdout = Join-Path $Root "data\logs\backend-stdout.log"
$stderr = Join-Path $Root "data\logs\backend-stderr.log"
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $stdout) | Out-Null

Start-Process -FilePath $Python `
    -ArgumentList @("-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", "$Port", "--no-access-log") `
    -WorkingDirectory $Root `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr | Out-Null

for ($attempt = 0; $attempt -lt 60; $attempt++) {
    Start-Sleep -Milliseconds 250
    try {
        Invoke-RestMethod "$Url/api/health" -TimeoutSec 2 | Out-Null
        Write-Host "Backend ready: $Url/"
        if (-not $NoBrowser) {
            Start-Process "$Url/"
        }
        exit 0
    } catch {
    }
}

throw "Backend did not become ready. Check data\logs\backend-stderr.log."
