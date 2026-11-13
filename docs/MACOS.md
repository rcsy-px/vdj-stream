# VDJ Companion for macOS

Search YouTube inside VirtualDJ, then drag a result onto a deck. Companion runs
alongside VirtualDJ and provides a browser control panel for status and updates.

**Public beta · Intel and Apple Silicon · macOS 14 or later**

[Download beta 2](https://github.com/rcsy-px/vdj-stream/releases/download/macos-v0.2.0-beta.2/vdj-companion-0.2.0-beta.2-macos-universal.zip)
· [Release notes](https://github.com/rcsy-px/vdj-stream/releases/tag/macos-v0.2.0-beta.2)
· [Report a problem](https://github.com/rcsy-px/vdj-stream/issues)

No GitHub account is needed to download. Installation and update flows have
automated tests on both Mac CPU families, but search and deck playback still need
feedback from people using real VirtualDJ installations.

## Before you start

- A Mac running macOS 14 or later, with an internet connection.
- VirtualDJ installed and opened at least once, with an active Pro license as
  required by the Windows version.
- **FFmpeg and ffprobe**, installed using the instructions below.

You do not need to install Python, yt-dlp or Chromium yourself. The launcher
downloads private copies into the Companion folder on first launch.

## 1. Install FFmpeg

If you use [Homebrew](https://brew.sh), open **Terminal** (Applications → Utilities)
and run:

```bash
brew install ffmpeg
```

If Homebrew is not installed, follow its [official instructions](https://brew.sh),
including any “Next steps”, then run the command above. Homebrew currently supports
macOS 15 and newer; on macOS 14, use an existing compatible FFmpeg installation
with the [custom folder option](#custom-folders) below.

Check that both tools print version information:

```bash
ffmpeg -version
ffprobe -version
```

If either says `command not found`, finish the Homebrew setup or configure your
existing FFmpeg folder before continuing.

## 2. Download and start Companion

1. Download the **macOS ZIP** linked above. Under release **Assets**, choose
   `vdj-companion-0.2.0-beta.2-macos-universal.zip`, not a source-code archive.
   The same ZIP works on Intel and Apple Silicon.
2. Double-click the ZIP to extract it. Move the extracted folder somewhere
   permanent and writable, such as inside your home folder, **before** running it.
   Keep all its files together.
3. Open VirtualDJ once if you have not already, then **quit it with Command+Q**
   so Companion can install its source plugin.
4. Double-click **START.command**. A Terminal window opens. First setup downloads
   the tools and installs the plugin; allow several minutes and keep it open.
5. The control panel opens in your browser. If it does not, visit
   [http://127.0.0.1:8765](http://127.0.0.1:8765/).
6. Open VirtualDJ, select **Online Music / Online Sources → VDJ Companion Source**,
   search for a track, and drag a result onto a deck.

### If macOS blocks opening a file

This beta is ad-hoc signed, **not Apple Developer ID signed or notarized**.
If the developer cannot be verified and you trust the download, try opening the
file once, then go to **System Settings → Privacy & Security → Open Anyway**
(if offered) and confirm. See [Apple's instructions](https://support.apple.com/en-us/102445).

Do not disable Gatekeeper globally. If the message says the file is damaged or
will harm your computer, or VirtualDJ refuses the plugin, stop and report the
exact message.

## Everyday use

Open **START.command** before using the source. Keep its Terminal window open
while searching or streaming. You may close the browser tab and reopen the
control panel whenever needed.

When finished, stop using the source, then double-click **STOP.command**, click
**Shutdown backend**, or press **Ctrl+C** in the launcher Terminal. Companion
does not start automatically when you log in.

Do not move or rename its folder after setup: the managed environment contains
absolute paths. To change location, extract a fresh copy there and run its launcher.

## Keep it up to date

### Companion updates

The panel checks the separate Mac release channel automatically, including newer
betas. You can also click **Check again**.

1. When an update appears, finish your session and **quit VirtualDJ**.
2. Click **Install update & restart** and confirm.
3. Keep the launcher Terminal open and wait for the panel to return.
4. Check the displayed version, then reopen VirtualDJ.

Companion verifies the download, backs up its files, Python environment and
installed plugin, installs the update and restarts. Settings and user data stay
in place. Installation failures restore the previous files. Updates install only
when you click the button; they are not silently installed during a session.

Backups and `update.log` remain in `.cache/app-update-*` inside the Companion
folder. Keep them if something goes wrong. In Finder, **Command+Shift+.** toggles
hidden files. After an interrupted update, reopen **START.command** in the same
folder so it can attempt recovery; do not delete the backup first.

<details>
<summary>Already installed the earlier beta 1?</summary>

That build did not include the app updater and is no longer offered for download.
Stop the old Companion, quit VirtualDJ, extract beta 2 into a new permanent folder
and run its **START.command** once. Use the new folder from then on; later updates
can be installed from the panel. Keep the old folder if you need its data: this
fresh installation does not migrate it automatically.

</details>

### YouTube engine updates (yt-dlp)

yt-dlp has its own installed/latest version display and **Update yt-dlp** button.
If tracks stop loading, check for an engine update, install it if available, then
reload the track in VirtualDJ. This is separate from updating Companion itself.

## Troubleshooting

| What you see | What to try |
| --- | --- |
| `brew: command not found` | Complete Homebrew's installation and “Next steps”, then open a new Terminal. |
| FFmpeg or ffprobe missing | Complete step 1 or set `FFMPEG_BIN_DIR` below. Both tools are required. |
| Setup fails | Read the last error in the launcher Terminal. Resolve it, then reopen `START.command`. |
| VirtualDJ folder not found | Open VirtualDJ once and quit it. For a custom location, use `VDJ_HOME` below. |
| Source missing | Let setup finish, restart VirtualDJ and check your Pro license. Resolve any plugin-folder error shown during setup. |
| No search results | Click **Run checks** in the control panel and inspect **Live logs**. |
| Deck shows **Download error / 502** | Update yt-dlp if available and reload the track. If it persists, use **Run checks**. |
| **503 / busy** or **504 / timeout** | Wait for current requests or an engine update to finish, then retry. Check your connection if timeouts persist. |
| Panel does not open | Keep the launcher running and open `http://127.0.0.1:8765/` manually. Check Terminal for startup errors. |
| Port **8765** occupied | Stop the other Companion copy using its `STOP.command`. If another app owns the port, close that app before retrying. |
| Update asks to close VirtualDJ | Quit VirtualDJ with Command+Q, then retry. |
| Update fails or does not restart | Reopen `START.command` in the same folder. Keep the backup and `update.log`; report the error if recovery fails. |

If setup was forcibly interrupted and now reports a setup lock, first ensure the
old setup process has stopped. Remove only the empty `.cache/macos-setup.lock`
folder, then retry.

### Custom folders

The installer detects an existing VirtualDJ home in
`~/Library/Application Support/VirtualDJ` or `~/Documents/VirtualDJ`, and supports
existing `PluginsMacArm`, `PluginsArm`, `Plugins64`, and `PluginsMac` folders.
It backs up this source plugin before replacement and leaves other plugins alone.

In Terminal, type `cd ` (with a space), drag the Companion folder into the window,
and press Return. Run the matching command below, replacing example paths with
your actual folders:

```bash
# Choose your existing VirtualDJ home:
VDJ_HOME="$HOME/Library/Application Support/VirtualDJ" ./START.command

# Or choose the exact existing OnlineSources folder:
VDJ_PLUGIN_DIR="/path/to/VirtualDJ/PluginsMacArm/OnlineSources" ./START.command

# Use a folder containing both ffmpeg and ffprobe:
FFMPEG_BIN_DIR="/path/to/ffmpeg/bin" ./START.command
```

Overrides apply to that launch and its in-app updates. Use the same command on
later launches if your setup requires it. Multiple overrides can be placed before
`./START.command` on the same line.

## Send feedback

[Open an issue](https://github.com/rcsy-px/vdj-stream/issues) or reply in the
discussion where you found the beta. Include:

- macOS version and Intel or Apple Silicon.
- VirtualDJ, Companion and yt-dlp versions.
- Whether the source appears, searches return results and tracks load on a deck.
- The exact error and relevant **Run checks** result or log excerpt.

Remove personal paths, searches and tokens before sharing logs. Reports that
everything works are useful too, especially with your Mac and VirtualDJ versions.

## Development and validation

Mac scripts live in `scripts/macos`, native Mac networking in
`plugin/online-source/platform/macos`, and shared Python/frontend code in
`backend`. Windows launchers and the stable Windows release remain separate.

```bash
uv sync --locked
uv run python -m pytest -q
bash scripts/macos/build-plugin.sh
uv run python scripts/macos/native_smoke.py
uv run python scripts/macos/package.py
```

CI checks Intel and Apple Silicon builds, native loading and HTTP against a local
test server, Chromium startup, extracted-package setup/start/stop, and the app
update/install/restart flow with a fixture release. Windows regression checks also
run. These tests do not prove real VirtualDJ deck playback.

Before a stable Mac release: test real search and playback on both CPU families,
check Finder/Gatekeeper installation on a clean account, and arrange Developer ID
signing and notarization.
