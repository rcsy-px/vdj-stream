#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [ -x .venv/bin/python ] && .venv/bin/python scripts/macos/runtime.py status >/dev/null 2>&1; then
  exec .venv/bin/python scripts/macos/runtime.py start
fi
if ! bash scripts/macos/setup.sh; then
  echo "Setup failed. Read the message above and docs/MACOS.md."
  read -r -p "Press Return to close. " _
  exit 1
fi
exec .venv/bin/python scripts/macos/runtime.py start
