param(
    [switch]$BuildOnly
)

$ErrorActionPreference = "Stop"

$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent (Split-Path -Parent $projectDir)
$pluginVersion = (Get-Content (Join-Path $projectRoot "VERSION") -Raw).Trim()
$projectFile = Join-Path $projectDir "VdjCompanionSource.vcxproj"
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
$msbuild = & $vswhere -latest -products * `
    -requires Microsoft.Component.MSBuild `
    -find "MSBuild\**\Bin\MSBuild.exe" |
    Select-Object -First 1

if (-not $msbuild) {
    throw "MSBuild with the C++ workload was not found."
}

& $msbuild $projectFile /m /p:Configuration=Release /p:Platform=x64 /p:PluginVersion=$pluginVersion
if ($LASTEXITCODE -ne 0) {
    throw "Online Source plugin build failed with exit code $LASTEXITCODE."
}

$pluginFileName = "VDJ Companion Source.dll"
$legacyPluginFileName = "VdjCompanionSource.dll"
$dll = Join-Path $projectDir "build\Release\$pluginFileName"
$prebuiltDir = Join-Path $projectDir "prebuilt\x64"
$prebuiltDll = Join-Path $prebuiltDir $pluginFileName
New-Item -ItemType Directory -Force -Path $prebuiltDir | Out-Null
Copy-Item -Force $dll $prebuiltDll
$legacyPrebuiltDll = Join-Path $prebuiltDir $legacyPluginFileName
if (Test-Path $legacyPrebuiltDll) {
    Remove-Item -Force -LiteralPath $legacyPrebuiltDll
}
Write-Host "Updated prebuilt plugin: $prebuiltDll"

if ($BuildOnly) {
    exit 0
}

$virtualDjSettings = Get-ItemProperty "HKCU:\Software\VirtualDJ" -ErrorAction SilentlyContinue
$virtualDjHome = $virtualDjSettings.HomeFolder
if (-not $virtualDjHome) {
    $virtualDjHome = Join-Path $HOME "Documents\VirtualDJ"
}
$pluginDir = Join-Path $virtualDjHome "Plugins64\OnlineSources"
New-Item -ItemType Directory -Force -Path $pluginDir | Out-Null
$installedPlugin = Join-Path $pluginDir $pluginFileName
Copy-Item -Force $prebuiltDll $installedPlugin
$legacyInstalledPlugin = Join-Path $pluginDir $legacyPluginFileName
if (Test-Path $legacyInstalledPlugin) {
    Remove-Item -Force -LiteralPath $legacyInstalledPlugin
}
Write-Host "Installed: $installedPlugin"
