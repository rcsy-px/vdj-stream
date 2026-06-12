$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Tools = Join-Path $Root "tools"
$Cache = Join-Path $Root ".cache\downloads"

@(
    $Tools, $Cache, (Join-Path $Root "data\logs"),
    (Join-Path $Root "data\chromium-profile"),
    (Join-Path $Tools "uv"), (Join-Path $Tools "yt-dlp"),
    (Join-Path $Tools "ffmpeg"), (Join-Path $Tools "playwright-browsers")
) | ForEach-Object { New-Item -ItemType Directory -Force $_ | Out-Null }

function Download-File($Url, $Destination) {
    if (Test-Path $Destination) {
        Write-Host "Already present: $Destination"
        return
    }
    Write-Host "Downloading $Url"
    Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $Destination
}

$UvZip = Join-Path $Cache "uv-x86_64-pc-windows-msvc.zip"
Download-File "https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip" $UvZip
if (-not (Test-Path (Join-Path $Tools "uv\uv.exe"))) {
    Expand-Archive -Force $UvZip (Join-Path $Tools "uv")
}

Download-File "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe" (Join-Path $Tools "yt-dlp\yt-dlp.exe")

$FfmpegZip = Join-Path $Cache "ffmpeg-release-essentials.zip"
Download-File "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip" $FfmpegZip
if (-not (Test-Path (Join-Path $Tools "ffmpeg\bin\ffmpeg.exe"))) {
    $Extract = Join-Path $Cache "ffmpeg-extract"
    New-Item -ItemType Directory -Force $Extract | Out-Null
    Expand-Archive -Force $FfmpegZip $Extract
    $Bin = Get-ChildItem $Extract -Directory | Select-Object -First 1 | ForEach-Object { Join-Path $_.FullName "bin" }
    New-Item -ItemType Directory -Force (Join-Path $Tools "ffmpeg\bin") | Out-Null
    Copy-Item (Join-Path $Bin "*") (Join-Path $Tools "ffmpeg\bin") -Force
}

Write-Host ""
Write-Host "Portable tools are ready."
