@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 goto python_launcher
where python >nul 2>nul
if not errorlevel 1 goto python_command
echo Install Python 3.11 or newer from https://www.python.org/downloads/
echo Enable the Python launcher during installation, then open START SORI.bat again.
pause
exit /b 1

:python_launcher
py -3 start_sori.py %*
goto finished

:python_command
python start_sori.py %*

:finished
set "SORI_EXIT=%ERRORLEVEL%"
if not "%SORI_EXIT%"=="0" (
    echo.
    echo Sori could not finish. Read the message above before closing this window.
    pause
)
exit /b %SORI_EXIT%
