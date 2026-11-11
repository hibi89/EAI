@echo off
setlocal DisableDelayedExpansion
rem Synthetic-only offline EAI sample. Never touches real customer files.
if not "%~1"=="" if /i not "%~1"=="--ci" goto usage
set "ROOT=%~dp0"
set "DEST=%~dp0..\EAI-SYNTHETIC-REVIEW"
if exist "%DEST%" goto occupied
set "PYTHON="
set "PY_ARGS="
where python >nul 2>nul
if errorlevel 1 goto try_launcher
python -I -B -c "import sys;sys.exit(0 if sys.version_info >= (3,11) else 2)" >nul 2>nul
if errorlevel 1 goto try_launcher
set "PYTHON=python"
goto ready
:try_launcher
where py >nul 2>nul
if errorlevel 1 goto missing
py -3 -I -B -c "import sys;sys.exit(0 if sys.version_info >= (3,11) else 2)" >nul 2>nul
if errorlevel 1 goto missing
set "PYTHON=py"
set "PY_ARGS=-3"
:ready
rem Verify current extracted package before executing the Python zipapp.
%PYTHON% %PY_ARGS% -I -B "%ROOT%verify_candidate.py" --directory "%ROOT%."
if errorlevel 1 goto invalid
%PYTHON% %PY_ARGS% -I -B "%ROOT%eai.pyz" customer-review --spec "%ROOT%samples\sample_key_coverage_goal.json" --output-dir "%DEST%" --ack-authorized-local
if errorlevel 1 goto audit
%PYTHON% %PY_ARGS% -I -B "%ROOT%eai.pyz" verify-review --output-dir "%DEST%"
if errorlevel 1 goto audit
echo EAI VERIFIED SYNTHETIC REVIEW GENERATED - UNSIGNED
echo REPORT: "%DEST%\review.html"
if /i "%~1"=="--ci" exit /b 0
start "" "%DEST%\review.html"
echo No real customer environment, antivirus, signed delivery, or live model verified.
pause
exit /b 0
:usage
echo Usage: RUN_EAI_REVIEW.cmd [--ci]
goto failure
:occupied
echo Refused: existing output folder preserved.
goto failure
:missing
echo Python 3.11 or newer is required. Nothing installed.
goto failure
:invalid
echo Package inventory/hash validation refused execution.
goto failure
:audit
echo Synthetic source review or integrity verification failed.
goto failure
:failure
if /i "%~1"=="--ci" exit /b 2
pause
exit /b 2
