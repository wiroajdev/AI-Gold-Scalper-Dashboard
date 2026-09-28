@echo off
title AI Gold Scalper Web Dashboard
echo ======================================================
echo    AI Gold Scalper -- Local Live Web Dashboard
echo ======================================================
echo Starting Flask Server...
echo Staging Directory: %~dp0exportedpricedata\
echo.

cd /d "%~dp0"

:: Start Flask server in background
start /B "" python app.py

:: Wait for server to be ready before opening browser (max 30s)
echo Waiting for server to be ready...
powershell -Command "$url='http://127.0.0.1:5000'; $maxTries=30; $i=0; while($i -lt $maxTries){ try{ $r=[System.Net.WebRequest]::Create($url); $r.Timeout=1000; $resp=$r.GetResponse(); $resp.Close(); Write-Host 'Server is ready!'; break } catch{ $i++; Start-Sleep -Seconds 1 } }; if($i -ge $maxTries){ Write-Host 'Timeout: server did not respond in 30s' }"

:: Open browser only after server is up
start "" http://127.0.0.1:5000

echo Dashboard opened in browser. Press Ctrl+C to stop the server.
pause
