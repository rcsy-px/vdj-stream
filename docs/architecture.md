# Architecture

```text
VirtualDJ native browser
  -> VDJ Companion Source.dll
  -> FastAPI Online Source API
  -> SQLite query cache
  -> yt-dlp metadata search
       fallback: Chromium YouTube search

VirtualDJ deck load
  -> Online Source GetStreamUrl
  -> selected-track yt-dlp resolver
  -> localhost Range proxy
  -> VirtualDJ deck
```

The Online Source plugin is intentionally thin. Search rendering, fallback,
caching, yt-dlp resolution, upstream URL refresh, and HTTP streaming remain in
FastAPI.

Search results are not pre-resolved. `GetStreamUrl` resolves only the selected
track when VirtualDJ loads it onto a deck.

The dedicated `/stream/vdj-source/...` route defaults missing Range requests to
`bytes=0-`, which gives VirtualDJ `206 Partial Content` behavior for faster
analysis and seeking.

The backend binds only to `127.0.0.1`. No endpoint is intended to be exposed to
a LAN or the public internet.
