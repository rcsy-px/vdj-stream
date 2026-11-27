# Changelog

## 0.4.1 - 2026-11-27

- Wait until yt-dlp's `available_at` timestamp before requesting a YouTube audio stream, fixing a cause of HTTP 502 track-loading errors.
- Honor the full availability delay within the existing total request deadline, including refreshed URLs; cached streams do not wait again once available.
- Log upstream failures and stream timeouts for troubleshooting.
- Add regression coverage for long waits, repeated range requests, URL refresh, timeouts and cancellation.
- Includes macOS 0.4.1 beta 1 for Intel and Apple Silicon.
- Thanks to @kernel-machine for identifying the issue and contributing the initial fix in PR #13.

## 0.4.0 - 2026-11-24

- Add a persistent Search source selector: YouTube, YouTube Music Songs, or YouTube Music Videos, with artist, duration and cover metadata.
- Keep search caches separate by source; Music searches never silently fall back to ordinary YouTube results.
- Recover valid saved audio/video before downloading again when its library record is missing or stale.
- Add an optional **Track title + ID** filename setting for new downloads on Windows and macOS; existing filenames stay unchanged.
- Includes macOS 0.4.0 beta 1 for Intel and Apple Silicon.

## 0.3.1 - 2026-11-17

- Added Windows application updates from the control panel, including verified downloads, plugin installation and automatic restart.
- Preserve user data and downloaded media; restore the old application, Python environment and plugin if installation or startup fails.
- Recover interrupted updates through the START launcher and retain local update logs and backups.
- Windows 0.3.0 and earlier require one manual installation of 0.3.1 before using the new updater for future releases.

## 0.3.0 - 2026-11-17

- Added persistent setlists and M3U8 export.
- Added offline audio downloads and prepared H.264 video up to 720p.
- Added read-only VirtualDJ History import and a Last search folder.
- Added download queue controls, storage limits and media validation.
- Labelled Companion context-menu actions.
- Includes macOS 0.3.0 beta 1 with separate platform setup and update support.

## 0.2.0 - 2026-11-12

Package revised on 2026-11-12 without a version bump:

- Tightened the logo framing in the control panel and README while preserving the original artwork.
- Bypass HTTP caches when fetching release versions and prevent browsers from storing update-status responses. Manual checks refresh both application and yt-dlp data while automatic checks remain rate-limited.

- Rebuilt the local control panel with a responsive retro metal skin and an original headphone robot logo.
- Added a first-visit welcome dialog and optional Ko-fi support link.
- Added on-demand diagnostics for search, Chromium, audio resolution, and actual audio delivery.
- Serialized engine updates against bounded concurrent searches and resolutions; ignored external yt-dlp configuration.
- Aligned plugin/backend timeouts, distinguished search failure from empty results, and improved track-load errors.
- Closed upstream connections and child processes on errors, cancellation, and disconnects; preserved HTTP 416 and audio extensions.
- Bounded the resolver cache and removed unused per-track locks.
- Validated and retried portable-tool downloads before replacing files; installed the exact Playwright Chromium revision.
- Enforced a total download deadline even when a server stalls mid-transfer.
- Preferred the FFmpeg build author's GitHub mirror for first-install downloads.
- Kept portable Python installation from adding user-level executables or registry entries.
- Required backend tests, native builds, source fingerprint checks, and archive smoke checks before release publication.
- Reworked the README and included contributor instructions in release archives.
- Added installed/latest yt-dlp versions, periodic checks, and a protected manual stable update button.
- Reduced failed release-check caching to one minute and added immediate retry with useful errors.
- Replaced startup's automatic yt-dlp updates with explicit control-panel updates.
- Fixed misleading backend startup failures when the browser cannot be opened.
- Excluded local design mockups from Git.

## 0.1.2 - 2026-06-13

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
