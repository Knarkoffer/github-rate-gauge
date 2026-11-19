@echo off
setlocal EnableExtensions DisableDelayedExpansion

rem Double-click to launch hidden. Use --diagnose for visible startup.
if /i "%~1"=="--diagnose" goto :launch
if /i "%~1"=="--background" goto :launch
start "" wscript.exe "%~dp0Launch GitHub Rate Gauge.vbs"
exit /b 0

:launch
pushd "%~dp0"
if errorlevel 1 (
    set "GRG_ERROR_MESSAGE=The gauge project folder could not be opened."
    goto :error
)
set "GRG_PUSHED=1"
set "GRG_PYTHON=.venv\Scripts\python.exe"

if exist "%GRG_PYTHON%" goto :validate
echo Preparing GitHub Rate Gauge for its first run...
call :find_python
if not defined GRG_PYTHON_COMMAND (
    set "GRG_ERROR_MESSAGE=Python 3.12 or later with Tkinter was not found. Install it from python.org, then start the gauge again."
    goto :error
)
%GRG_PYTHON_COMMAND% -m venv --without-pip .venv
if errorlevel 1 (
    set "GRG_ERROR_MESSAGE=Python could not create the gauge's .venv folder. Run this CMD file with --diagnose for details."
    goto :error
)

:validate
"%GRG_PYTHON%" -c "import sys, tkinter; raise SystemExit(sys.version_info < (3, 12))"
if errorlevel 1 (
    set "GRG_ERROR_MESSAGE=The .venv needs Python 3.12 or later with Tkinter. Recreate it after installing a supported Python."
    goto :error
)
if not exist "VERSION" (
    set "GRG_ERROR_MESSAGE=The VERSION file is missing. Keep the complete project and both launcher files together."
    goto :error
)

"%GRG_PYTHON%" -c "import PIL, pystray; from importlib.metadata import version; version('github-rate-gauge')" >nul 2>&1
if not errorlevel 1 goto :run
echo Installing GitHub Rate Gauge and its dependencies...
"%GRG_PYTHON%" -m ensurepip
if errorlevel 1 (
    set "GRG_ERROR_MESSAGE=The gauge could not prepare pip. Run this CMD file with --diagnose for details."
    goto :error
)
"%GRG_PYTHON%" -m pip install --index-url https://pypi.org/simple .
if errorlevel 1 (
    set "GRG_ERROR_MESSAGE=The gauge could not install the project and its dependencies. Run this CMD file with --diagnose for details."
    goto :error
)

:run
rem Use the same WSL GitHub CLI login as the original gauge.
rem GRG_WSL_DISTRO may select a distribution; an empty value uses the default.
"%GRG_PYTHON%" rate_gauge.py --wsl-distro "%GRG_WSL_DISTRO%"
if errorlevel 1 (
    set "GRG_ERROR_MESSAGE=GitHub Rate Gauge stopped unexpectedly. Run this CMD file with --diagnose for details."
    goto :error
)
popd
endlocal
exit /b 0

:find_python
set "GRG_PYTHON_COMMAND="
py -3.12 -c "import sys, tkinter; raise SystemExit(sys.version_info < (3, 12))" >nul 2>&1
if not errorlevel 1 set "GRG_PYTHON_COMMAND=py -3.12"
if defined GRG_PYTHON_COMMAND exit /b 0
py -3 -c "import sys, tkinter; raise SystemExit(sys.version_info < (3, 12))" >nul 2>&1
if not errorlevel 1 set "GRG_PYTHON_COMMAND=py -3"
if defined GRG_PYTHON_COMMAND exit /b 0
python -c "import sys, tkinter; raise SystemExit(sys.version_info < (3, 12))" >nul 2>&1
if not errorlevel 1 set "GRG_PYTHON_COMMAND=python"
exit /b 0

:error
echo %GRG_ERROR_MESSAGE%
if defined GRG_ERROR_FILE > "%GRG_ERROR_FILE%" echo %GRG_ERROR_MESSAGE%
if defined GRG_PUSHED popd
endlocal
exit /b 1
