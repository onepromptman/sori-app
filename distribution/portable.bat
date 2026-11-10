@echo off
setlocal
set "SORI_PROFILE=portable"
set "SORI_WHISPER_BACKEND=faster"
echo Sori opens in your browser. Leave this window open while using Sori.
"%~dp0runtime\python.exe" -E -s -B "%~dp0app\app.py" %*
set "SORI_EXIT=%ERRORLEVEL%"
if not "%SORI_EXIT%"=="0" pause
exit /b %SORI_EXIT%
