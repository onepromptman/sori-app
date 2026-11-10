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
if not defined URL (
    echo.
    echo  No link entered - nothing to do.
    pause
    exit /b 1
)
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmm"') do set TS=%%i
set "OUT=%USERPROFILE%\Desktop\transcript-%TS%.txt"
echo.
echo  Getting the transcript. Audio can take a few minutes; leave this window open.
rem Read the pasted value from the environment in Python so CMD never parses it
rem as command syntax. The Python CLI receives it as one argument.
call py -c "import os,sys,transcribe; u=os.environ['URL']; sys.argv=['transcribe.py', 'youtube' if 'youtube.com' in u.lower() or 'youtu.be' in u.lower() else 'audio', u, '--out', os.environ['OUT']]; transcribe.main()"
if errorlevel 1 goto failed
if not exist "%OUT%" goto failed
echo.
echo  Done! The transcript is on your Desktop:
echo    %OUT%
start notepad "%OUT%"
goto done
:failed
echo.
echo  Something went wrong - the messages above say why.
echo  Common causes: the link isn't a direct MP3, or the episode
echo  has no captions on YouTube. Try the other kind of link.
:done
echo.
pause
