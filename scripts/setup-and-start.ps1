param(
    [switch]$SetupOnly
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Tools = Join-Path $Root "tools"
$Uv = Join-Path $Tools "uv\uv.exe"
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$BrowserRoot = Join-Path $Tools "playwright-browsers"
$PluginRoot = Join-Path $Root "plugin\online-source"
$PluginFileName = "VDJ Companion Source.dll"
$LegacyPluginFileName = "VdjCompanionSource.dll"
$PrebuiltPlugin = Join-Path $PluginRoot "prebuilt\x64\$PluginFileName"

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Get-VirtualDjHome {
    $settings = Get-ItemProperty "HKCU:\Software\VirtualDJ" -ErrorAction SilentlyContinue
    if ($settings.HomeFolder) {
        return $settings.HomeFolder
    }
    return Join-Path $HOME "Documents\VirtualDJ"
}

Set-Location $Root

Write-Step "Checking portable tools"
& (Join-Path $PSScriptRoot "bootstrap-tools.ps1")

$env:PATH = "$(Join-Path $Tools 'uv');$(Join-Path $Tools 'yt-dlp');$(Join-Path $Tools 'ffmpeg\bin');$env:PATH"
$env:UV_CACHE_DIR = Join-Path $Root ".cache\uv"
$env:UV_PYTHON_INSTALL_DIR = Join-Path $Tools "python"
$env:PLAYWRIGHT_BROWSERS_PATH = $BrowserRoot

Write-Step "Checking Python environment"
if (-not (Test-Path $VenvPython)) {
    & $Uv python install 3.12
    if ($LASTEXITCODE -ne 0) { throw "Python installation failed." }
    & $Uv venv
    if ($LASTEXITCODE -ne 0) { throw "Virtual environment creation failed." }
}
& $Uv sync
if ($LASTEXITCODE -ne 0) { throw "Python dependency sync failed." }

$chromiumInstalled = Get-ChildItem $BrowserRoot -Directory -Filter "chromium-*" -ErrorAction SilentlyContinue
if (-not $chromiumInstalled) {
    Write-Step "Installing Playwright Chromium"
    & $Uv run python -m playwright install chromium
    if ($LASTEXITCODE -ne 0) { throw "Playwright Chromium installation failed." }
} else {
    Write-Host "Already present: Playwright Chromium"
}

$virtualDjHome = Get-VirtualDjHome
$installedPlugin = Join-Path $virtualDjHome "Plugins64\OnlineSources\$PluginFileName"
$legacyInstalledPlugin = Join-Path $virtualDjHome "Plugins64\OnlineSources\$LegacyPluginFileName"
if (-not (Test-Path $PrebuiltPlugin)) {
    throw "Prebuilt plugin is missing: $PrebuiltPlugin"
}

$installRequired = -not (Test-Path $installedPlugin)
if (-not $installRequired) {
    $installRequired = (Get-FileHash $PrebuiltPlugin).Hash -ne (Get-FileHash $installedPlugin).Hash
}
if ($installRequired) {
    Write-Step "Installing VirtualDJ plugin"
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $installedPlugin) | Out-Null
    Copy-Item -Force $PrebuiltPlugin $installedPlugin
    Write-Host "Installed: $installedPlugin"
} else {
    Write-Host "Already up to date: $installedPlugin"
}
if (Test-Path $legacyInstalledPlugin) {
    Remove-Item -Force -LiteralPath $legacyInstalledPlugin
    Write-Host "Removed legacy plugin: $legacyInstalledPlugin"
}

if ($SetupOnly) {
    Write-Step "Setup complete"
} else {
    Write-Step "Starting backend"
    & (Join-Path $PSScriptRoot "run-backend.bat")
}
