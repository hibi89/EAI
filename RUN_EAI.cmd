@echo off
setlocal
cd /d "%~dp0"
echo [EAI] Local CPU-first independent engine
where py >nul 2>nul
if errorlevel 1 goto python_fallback
py -3.11 -c "import sys; assert sys.version_info >= (3,11)" >nul 2>nul
if errorlevel 1 goto python_fallback
py -3.11 -m eai chat
goto done
:python_fallback
python -m eai chat
:done
if errorlevel 1 (
  echo.
  echo [EAI] Python 3.11 or newer is required. Check your install or run python -m eai health
  pause
)
endlocal
