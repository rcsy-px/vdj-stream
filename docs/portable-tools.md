# Portable Tools

All generated tools and runtimes remain inside the project:

- `tools/uv`
- `tools/python`
- `tools/yt-dlp`
- `tools/ffmpeg`
- `tools/playwright-browsers`
- `.cache/uv`

`START.bat` runs the idempotent setup flow. It downloads uv and yt-dlp from
their official GitHub releases and the essentials FFmpeg build from gyan.dev.
Existing tools are left in place. The control panel checks the installed yt-dlp
version and the latest stable release; updates are installed only when you click
**Update yt-dlp**. The setup also creates `.venv`, syncs Python
dependencies, installs Chromium locally, starts the backend in the background,
and opens the local control panel. Use `START-DEBUG.bat` for a visible backend
console or `STOP.bat` as a fallback shutdown method.

Scripts modify PATH and environment variables for their own process only. They
do not require administrator rights or permanently alter the system PATH.

The backend runner intentionally omits Uvicorn's `--reload` option. On Windows,
reload mode selects an asyncio event loop without subprocess support, while both
Playwright and yt-dlp require subprocesses.

If bootstrap download is blocked, download the same official assets manually:
place `uv.exe` in `tools/uv`, `yt-dlp.exe` in `tools/yt-dlp`, and the FFmpeg
`bin` contents in `tools/ffmpeg/bin`.

## Verify a release download

Download the matching `.sha256` files from the same GitHub release as your ZIP.
Calculate the local hashes in PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 .\vdj-companion-<version>-windows-x64.zip
Get-FileHash -Algorithm SHA256 ".\plugin\online-source\prebuilt\x64\VDJ Companion Source.dll"
```

Compare each hash with its matching checksum file. The DLL command applies after
extracting the ZIP. A matching hash confirms that your copy matches the published
release artifact.
