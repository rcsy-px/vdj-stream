# VDJ Companion — macOS preview

This is an experimental macOS port. The stable Windows release is unchanged.
The bundle contains both Apple Silicon and Intel code. Requires macOS 14 or later,
VirtualDJ, an internet connection, and FFmpeg. Real VirtualDJ loading and playback
still need validation by Mac users; automated tests do not replace that check.

## First start

1. Download the **macOS preview artifact** from the `macOS preview` GitHub Actions
   run for the `feature/macos` branch. Extract the artifact, then the ZIP inside it.
   Keep the extracted Companion folder somewhere permanent and writable.
2. Install FFmpeg and ffprobe. If you use [Homebrew](https://brew.sh), run
   `brew install ffmpeg`. Alternatively, supply your existing FFmpeg folder with
   `FFMPEG_BIN_DIR` as shown below.
3. Open VirtualDJ once, then close it so its plugin folders exist.
4. Double-click **START.command**. The first start downloads a private Python,
   yt-dlp and Chromium, and installs the plugin. Allow a few minutes.
5. Keep the Terminal window open, reopen VirtualDJ, and look for
   **VDJ Companion Source** in Online Sources. The control panel opens in your browser.

Double-click **STOP.command**, use the control panel's shutdown button, or press
Ctrl+C in the launcher's Terminal to stop Companion. No login service is installed.
The web control panel and yt-dlp update button work the same way as on Windows.
Preview updates are installed manually from a new preview ZIP; the app will never
offer a Windows ZIP as a Mac update.

## macOS security prompts

This preview is ad-hoc signed, **not Apple Developer ID signed or notarized**.
macOS may block the downloaded launcher or bundle. Review the source/download,
then use the system's per-item **Open Anyway** option in Privacy & Security if
available. Do not disable Gatekeeper globally. If VirtualDJ still refuses the
bundle, report the exact message before changing security settings. A smooth
signed installer remains a requirement for a stable Mac release.

## Custom folders and troubleshooting

The installer detects an existing VirtualDJ home in
`~/Library/Application Support/VirtualDJ` or `~/Documents/VirtualDJ`.
It supports existing `PluginsMacArm`, `PluginsArm`, `Plugins64`, and `PluginsMac`
folders. Existing copies of this plugin are backed up before replacement; no other
plugins are changed. If detection is ambiguous, launch from Terminal:

```bash
cd "/path/to/extracted/Companion"
VDJ_HOME="$HOME/Library/Application Support/VirtualDJ" ./START.command
# Or choose the exact existing OnlineSources directory:
VDJ_PLUGIN_DIR="/path/to/VirtualDJ/PluginsMacArm/OnlineSources" ./START.command
# Optional existing FFmpeg installation:
FFMPEG_BIN_DIR="/path/to/ffmpeg/bin" ./START.command
```

If setup was forcibly interrupted and reports a setup lock, first close the old
setup process, then remove the empty `.cache/macos-setup.lock` folder and retry.
Do not move the extracted app after setup: managed environments contain absolute
paths. For a new location, extract a fresh copy and run setup again.

For feedback, include macOS version, Intel/Apple Silicon, VirtualDJ version,
whether the source appears, and the exact search/deck error. Review logs before
sharing; remove personal paths, searches, and tokens.

## Development and validation

Windows-specific scripts and the stable release workflow remain separate.
Shared Python/frontend code lives in `backend`; Mac setup and packaging live in
`scripts/macos`; native Mac networking lives in
`plugin/online-source/platform/macos`. `build-plugin.sh` builds a universal `.bundle`
using Apple's SDK and system libcurl. Windows continues to use WinHTTP and MSBuild.

```bash
uv sync --locked
uv run python -m pytest -q
bash scripts/macos/build-plugin.sh
uv run python scripts/macos/native_smoke.py
uv run python scripts/macos/package.py
```

The separate CI workflow checks both CPU families, native plugin loading and HTTP
requests against a local test server, Chromium startup, and extracted-package
setup/start/stop. It also rebuilds/tests the Windows version for regressions.
It does not publish or replace the stable Windows release.

Before a stable Mac release: test search and deck playback in real VirtualDJ on
both CPU families, test Finder/Gatekeeper installation on a clean user account,
and arrange Developer ID signing and notarization.
