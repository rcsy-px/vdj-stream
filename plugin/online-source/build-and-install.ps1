$ErrorActionPreference = "Stop"

$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectFile = Join-Path $projectDir "VdjCompanionSource.vcxproj"
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
$msbuild = & $vswhere -latest -products * `
    -requires Microsoft.Component.MSBuild `
    -find "MSBuild\**\Bin\MSBuild.exe" |
    Select-Object -First 1

if (-not $msbuild) {
    throw "MSBuild with the C++ workload was not found."
}

& $msbuild $projectFile /m /p:Configuration=Release /p:Platform=x64
if ($LASTEXITCODE -ne 0) {
    throw "Online Source plugin build failed with exit code $LASTEXITCODE."
}

$dll = Join-Path $projectDir "build\Release\VdjCompanionSource.dll"
$prebuiltDir = Join-Path $projectDir "prebuilt\x64"
$prebuiltDll = Join-Path $prebuiltDir "VdjCompanionSource.dll"
New-Item -ItemType Directory -Force -Path $prebuiltDir | Out-Null
Copy-Item -Force $dll $prebuiltDll
Write-Host "Updated prebuilt plugin: $prebuiltDll"

$virtualDjSettings = Get-ItemProperty "HKCU:\Software\VirtualDJ" -ErrorAction SilentlyContinue
$virtualDjHome = $virtualDjSettings.HomeFolder
if (-not $virtualDjHome) {
    $virtualDjHome = Join-Path $HOME "Documents\VirtualDJ"
}
$pluginDir = Join-Path $virtualDjHome "Plugins64\OnlineSources"
New-Item -ItemType Directory -Force -Path $pluginDir | Out-Null
Copy-Item -Force $prebuiltDll (Join-Path $pluginDir "VdjCompanionSource.dll")
Write-Host "Installed: $pluginDir\VdjCompanionSource.dll"
