$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.IO.Compression.FileSystem

function Test-ToolDownload([string]$Path, [string]$Kind) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
    if ((Get-Item -LiteralPath $Path).Length -eq 0) { return $false }
    try {
        if ($Kind -eq ".zip") {
            $archive = [System.IO.Compression.ZipFile]::OpenRead($Path)
            try {
                if ($archive.Entries.Count -eq 0) { return $false }
                foreach ($entry in $archive.Entries) {
                    $stream = $entry.Open()
                    try { $stream.CopyTo([System.IO.Stream]::Null) }
                    finally { $stream.Dispose() }
                }
            } finally { $archive.Dispose() }
        } elseif ($Kind -eq ".exe") {
            # Version probes catch truncated executables, including old partial downloads.
            $process = New-Object System.Diagnostics.Process
            $process.StartInfo.FileName = $Path
            $process.StartInfo.Arguments = if ($Path -match "yt-dlp") { "--ignore-config --version" } elseif ($Path -match "ffmpeg|ffprobe") { "-version" } else { "--version" }
            $process.StartInfo.UseShellExecute = $false
            $process.StartInfo.CreateNoWindow = $true
            $process.StartInfo.RedirectStandardOutput = $true
            $process.StartInfo.RedirectStandardError = $true
            try {
                $process.Start() | Out-Null
                $stdout = $process.StandardOutput.ReadToEndAsync()
                $stderr = $process.StandardError.ReadToEndAsync()
                if (-not $process.WaitForExit(15000)) { $process.Kill(); $process.WaitForExit(); return $false }
                if ($process.ExitCode -ne 0) { return $false }
            } finally { $process.Dispose() }
        } else { return $false }
        return $true
    } catch { return $false }
}

function Invoke-ToolDownload([string]$Uri, [string]$OutFile, [ValidateRange(1, 600)][int]$TimeoutSeconds = 180) {
    $curl = Join-Path $env:SystemRoot "System32\curl.exe"
    if (-not (Test-Path -LiteralPath $curl)) {
        throw "Windows curl.exe is missing. Install current Windows updates and retry."
    }
    # PowerShell's web timeout does not reliably bound stalled response bodies.
    & $curl --fail --location --silent --show-error --connect-timeout 20 --max-time $TimeoutSeconds --output $OutFile $Uri
    if ($LASTEXITCODE -ne 0) { throw "Tool download failed (curl exit $LASTEXITCODE)." }
}

function Download-File([string]$Url, [string]$Destination) {
    $kind = [System.IO.Path]::GetExtension($Destination)
    if (Test-ToolDownload $Destination $kind) {
        Write-Host "Already verified: $Destination"
        return
    }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
    # Preserve the old destination until the complete replacement is validated.
    # Keep .exe as the final suffix so Windows can execute the version probe.
    $partial = "$Destination.part$kind"
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        try {
            Write-Host "Downloading $Url (attempt $attempt/3)"
            Invoke-ToolDownload -Uri $Url -OutFile $partial
            if (-not (Test-ToolDownload $partial $kind)) { throw "Downloaded tool did not pass validation." }
            Move-Item -LiteralPath $partial -Destination $Destination -Force
            return
        } catch {
            if (Test-Path -LiteralPath $partial) { Remove-Item -LiteralPath $partial -Force }
            if ($attempt -eq 3) { throw }
            Start-Sleep -Seconds 1
        }
    }
}
