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

. (Join-Path $PSScriptRoot "download-tools.ps1")

$UvZip = Join-Path $Cache "uv-x86_64-pc-windows-msvc.zip"
if (-not (Test-ToolDownload (Join-Path $Tools "uv\uv.exe") ".exe")) {
    Download-File "https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip" $UvZip
    Expand-Archive -Force $UvZip (Join-Path $Tools "uv")
}

Download-File "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe" (Join-Path $Tools "yt-dlp\yt-dlp.exe")
Write-Host "yt-dlp updates can be checked and installed from the local control panel."

$FfmpegZip = Join-Path $Cache "ffmpeg-release-essentials.zip"
if (-not (Test-ToolDownload (Join-Path $Tools "ffmpeg\bin\ffmpeg.exe") ".exe") -or
    -not (Test-ToolDownload (Join-Path $Tools "ffmpeg\bin\ffprobe.exe") ".exe")) {
    $ffmpegUrl = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    try {
        # The build author's GitHub mirror avoids stalled transfers on the main host.
        $releaseJson = & (Join-Path $env:SystemRoot "System32\curl.exe") --fail --location --silent --show-error --max-time 20 "https://api.github.com/repos/GyanD/codexffmpeg/releases/latest"
        if ($LASTEXITCODE -ne 0) { throw "FFmpeg mirror lookup failed." }
        $release = $releaseJson | ConvertFrom-Json
        $asset = $release.assets | Where-Object { $_.name -match '^ffmpeg-[0-9.]+-essentials_build\.zip$' } | Select-Object -First 1
        if ($asset.browser_download_url -notlike 'https://github.com/GyanD/codexffmpeg/releases/download/*') {
            throw "FFmpeg mirror did not provide an expected release ZIP."
        }
        $ffmpegUrl = $asset.browser_download_url
    } catch { Write-Warning "Mirror unavailable; using the build author's main download server." }
    Download-File $ffmpegUrl $FfmpegZip
    $Extract = Join-Path $Cache "ffmpeg-extract"
    New-Item -ItemType Directory -Force $Extract | Out-Null
    Expand-Archive -Force $FfmpegZip $Extract
    $Bin = Get-ChildItem $Extract -Directory | Select-Object -First 1 | ForEach-Object { Join-Path $_.FullName "bin" }
    New-Item -ItemType Directory -Force (Join-Path $Tools "ffmpeg\bin") | Out-Null
    Copy-Item (Join-Path $Bin "*") (Join-Path $Tools "ffmpeg\bin") -Force
}

Write-Host ""
Write-Host "Portable tools are ready."
