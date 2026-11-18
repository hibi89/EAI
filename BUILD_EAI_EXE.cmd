@echo off
setlocal
cd /d "%~dp0"
py -3.11 -m PyInstaller --noconfirm --clean --onefile --windowed --name EAI --collect-submodules eai scripts\eai_desktop_entry.py
if errorlevel 1 (
    echo Build failed. Prepare an offline PyInstaller environment first.
    exit /b 1
)
echo Unsigned development binary: dist\EAI.exe
echo Real Windows UI, antivirus, and acceptance tests are still required.
exit /b 0
