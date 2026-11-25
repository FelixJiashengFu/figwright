@echo off
rem Figwright, started by double-clicking (Windows).
rem
rem The first run makes a private virtual environment next to this file and
rem installs what Figwright needs; later runs start in a second or two.
rem Nothing is installed into your system Python.

setlocal
cd /d "%~dp0"

set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
  where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo Figwright needs Python 3.10 or newer.
  echo Get it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
  echo.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo First run: setting up ^(a few minutes, once^)...
  %PY% -m venv .venv
  if errorlevel 1 (
    echo Could not create .venv
    pause
    exit /b 1
  )
)

".venv\Scripts\python.exe" -c "import figwright" >nul 2>&1
if errorlevel 1 (
  ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
  ".venv\Scripts\python.exe" -m pip install -e ".[mcp]"
  if errorlevel 1 (
    echo.
    echo Installing failed. If you are offline, connect and run this again.
    pause
    exit /b 1
  )
)

echo.
".venv\Scripts\python.exe" -m figwright %*
if errorlevel 1 (
  echo.
  echo Figwright stopped with an error.
  pause
)
endlocal
