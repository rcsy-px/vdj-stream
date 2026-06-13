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
Existing downloads are left in place, while yt-dlp checks its stable channel
for updates on startup. The setup also creates `.venv`, syncs Python
dependencies, and installs Chromium locally.

Scripts modify PATH and environment variables for their own process only. They
do not require administrator rights or permanently alter the system PATH.

The backend runner intentionally omits Uvicorn's `--reload` option. On Windows,
reload mode selects an asyncio event loop without subprocess support, while both
Playwright and yt-dlp require subprocesses.

If bootstrap download is blocked, download the same official assets manually:
place `uv.exe` in `tools/uv`, `yt-dlp.exe` in `tools/yt-dlp`, and the FFmpeg
`bin` contents in `tools/ffmpeg/bin`.
