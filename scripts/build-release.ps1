param(
    [ValidatePattern("^\d+\.\d+\.\d+([.-][A-Za-z0-9.-]+)?$")]
    [string]$Version = "0.1.0"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Dist = Join-Path $Root "dist"
$Stage = Join-Path $Dist "vdj-companion-$Version"
$Archive = Join-Path $Dist "vdj-companion-$Version-windows-x64.zip"
$Checksum = "$Archive.sha256"

$resolvedRoot = [System.IO.Path]::GetFullPath($Root)
$resolvedDist = [System.IO.Path]::GetFullPath($Dist)
if (-not $resolvedDist.StartsWith($resolvedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to prepare a release outside the project directory."
}

if (Test-Path $Stage) {
    Remove-Item -Recurse -Force -LiteralPath $Stage
}
if (Test-Path $Archive) {
    Remove-Item -Force -LiteralPath $Archive
}
if (Test-Path $Checksum) {
    Remove-Item -Force -LiteralPath $Checksum
}
New-Item -ItemType Directory -Force -Path $Stage | Out-Null

$files = @(
    "START.bat",
    "README.md",
    "LICENSE",
    "CHANGELOG.md",
    "SECURITY.md",
    "pyproject.toml",
    "uv.lock"
)
$scripts = @(
    "bootstrap-tools.ps1",
    "run-backend.bat",
    "setup-and-start.ps1",
    "stop-backend.ps1"
)

foreach ($file in $files) {
    Copy-Item -Force (Join-Path $Root $file) (Join-Path $Stage $file)
}

function Copy-CleanTree([string]$SourceRelative, [string]$DestinationRelative) {
    $source = Join-Path $Root $SourceRelative
    $destination = Join-Path $Stage $DestinationRelative
    Get-ChildItem -Path $source -Recurse -File |
        Where-Object {
            $_.FullName -notmatch "\\__pycache__\\" -and
            $_.Extension -notin @(".pyc", ".log", ".sqlite", ".sqlite3")
        } |
        ForEach-Object {
            $relative = $_.FullName.Substring($source.Length).TrimStart("\")
            $target = Join-Path $destination $relative
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
            Copy-Item -Force $_.FullName $target
        }
}

Copy-CleanTree "backend" "backend"
Copy-CleanTree "docs" "docs"
New-Item -ItemType Directory -Force -Path (Join-Path $Stage "plugin\online-source") | Out-Null
Copy-Item -Recurse -Force `
    (Join-Path $Root "plugin\online-source\prebuilt") `
    (Join-Path $Stage "plugin\online-source\prebuilt")
New-Item -ItemType Directory -Force -Path (Join-Path $Stage "scripts") | Out-Null
foreach ($script in $scripts) {
    Copy-Item -Force (Join-Path $Root "scripts\$script") (Join-Path $Stage "scripts\$script")
}

Compress-Archive -Path (Join-Path $Stage "*") -DestinationPath $Archive
$hash = (Get-FileHash -Algorithm SHA256 $Archive).Hash.ToLowerInvariant()
Set-Content -Encoding ascii -Path $Checksum -Value "$hash  $(Split-Path -Leaf $Archive)"
Write-Host "Release ready: $Archive"
Write-Host "Checksum ready: $Checksum"
