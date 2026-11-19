# VDJ Companion for macOS — 0.3.2 beta 1

Public beta for Apple Silicon and Intel, macOS 14 or later. No GitHub account required.

- See download storage usage and free disk space in the control panel.
- Open saved files in Finder with **Open download folder**.
- Removed the 5 GB library cap and 500 MB per-file cap.
- Downloads stop when less than 2 GB of free space remains; free up space and retry.

Includes setlists, offline audio, prepared videos up to 720p, played-track history
and remembered searches. Existing saved files and setlists are preserved.

## Install

Download `vdj-companion-0.3.2-beta.1-macos-universal.zip`, extract it to a permanent
folder and run `START.command`. The launcher installs the required tools and plugin.
This beta is not Developer ID signed or notarized; macOS may require approval in
Privacy & Security. See the included README for the walkthrough.

## Update

Existing beta users can check for updates in the control panel, close VirtualDJ,
then click **Install update & restart**. Keep Companion running while playing
saved files. Setup and runtime logs remain local in `data/logs`.

## Testing status

Publication requires passing automated tests, native builds and extracted-package
installation checks on both Apple Silicon and Intel. Actual VirtualDJ playback on
a physical Mac has not been tested by the maintainer; this remains a public beta.
