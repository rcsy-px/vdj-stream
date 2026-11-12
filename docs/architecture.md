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

A shared runner allows at most two yt-dlp processes. Updates wait for active
processes to drain and block new work while replacing the executable. Every
invocation ignores external yt-dlp configuration. Cancelled or timed-out calls
kill and reap their child process.

Backend search/resolution and stream preparation have a 55-second total budget;
the native plugin waits up to 65 seconds for an HTTP response. Search providers
each get 20 seconds. Streaming reads have their own finite idle timeout. HTTP
503 means busy, 504 means timed out, and 502 means the upstream operation failed.
An empty successful search remains HTTP 200. Audio extensions and upstream Range
responses are preserved; upstream clients close on failure and disconnection.

Resolved URLs use a bounded 256-entry cache. Per-track locks deduplicate concurrent
resolution and are removed when no caller needs them. Chromium must match the
revision specified by the installed Playwright package.

The local, token-protected diagnostics endpoint tests both search providers,
resolves a sample track, and requests a small audio range without playing it.
