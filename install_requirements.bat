@echo off
title Install AI Gold Scalper Dependencies
echo ======================================================
echo    Installing Python Dependencies for Web Dashboard
echo ======================================================
echo.

cd /d "%~dp0"
python -m pip install --upgrade pip
pip install -r requirements.txt

echo.
echo ======================================================
echo    Installation Complete! You can now run:
echo    start_dashboard.bat
echo ======================================================
pause
