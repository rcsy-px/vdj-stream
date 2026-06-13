<p align="center">
  <img src="docs/assets/logo.svg" alt="VDJ Companion" width="720">
</p>

<p align="center">
  Search YouTube from VirtualDJ's native browser and load results directly onto a deck.
</p>

<p align="center">
  <a href="LICENSE"><img alt="MIT License" src="https://img.shields.io/badge/license-MIT-22c55e"></a>
  <img alt="Windows x64" src="https://img.shields.io/badge/platform-Windows%20x64-2563eb">
  <img alt="Local only" src="https://img.shields.io/badge/backend-localhost-8b5cf6">
  <a href="https://github.com/rcsy-px/vdj-stream/releases/latest"><img alt="Latest release" src="https://img.shields.io/github/v/release/rcsy-px/vdj-stream?display_name=tag"></a>
  <a href="https://ko-fi.com/rycsypx"><img alt="Support on Ko-fi" src="https://img.shields.io/badge/Ko--fi-support-ff5e5b"></a>
</p>

## What it does

VDJ Companion adds a lightweight Online Source to VirtualDJ. Search results
appear in VirtualDJ's own browser, and selected tracks are resolved only when
you load them onto a deck.

- Native VirtualDJ browser integration
- One-shot Windows setup with no manual plugin copying
- Prebuilt x64 plugin; Visual Studio is not required for users
- Local-only FastAPI backend bound to `127.0.0.1`
- HTTP Range streaming for responsive analysis and seeking
- yt-dlp metadata search with Chromium fallback
- Lightweight local health page with no telemetry
- Consent-based GitHub release update notifications

## Install

### Requirements

- Windows x64
- VirtualDJ with a Pro license
- Internet access during setup and use

### Quick start

1. [Download the latest release ZIP](https://github.com/rcsy-px/vdj-stream/releases/latest)
   and extract it to a permanent folder.
2. Double-click `START.bat`.
3. Wait for the first-time setup to finish.
4. Restart VirtualDJ.
5. Open **Online Music → VDJ Companion Source** in VirtualDJ's browser.

That is all. `START.bat` downloads only missing portable dependencies, installs
the included plugin into VirtualDJ's active plugin folder, starts the local
backend in the background, and opens its control panel. Running it again skips
components that are already ready.

The status page is available at <http://127.0.0.1:8765/>.
It includes live logs and a button to shut down the backend. `STOP.bat` provides
a fallback, while `START-DEBUG.bat` runs the backend in a visible console. The
page also checks GitHub releases for newer versions and links to the release
details when an update is available. A specific update can be skipped
locally; its version badge remains clickable, and any newer release is shown
prominently again.

### Verify downloads

Each GitHub release includes SHA-256 checksum files for the release ZIP and the
plugin DLL. After downloading them, calculate the local hashes:

```powershell
Get-FileHash -Algorithm SHA256 .\vdj-companion-<version>-windows-x64.zip
Get-FileHash -Algorithm SHA256 ".\plugin\online-source\prebuilt\x64\VDJ Companion Source.dll"
```

Compare the resulting hashes with the matching `.sha256` files from the GitHub
release. Matching hashes confirm that the downloaded files have not changed.

## How it works

```text
VirtualDJ native browser
  -> prebuilt Online Source plugin
  -> localhost search API
  -> Chromium / yt-dlp search
  -> selected-track resolver
  -> localhost Range proxy
  -> VirtualDJ deck
```

The backend does not pre-resolve every search result. Resolution starts only
when a result is loaded, keeping searches quick and upstream URLs fresh.

More detail is available in [Architecture](docs/architecture.md) and
[Portable tools](docs/portable-tools.md).

## Privacy and security

VDJ Companion runs locally and listens only on `127.0.0.1`. It includes no
telemetry and does not require an account of its own. Runtime logs, caches,
downloaded tools, and browser data remain local and are excluded from source
control and release packages. Opening the local control panel sends a
rate-limited request to GitHub's Releases API to read the latest available
version. If an update is skipped, only that version number is stored in the
browser's local storage. VDJ Companion never downloads or installs updates
automatically; updating remains a fully manual user decision through the linked
GitHub release page.

See [Security Policy](SECURITY.md) before reporting a vulnerability.

## Troubleshooting

**The Online Source is missing in VirtualDJ**

- Confirm VirtualDJ is signed in with an active Pro license.
- Run `START.bat`, then restart VirtualDJ.
- Check that the status page reports all components as ready.

**Search or loading fails**

- Open <http://127.0.0.1:8765/> and check the component status.
- YouTube or yt-dlp changes can temporarily affect extraction.

**Port `8765` is already in use**

- Close the other VDJ Companion/backend process, then run `START.bat` again.

## Build from source

Application tests:

```powershell
.venv\Scripts\python -m pytest -q
```

The native plugin requires Visual Studio with the C++ workload:

```powershell
powershell -ExecutionPolicy Bypass -File plugin\online-source\build-and-install.ps1
```

The build script refreshes the distributable plugin at
`plugin\online-source\prebuilt\x64\VDJ Companion Source.dll`.

Create a sanitized Windows release ZIP:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build-release.ps1
```

The release script also creates SHA-256 checksum files for the ZIP and plugin
DLL in `dist`.

## Support the project

VDJ Companion is free and open source. If it saves you time or makes a set
easier, you can support continued development on
[Ko-fi](https://ko-fi.com/rycsypx).

## Legal

VDJ Companion is an independent, unofficial project. It is not affiliated with,
endorsed by, or sponsored by Atomix Productions, VirtualDJ, Google, or YouTube.
VirtualDJ and YouTube are trademarks of their respective owners.

Users are responsible for complying with applicable laws, licenses, platform
terms, and venue or performance requirements. This project does not bypass DRM
and does not include or redistribute media.

Released under the [MIT License](LICENSE).
