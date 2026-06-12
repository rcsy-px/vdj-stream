@echo off
setlocal
echo Checking health...
powershell -NoProfile -Command "$r=Invoke-RestMethod http://127.0.0.1:8765/api/health; $r | ConvertTo-Json -Depth 4"
if errorlevel 1 exit /b 1
echo.
echo Online Source API: http://127.0.0.1:8765/api/vdj/source/search?q=test
