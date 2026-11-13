#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if ! bash scripts/macos/setup.sh; then
  echo "Setup failed. Read the message above and docs/MACOS.md."
  read -r -p "Press Return to close. " _
  exit 1
fi
exec .venv/bin/python scripts/macos/runtime.py start
