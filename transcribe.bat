@echo off
setlocal
cd /d "%~dp0"
echo.
echo  Sori
echo  -------------------
echo  Paste a link to the episode and press Enter.
echo.
echo  Works with either:
echo    - a YouTube link ^(fastest - uses the video's captions^)
echo    - a direct MP3 link ^(transcribed on your computer, a 20-minute
echo      episode takes a minute or two^)
echo.
set /p "URL=  Link: "
if "%URL%"=="" (
    echo.
    echo  No link entered - nothing to do.
    pause
    exit /b 1
)
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmm"') do set TS=%%i
set "OUT=%USERPROFILE%\Desktop\transcript-%TS%.txt"
echo.
echo %URL% | findstr /i "youtube.com youtu.be" >nul
if not errorlevel 1 (
    echo  Grabbing the YouTube captions...
    py transcribe.py youtube "%URL%" --out "%OUT%"
) else (
    echo  Downloading and transcribing on your computer - this can take a
    echo  few minutes for a long episode. Leave this window open.
    echo.
    py transcribe.py audio "%URL%" --out "%OUT%"
)
if exist "%OUT%" (
    echo.
    echo  Done! The transcript is on your Desktop:
    echo    %OUT%
    start notepad "%OUT%"
) else (
    echo.
    echo  Something went wrong - the messages above say why.
    echo  Common causes: the link isn't a direct MP3, or the episode
    echo  has no captions on YouTube. Try the other kind of link.
)
echo.
pause
