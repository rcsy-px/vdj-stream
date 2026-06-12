param(
    [int]$Port = 8765
)

$ErrorActionPreference = "Stop"
$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -First 1

if (-not $listener) {
    Write-Host "Port $Port is free."
    exit 0
}

$processId = $listener.OwningProcess
$processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $processId"
$commandLine = $processInfo.CommandLine

if ($commandLine -notmatch "uvicorn" -or $commandLine -notmatch "backend\.app\.main:app") {
    Write-Error "Port $Port is used by PID $processId, but it is not this project's backend. Stop it manually."
    exit 1
}

Write-Host "Stopping existing backend on port $Port (PID $processId)..."
Stop-Process -Id $processId

for ($attempt = 0; $attempt -lt 20; $attempt++) {
    Start-Sleep -Milliseconds 100
    if (-not (Get-Process -Id $processId -ErrorAction SilentlyContinue)) {
        Write-Host "Existing backend stopped."
        exit 0
    }
}

Write-Host "Backend did not stop gracefully; forcing shutdown."
Stop-Process -Id $processId -Force
