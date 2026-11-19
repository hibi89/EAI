@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
echo EAI V3.2 development-only unsigned Windows EXE. Offline build; no remote model.
set "PYTHON_EXE=py -3.11"
if defined VIRTUAL_ENV set PYTHON_EXE="%VIRTUAL_ENV%\Scripts\python.exe"
%PYTHON_EXE% -m PyInstaller --version >nul 2>nul
if errorlevel 1 (
    echo HOLD: PyInstaller must already be installed locally. No network install attempted.
    exit /b 1
)
%PYTHON_EXE% -m PyInstaller --noconfirm --clean scripts\eai_desktop.spec
if errorlevel 1 (
    echo Build failed. Original files and deployment remain unchanged.
    exit /b 1
)
if not exist "dist\EAI.exe" exit /b 2
set "EAI_REPORT=dist\EAI-v32-selfcheck-%RANDOM%-%RANDOM%.json"
if exist "%EAI_REPORT%" (
    echo HOLD: candidate report already exists, not overwritten.
    exit /b 2
)
"dist\EAI.exe" --self-check --report "%CD%\%EAI_REPORT%"
if errorlevel 1 (
    echo HOLD: Windows EXE self-check failed; no release proof.
    exit /b 2
)
if not exist "%EAI_REPORT%" (
    echo HOLD: self-check did not create a report.
    exit /b 2
)
%PYTHON_EXE% -c "import json,sys;p=json.load(open(sys.argv[1],encoding='utf-8'));assert p['status']=='PASS_UNSIGNED_BUNDLE_IMPORTS' and p['native_gui_e2e']=='NOT_RUN'" "%EAI_REPORT%"
if errorlevel 1 exit /b 2
certutil -hashfile "dist\EAI.exe" SHA256
if errorlevel 1 exit /b 2
echo Self-check report: %EAI_REPORT%
echo Native Windows GUI/IME/real-user validation remains P2 NOT_RUN.
exit /b 0
