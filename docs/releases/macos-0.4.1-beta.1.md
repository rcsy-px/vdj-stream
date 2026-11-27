# VDJ Companion for macOS — 0.4.1 beta 1

Public beta for Apple Silicon and Intel, macOS 14 or later.

Fixes a cause of **Download error (502)** when loading YouTube audio. Companion now respects the link's availability time, including longer waits, within the existing request timeout. Subsequent requests reuse the ready link without another wait. Upstream failures and timeouts are logged for troubleshooting.

This addresses the availability-delay failure; other network or YouTube errors can still occur.

## Install or update

Existing users: quit VirtualDJ and click **Install update & restart** in Companion. Settings, setlists and saved media are preserved.

New users: extract `vdj-companion-0.4.1-beta.1-macos-universal.zip` to a permanent folder and run `START.command`. No GitHub account is required. See the included README for macOS security approval steps. This beta is not Developer ID signed or notarized.

## Validation

Publication requires automated tests, native builds and extracted-package checks on both Apple Silicon and Intel, plus Windows regression checks. The shared backend passed 162 tests and live HTTP audio checks on Windows with both installed and current yt-dlp versions. Delayed availability was verified with controlled tests. Physical Mac VirtualDJ playback testing is still needed.

Thanks to [@kernel-machine](https://github.com/kernel-machine) for the initial fix in [#13](https://github.com/rcsy-px/vdj-stream/pull/13).
