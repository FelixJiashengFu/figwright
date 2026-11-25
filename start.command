#!/bin/bash
# Figwright, started by double-clicking (macOS and Linux).
#
# The first run makes a private virtual environment next to this file and
# installs what Figwright needs; later runs start in a second or two.
# Nothing is installed into your system Python.

set -u
cd "$(dirname "$0")" || exit 1

PY=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
    PY="$candidate"
    break
  fi
done

if [ -z "$PY" ]; then
  echo "Figwright needs Python 3.10 or newer."
  echo "On macOS the easiest way is:  brew install python"
  echo "Or download it from https://www.python.org/downloads/"
  echo
  read -r -p "Press Return to close this window. "
  exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
  echo "First run: setting up (a few minutes, once)..."
  "$PY" -m venv .venv || { echo "Could not create .venv"; read -r -p "Press Return. "; exit 1; }
fi

VENV_PY=".venv/bin/python"
if ! "$VENV_PY" -c 'import figwright' >/dev/null 2>&1; then
  "$VENV_PY" -m pip install --upgrade pip >/dev/null
  if ! "$VENV_PY" -m pip install -e ".[mcp]"; then
    echo
    echo "Installing failed. If you are offline, connect and run this again."
    read -r -p "Press Return to close this window. "
    exit 1
  fi
fi

echo
"$VENV_PY" -m figwright "$@"
status=$?
if [ "$status" -ne 0 ]; then
  echo
  echo "Figwright stopped with code $status."
  read -r -p "Press Return to close this window. "
fi
exit "$status"
