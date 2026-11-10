@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
    py -3 start_sori.py
    if errorlevel 1 pause
    exit /b
)
where python >nul 2>nul
if not errorlevel 1 (
    python start_sori.py
    if errorlevel 1 pause
    exit /b
)
echo Install Python 3.11 or newer from https://www.python.org/downloads/
echo Enable the Python launcher during installation, then open start-sori.bat again.
pause
exit /b 1
