#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/../.."
# Log before Python or any downloaded tools are available. A pipeline wrapper
# waits for tee and preserves the installer's status (including early failures).
if [ "${1:-}" != --logged-setup ]; then
  mkdir -p data/logs
  setup_log="$PWD/data/logs/setup-$(date -u +%Y%m%d-%H%M%S)-$$.log"
  (umask 077; set -o noclobber; : > "$setup_log")
  echo "Setup log: $setup_log"
  set +e
  bash "$PWD/scripts/macos/setup.sh" --logged-setup "$@" 2>&1 | tee "$setup_log"
  results=("${PIPESTATUS[@]}")
  result=${results[0]}
  if [ "${results[1]}" -ne 0 ]; then
    echo "Could not save the complete setup log: $setup_log" >&2
    [ "$result" -ne 0 ] || result=1
  fi
  if [ "$result" -eq 0 ]; then
    echo "Setup succeeded. Log: $setup_log" | tee -a "$setup_log"
  else
    echo "Setup failed (exit $result). For help, share this log after reviewing it: $setup_log" | tee -a "$setup_log"
  fi
  exit "$result"
fi
shift
echo "VDJ Companion setup — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "Mac version: $(cat MACOS_VERSION)"
if [ "$(uname -s)" != Darwin ]; then echo "This launcher requires macOS." >&2; exit 1; fi
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
export UV_CACHE_DIR="$PWD/.cache/uv"
export UV_PYTHON_INSTALL_DIR="$PWD/tools/python"
export UV_PYTHON_PREFERENCE=only-managed
export PLAYWRIGHT_BROWSERS_PATH="$PWD/tools/playwright-browsers"
mkdir -p tools/uv tools/yt-dlp tools/ffmpeg/bin .cache
# Atomic mkdir works with the system Bash, without a preinstalled Python.
if ! mkdir .cache/macos-setup.lock 2>/dev/null; then
  echo "Setup is already running. If it was interrupted, remove .cache/macos-setup.lock and retry." >&2
  exit 1
fi
tmp=$(mktemp -d "$PWD/.cache/setup.XXXXXX")
trap 'rm -rf "$tmp"; rmdir .cache/macos-setup.lock' EXIT
case "$(uname -m)" in
  arm64) target=aarch64-apple-darwin ;;
  x86_64) target=x86_64-apple-darwin ;;
  *) echo "Unsupported CPU architecture." >&2; exit 1 ;;
esac
download() { curl --fail --location --retry 3 --connect-timeout 15 --max-time 300 "$1" -o "$2"; }
if [ ! -x tools/uv/uv ]; then
  version=0.11.20
  base="https://github.com/astral-sh/uv/releases/download/$version"
  name="uv-$target.tar.gz"
  download "$base/$name" "$tmp/$name"
  download "$base/$name.sha256" "$tmp/uv.sha256"
  expected=$(awk '{print $1}' "$tmp/uv.sha256")
  actual=$(shasum -a 256 "$tmp/$name" | awk '{print $1}')
  [ "$expected" = "$actual" ] || { echo "uv checksum mismatch" >&2; exit 1; }
  tar -xzf "$tmp/$name" -C "$tmp"
  mv "$tmp/uv-$target/uv" tools/uv/uv
fi
tools/uv/uv python install 3.12 --no-bin --no-registry
tools/uv/uv sync --locked --no-dev
if [ ! -x tools/yt-dlp/yt-dlp ]; then
  base=https://github.com/yt-dlp/yt-dlp/releases/latest/download
  download "$base/yt-dlp_macos" "$tmp/yt-dlp_macos"
  download "$base/SHA2-256SUMS" "$tmp/sums"
  expected=$(awk '$2 == "yt-dlp_macos" {print $1}' "$tmp/sums")
  actual=$(shasum -a 256 "$tmp/yt-dlp_macos" | awk '{print $1}')
  [ -n "$expected" ] && [ "$expected" = "$actual" ] || { echo "yt-dlp checksum mismatch" >&2; exit 1; }
  chmod +x "$tmp/yt-dlp_macos"
  mv "$tmp/yt-dlp_macos" tools/yt-dlp/yt-dlp
fi
tools/yt-dlp/yt-dlp --ignore-config --version
.venv/bin/python scripts/macos/install_ffmpeg.py
.venv/bin/python -m playwright install chromium
if [ "${1:-}" != --skip-plugin-install ]; then
  .venv/bin/python scripts/macos/install_plugin.py
fi
echo "macOS preview setup complete."
