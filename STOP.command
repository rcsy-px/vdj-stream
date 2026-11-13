#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then echo "Companion has not been set up yet."; exit 0; fi
exec .venv/bin/python scripts/macos/runtime.py stop
