@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0dist\EAI.exe" (
    start "" "%~dp0dist\EAI.exe"
    exit /b 0
)
py -3.11 -m eai.desktop_app
if errorlevel 1 (
    echo EAI Desktop could not start. Python 3.11 plus Tkinter is required.
    exit /b 1
)
exit /b 0
