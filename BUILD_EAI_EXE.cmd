@echo off
setlocal
cd /d "%~dp0"
if defined VIRTUAL_ENV (
    "%VIRTUAL_ENV%\Scripts\python.exe" -m PyInstaller --noconfirm --clean scripts\eai_desktop.spec
) else (
    py -3.11 -m PyInstaller --noconfirm --clean scripts\eai_desktop.spec
)
if errorlevel 1 (
    echo Build failed. Prepare an offline PyInstaller environment first.
    exit /b 1
)
echo Unsigned development binary: dist\EAI.exe
echo SHA256:
certutil -hashfile dist\EAI.exe SHA256
exit /b 0
