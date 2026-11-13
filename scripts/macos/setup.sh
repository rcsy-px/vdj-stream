#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/../.."
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
for name in ffmpeg ffprobe; do
  candidate="${FFMPEG_BIN_DIR:-}/$name"
  if [ ! -x "$candidate" ]; then candidate=$(command -v "$name" || true); fi
  if [ -z "$candidate" ] || [ ! -x "$candidate" ]; then
    echo "Install FFmpeg first (brew install ffmpeg), then reopen START.command." >&2
    echo "Alternatively set FFMPEG_BIN_DIR to a folder containing ffmpeg and ffprobe." >&2
    exit 1
  fi
  ln -sfn "$candidate" "tools/ffmpeg/bin/$name"
done
.venv/bin/python -m playwright install chromium
if [ "${1:-}" != --skip-plugin-install ]; then
  .venv/bin/python scripts/macos/install_plugin.py
fi
echo "macOS preview setup complete."
