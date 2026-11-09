@echo off
setlocal
cd /d "%~dp0"
echo [EAI] Offline diagnostics - no model or network call
where py >nul 2>nul
if errorlevel 1 goto fallback
py -3.11 -c "import sys; assert sys.version_info >= (3,11)" >nul 2>nul
if errorlevel 1 goto fallback
py -3.11 -m eai doctor --json
set "EAI_RC=%ERRORLEVEL%"
goto end
:fallback
python -m eai doctor --json
set "EAI_RC=%ERRORLEVEL%"
:end
if not "%EAI_RC%"=="0" (
 echo [EAI] Diagnostic incomplete. Review errors above.
 pause
)
exit /b %EAI_RC%
