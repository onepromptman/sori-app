@echo off
rem Keep the app folder next to this launcher.
if not exist "%~dp0app\start-sori.bat" (
    echo Sori could not find its app folder.
    echo Extract the whole ZIP, then open START SORI.bat from the extracted folder.
    pause
    exit /b 1
)
call "%~dp0app\start-sori.bat" %*
exit /b %ERRORLEVEL%
