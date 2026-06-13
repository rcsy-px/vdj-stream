# Changelog

## Unreleased

- Added consent-based update notifications, GitHub release details, and per-version skipping to the control panel.

## 0.1.1 - 2026-06-13

- Added finite upstream stream timeouts and expired-URL retry coverage.
- Improved search cache behavior for different result limits.
- Added automatic yt-dlp update checks during setup and startup.
- Added cache cleanup, accurate health readiness, and clearer plugin errors.
- Added native plugin builds to CI and release workflows.
- Centralized the application version in `VERSION`.
- Expanded backend integration coverage for fallback search and Range streaming.
- Added a browser control panel with live redacted logs and local shutdown.
- Added hidden background startup, visible debug startup, and fallback stop scripts.
- Made lightweight yt-dlp metadata search primary for substantially better track lengths.
- Added release SHA-256 checksums for both the Windows ZIP and plugin DLL.

## 0.1.0 - 2026-06-12

- Added native VirtualDJ Online Source search and deck loading.
- Added localhost Range proxy for responsive analysis and seeking.
- Added one-shot Windows setup and startup flow.
- Added prebuilt x64 VirtualDJ plugin for no-build installation.
- Added lightweight local status page.
