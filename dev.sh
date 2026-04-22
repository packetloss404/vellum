#!/usr/bin/env bash
# Vellum dev runner — starts backend (uvicorn on :8731) and frontend (vite on
# :5173, proxies /api/*) together in one shell. Ctrl-C kills both.
#
# Tested on Windows git-bash. On Linux/macOS replace `.venv/Scripts/python`
# with `.venv/bin/python` (or `python3` if you don't use a local venv).
# For PowerShell / cmd.exe on Windows, the python path would be
# `.venv\Scripts\python.exe` with backslashes — this script assumes bash.

set -e

# Kill any still-running children on exit / Ctrl-C / kill.
trap 'kill $(jobs -p) 2>/dev/null' EXIT INT TERM

# Detect the right python binary for the active OS/venv layout. Paths are
# relative to the backend/ directory (where we cd below before launching).
if [ -x "backend/.venv/Scripts/python" ]; then
  PYTHON=".venv/Scripts/python"       # Windows venv (git-bash)
elif [ -x "backend/.venv/Scripts/python.exe" ]; then
  PYTHON=".venv/Scripts/python.exe"   # Windows venv (explicit .exe)
elif [ -x "backend/.venv/bin/python" ]; then
  PYTHON=".venv/bin/python"           # POSIX venv
else
  PYTHON="python"                     # fallback — hope it's on PATH
fi

(
  cd backend && \
    "$PYTHON" -m uvicorn vellum.main:app \
      --host 127.0.0.1 --port 8731 --log-level info
) &
BACKEND_PID=$!

(
  cd frontend && npm run dev
) &
FRONTEND_PID=$!

echo "Vellum dev: backend=$BACKEND_PID frontend=$FRONTEND_PID"
echo "Open http://localhost:5173  (demo UI: http://localhost:5173/demo)"

wait
