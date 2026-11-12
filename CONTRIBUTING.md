# Contributing

Contributions and focused bug reports are welcome.

## Development setup

1. Run `START.bat` once to prepare the local environment.
2. Run `.venv\Scripts\python -m pytest -q` before submitting changes.
3. Keep the backend bound to `127.0.0.1`.
4. Do not commit runtime data, logs, downloaded tools, credentials, or cookies.

## Native plugin changes

The plugin requires Visual Studio with the C++ workload. Build it with:

```powershell
powershell -ExecutionPolicy Bypass -File plugin\online-source\build-and-install.ps1 -BuildOnly
```

That script refreshes the distributable prebuilt DLL. Include the updated
`plugin\online-source\prebuilt\x64\VDJ Companion Source.dll` with plugin changes.
Include its generated `build-info.json` too. Packaging checks the version, DLL
checksum, and source fingerprints. Omit `-BuildOnly` to install locally; close
VirtualDJ first. For a nonstandard Visual Studio installation, pass
`-MSBuildPath "D:\path\to\MSBuild.exe"`.

## Release package

Create a Windows release ZIP and SHA-256 checksums in `dist`:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build-release.ps1
.venv\Scripts\python scripts\verify-release.py
```

Build the native plugin first when its source has changed. The release archive
includes the backend, control panel assets, documentation, and prebuilt plugin;
it excludes local tools, caches, logs, and design mockups.

CI and tagged releases run backend tests, build the native plugin, and verify
the extracted archive before publishing. Before tagging, also check on Windows:

- Extract to a fresh folder and run `START.bat` without preinstalled tools.
- Confirm the welcome appears once and diagnostics pass.
- Search and load two different tracks on two VirtualDJ decks, seek in both,
  and confirm audio continues to play.
- Disconnect/reconnect the network and verify an actionable error and recovery.
- Check an engine update while requests are active, then load a new track.

Automated proxy and concurrency tests do not replace the actual VirtualDJ checks.

## Pull requests

Keep changes scoped, explain user-visible behavior, and include relevant tests.
By contributing, you agree that your contribution is licensed under the MIT
License.
