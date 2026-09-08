@echo off
setlocal
cd /d "%~dp0"
echo.
echo  Sori - daily automatic check
echo  ---------------------------
echo.
echo  This sets up a daily 9:03am job that checks your shows and
echo  transcribes new episodes for any show you switched to "Auto".
echo  It runs quietly in the background - no window appears.
echo.

set "EXE=%~dp0Sori.exe"
if not exist "%EXE%" (
    echo  Could not find "Sori.exe" next to this file.
    echo  Keep setup-auto-sweep.bat inside the unzipped Sori folder.
    echo.
    pause
    exit /b 1
)

schtasks /create /tn "Sori Daily Sweep" /tr "\"%EXE%\" --sweep" /sc daily /st 09:03 /f
if errorlevel 1 (
    echo.
    echo  Could not create the scheduled task. If Windows refused it, try
    echo  right-clicking this file and choosing "Run as administrator".
    echo.
    pause
    exit /b 1
)

echo.
echo  Done. Every day at 9:03am your shows get checked.
echo  A record of each run is written to:
echo    %USERPROFILE%\Sori\sweep.log
echo.
echo  To stop it later, run this command in a Command Prompt:
echo    schtasks /delete /tn "Sori Daily Sweep" /f
echo.
pause
