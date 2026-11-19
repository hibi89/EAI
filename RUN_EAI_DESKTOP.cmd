@echo off
setlocal
cd /d "%~dp0"
rem EAI V3.2: offline preview only. Pure Player does not execute external actions.
if exist "%~dp0dist\EAI.exe" (
    start "" "%~dp0dist\EAI.exe"
    exit /b 0
)
py -3.11 -m eai.desktop_app
if errorlevel 1 (
    echo EAI V3.2 Desktop could not start. Python 3.11 and Tkinter are required.
    echo No online install or fallback is attempted.
    exit /b 1
)
exit /b 0
