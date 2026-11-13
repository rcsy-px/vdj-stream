#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [ -f data/macos-update-active.json ] || [ -f data/macos-update-pending.json ]; then
  for candidate in .venv/bin/python tools/python/*/bin/python3.12; do
    if [ -x "$candidate" ]; then exec "$candidate" scripts/macos/runtime.py start; fi
  done
  echo "Update recovery needs the managed Python. Keep the .cache/app-update-* backup and report this error."
  exit 1
fi
if [ -x .venv/bin/python ] && .venv/bin/python scripts/macos/runtime.py status >/dev/null 2>&1; then
  exec .venv/bin/python scripts/macos/runtime.py start
fi
if ! bash scripts/macos/setup.sh; then
  echo "Setup failed. Read the message above and docs/MACOS.md."
  read -r -p "Press Return to close. " _
  exit 1
fi
exec .venv/bin/python scripts/macos/runtime.py start
