@echo off
setlocal
cd /d "%~dp0"
echo.
echo  Sori - one-time setup
echo  ------------------------------------
where py >nul 2>nul
if errorlevel 1 (
    echo.
    echo  Python is not installed yet ^(it's free^).
    echo  Opening the download page now. On the installer's first screen,
    echo  tick "Add python.exe to PATH", finish the install, then
    echo  double-click install.bat again.
    echo.
    start https://www.python.org/downloads/
    pause
    exit /b 1
)
echo.
echo  Installing components... this takes a minute or two, one time only.
echo.
py -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo  The install hit an error - see the messages above.
    pause
    exit /b 1
)
echo.
echo  All set! From now on, just double-click  transcribe.bat
echo  whenever you want a podcast transcript.
echo.
pause
