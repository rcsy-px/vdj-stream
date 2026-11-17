$marker = Join-Path $Root 'data\windows-update-active.json'
if (Test-Path -LiteralPath $marker) {
    $request = Get-Content -LiteralPath $marker -Raw | ConvertFrom-Json
    if ($request.job -notmatch '^app-update-[A-Za-z0-9_-]+$') { throw 'Invalid update recovery path.' }
    $helper = Join-Path $Root ".cache\$($request.job)\apply_update.py"
    $basePython = Get-ChildItem (Join-Path $Root 'tools\python\*\python.exe') | Select-Object -First 1
    if (-not $basePython -or -not (Test-Path -LiteralPath $helper)) { throw 'Update recovery files are missing.' }
    & $basePython.FullName $helper $Root --recover
    if ($LASTEXITCODE -ne 0) { throw 'Update is running or needs recovery. Check the update log before restarting.' }
}
