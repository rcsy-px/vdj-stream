import asyncio
import json
import logging
import os
import secrets
import signal
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse

from .config import get_settings
from .db.database import QueryCache
from .logging_config import configure_logging
from .models import ResolveResponse, SearchResponse
from .search.chromium_youtube import ChromiumYouTubeSearchProvider
from .search.ytdlp_search import YtDlpSearchProvider
from .stream.proxy import proxy_youtube_stream
from .stream.naming import stream_url
from .stream.resolver import YtDlpResolver
from .update_checker import GitHubReleaseChecker

settings = get_settings()
settings.prepare_directories()
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(settings.playwright_browsers_path))
live_logs = configure_logging(settings)
logger = logging.getLogger(__name__)
started_at = int(time.time())
shutdown_token = secrets.token_urlsafe(24)

cache = QueryCache(settings.database_path, Path(__file__).parent / "db" / "schema.sql")
browser_search = ChromiumYouTubeSearchProvider(
    headless=settings.headless, timeout_seconds=settings.search_timeout_seconds
)
ytdlp_search = YtDlpSearchProvider(settings.ytdlp_exe, settings.resolve_timeout_seconds)
resolver = YtDlpResolver(
    settings.ytdlp_exe,
    settings.resolve_timeout_seconds,
    settings.resolve_cache_ttl_seconds,
)
update_checker = GitHubReleaseChecker(
    settings.version,
    settings.github_repository,
    settings.update_check_cache_ttl_seconds,
    settings.update_check_timeout_seconds,
)


def _error_message(exc: Exception) -> str:
    message = str(exc).strip()
    return message or type(exc).__name__


@asynccontextmanager
async def lifespan(_: FastAPI):
    await cache.initialize()
    yield
    await browser_search.close()


app = FastAPI(title="VirtualDJ YouTube Companion", version=settings.version, lifespan=lifespan)
LOGO_PATH = settings.data_dir.parent / "docs" / "assets" / "logo.svg"
SEARCH_CACHE_NAMESPACE = "v2-ytdlp-primary"


def _search_cache_key(query: str) -> str:
    return f"{SEARCH_CACHE_NAMESPACE}:{query}"


def _health_payload() -> dict:
    chromium_installed = any(settings.playwright_browsers_path.glob("chromium-*"))
    tools = {
        "ytDlp": settings.ytdlp_exe.exists(),
        "ffmpeg": (settings.ffmpeg_bin / "ffmpeg.exe").exists(),
        "chromium": chromium_installed,
        "playwrightBrowsersPath": str(settings.playwright_browsers_path),
    }
    return {
        "ok": tools["ytDlp"] and tools["ffmpeg"] and tools["chromium"],
        "service": settings.service_name,
        "version": settings.version,
        "startedAt": started_at,
        "uptimeSeconds": max(0, int(time.time()) - started_at),
        "tools": tools,
    }


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def status_page() -> HTMLResponse:
    health = _health_payload()
    tools = health["tools"]
    checks = (
        ("Backend", True),
        ("yt-dlp", tools["ytDlp"]),
        ("FFmpeg", tools["ffmpeg"]),
        ("Chromium", tools["chromium"]),
    )
    rows = "".join(
        f'<li><span>{name}</span><strong class="{"ok" if ready else "bad"}">'
        f'{"Ready" if ready else "Missing"}</strong></li>'
        for name, ready in checks
    )
    return HTMLResponse(
        f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>VDJ Companion status</title>
  <style>
    :root {{ color-scheme: dark; font-family: system-ui, sans-serif; }}
    body {{ margin: 0; min-height: 100vh; display: grid; place-items: center; background: #111318; color: #f4f5f7; }}
    main {{ width: min(760px, calc(100% - 32px)); padding: 28px; margin: 24px 0; background: #1a1d24; border: 1px solid #30343e; border-radius: 16px; box-sizing: border-box; }}
    .logo {{ display: block; width: 100%; height: auto; margin: 0 0 22px; border-radius: 12px; }}
    ul {{ list-style: none; margin: 0; padding: 0; }}
    li {{ display: flex; justify-content: space-between; padding: 11px 0; border-top: 1px solid #30343e; }}
    .ok {{ color: #72db9c; }} .bad {{ color: #ff8585; }}
    .update {{ margin-top: 20px; padding: 14px; border: 1px solid #30343e; border-radius: 10px; transition: border-color .2s, background .2s, box-shadow .2s; }}
    .update.available {{ border-color: #3a9b61; background: linear-gradient(135deg, rgba(40, 120, 72, .2), rgba(26, 29, 36, .45)); box-shadow: 0 0 0 1px rgba(80, 210, 125, .1), 0 12px 32px rgba(0, 0, 0, .18); }}
    .update h2 {{ margin: 0 0 12px; font-size: 16px; }}
    .update-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }}
    .version {{ padding: 10px; background: #14171d; border-radius: 8px; }}
    .version span {{ display: block; color: #8f98a8; font-size: 12px; margin-bottom: 4px; }}
    .update.available #latest-version {{ display: inline-block; padding: 3px 8px; border-radius: 999px; background: #245c39; color: #b8f7ce; }}
    .update.skipped #latest-version {{ display: inline-block; padding: 3px 8px; border-radius: 999px; background: #245c39; color: #b8f7ce; cursor: pointer; }}
    .update.skipped #latest-version:hover {{ background: #2c7246; }}
    .update.skipped #update-status, .update.skipped .update-actions {{ display: none; }}
    #update-status {{ margin: 12px 0 0; color: #9ca3af; }}
    .update.available #update-status {{ color: #9ce3b6; font-weight: 650; }}
    .update-actions {{ display: none; gap: 10px; margin-top: 12px; }}
    .update.available .update-actions {{ display: flex; }}
    .release-link {{ flex: 1; padding: 10px 14px; border-radius: 9px; background: #245c39; color: #b8f7ce; text-decoration: none; font-weight: 650; text-align: center; }}
    .release-link:hover {{ background: #2c7246; }}
    .skip-update {{ border-color: #46505f; background: #252a33; color: #cbd5e1; }}
    .skip-update:hover {{ background: #303641; }}
    details {{ margin-top: 20px; border: 1px solid #30343e; border-radius: 10px; overflow: hidden; }}
    summary {{ padding: 12px; cursor: pointer; font-weight: 650; }}
    pre {{ height: 260px; overflow: auto; margin: 0; padding: 14px; background: #0c0e12; color: #cbd5e1; font: 12px/1.55 Consolas, monospace; white-space: pre-wrap; }}
    .actions {{ display: flex; justify-content: flex-end; margin-top: 20px; }}
    button {{ padding: 10px 14px; border: 1px solid #783b43; border-radius: 9px; background: #3b2025; color: #ffb4bd; cursor: pointer; font-weight: 650; }}
    button:hover {{ background: #51272e; }} button:disabled {{ opacity: .55; cursor: wait; }}
    #message {{ min-height: 20px; margin-top: 12px; color: #9ca3af; text-align: right; }}
    footer {{ margin-top: 20px; color: #737b8c; font-size: 13px; }}
    footer nav {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 14px; }}
    footer a {{ color: #aeb6c7; }}
    .social {{ display: flex; align-items: center; justify-content: center; gap: 8px; padding: 10px; border: 1px solid #3b414d; border-radius: 9px; color: #f4f5f7; text-decoration: none; font-weight: 650; }}
    .social:hover {{ background: #252a33; border-color: #606978; }}
    .social svg {{ width: 18px; height: 18px; fill: currentColor; }}
  </style>
</head>
<body>
  <main>
    <img class="logo" src="/assets/logo.svg" alt="VDJ Companion">
    <ul>{rows}</ul>
    <section id="update-panel" class="update" aria-labelledby="update-title">
      <h2 id="update-title">Updates</h2>
      <div class="update-grid">
        <div class="version"><span>Current version</span><strong>{health["version"]}</strong></div>
        <div class="version"><span>Latest available</span><strong id="latest-version">Checking...</strong></div>
      </div>
      <p id="update-status">Checking GitHub releases...</p>
      <div class="update-actions">
        <a id="view-update" class="release-link" target="_blank" rel="noopener noreferrer">View update details on GitHub</a>
        <button id="skip-update" class="skip-update" type="button">Skip this update</button>
      </div>
    </section>
    <details>
      <summary>Live logs</summary>
      <pre id="logs">Connecting...</pre>
    </details>
    <div class="actions"><button id="shutdown" type="button">Shutdown backend</button></div>
    <div id="message" role="status"></div>
    <footer>
      Version {health["version"]} · Uptime <span id="uptime">{health["uptimeSeconds"]}</span>s · <a href="/api/health">JSON health</a>
      <nav>
        <a class="social" href="https://github.com/rcsy-px" target="_blank" rel="noopener noreferrer" aria-label="GitHub profile">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 .7a11.5 11.5 0 0 0-3.6 22.4c.6.1.8-.2.8-.5v-2.2c-3.3.7-4-1.4-4-1.4-.5-1.4-1.3-1.7-1.3-1.7-1.1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1.1 1.8 2.8 1.3 3.4 1 .1-.8.4-1.3.8-1.6-2.7-.3-5.5-1.3-5.5-5.7 0-1.3.5-2.3 1.2-3.1-.1-.3-.5-1.6.1-3.1 0 0 1-.3 3.2 1.2a11 11 0 0 1 5.8 0C16.9 5 18 5.3 18 5.3c.6 1.5.2 2.8.1 3.1.8.8 1.2 1.8 1.2 3.1 0 4.4-2.8 5.4-5.5 5.7.4.4.8 1.1.8 2.2v3.2c0 .3.2.6.8.5A11.5 11.5 0 0 0 12 .7Z"/></svg>
          GitHub
        </a>
        <a class="social" href="https://ko-fi.com/rycsypx" target="_blank" rel="noopener noreferrer" aria-label="Support on Ko-fi">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 4h15a2 2 0 0 1 2 2v5a4 4 0 0 1-4 4h-1.2A6 6 0 0 1 10 19H8a6 6 0 0 1-6-6V6a2 2 0 0 1 2-2Zm12 3v5h1a1.5 1.5 0 0 0 0-3h-1V7Zm-7 8.2c.5-.4 3.4-2.3 3.4-4.7A2.3 2.3 0 0 0 8 9.4a2.3 2.3 0 0 0-4.4 1.1c0 2.4 2.9 4.3 3.4 4.7.6.4 1.4.4 2 0Z"/></svg>
          Ko-fi Support
        </a>
      </nav>
    </footer>
  </main>
  <script>
    const shutdownToken = {json.dumps(shutdown_token)};
    const logs = document.getElementById("logs");
    const message = document.getElementById("message");
    const shutdown = document.getElementById("shutdown");
    const latestVersion = document.getElementById("latest-version");
    const updatePanel = document.getElementById("update-panel");
    const updateStatus = document.getElementById("update-status");
    const viewUpdate = document.getElementById("view-update");
    const skipUpdate = document.getElementById("skip-update");
    const skippedUpdateKey = "vdj-companion-skipped-update";
    let availableUpdate = null;
    const getSkippedUpdate = () => {{
      try {{ return localStorage.getItem(skippedUpdateKey); }} catch (_) {{ return null; }}
    }};
    const setSkippedUpdate = version => {{
      try {{ localStorage.setItem(skippedUpdateKey, version); }} catch (_) {{}}
    }};
    const clearSkippedUpdate = () => {{
      try {{ localStorage.removeItem(skippedUpdateKey); }} catch (_) {{}}
    }};
    const showAvailableUpdate = update => {{
      updatePanel.classList.remove("skipped");
      updatePanel.classList.add("available");
      latestVersion.removeAttribute("role");
      latestVersion.removeAttribute("tabindex");
      updateStatus.textContent = `Version ${{update.latestVersion}} is available. Review the release details before downloading.`;
      viewUpdate.href = update.releaseUrl;
    }};
    const showSkippedUpdate = update => {{
      updatePanel.classList.remove("available");
      updatePanel.classList.add("skipped");
      latestVersion.setAttribute("role", "button");
      latestVersion.setAttribute("tabindex", "0");
      latestVersion.setAttribute("aria-label", `Show update ${{update.latestVersion}} details`);
    }};
    let firstLog = true;
    const events = new EventSource("/api/logs/stream");
    events.onmessage = event => {{
      if (firstLog) {{ logs.textContent = ""; firstLog = false; }}
      logs.textContent += event.data + "\\n";
      logs.scrollTop = logs.scrollHeight;
    }};
    events.onerror = () => {{
      if (!firstLog) logs.textContent += "Log stream disconnected.\\n";
    }};
    setInterval(() => {{
      const el = document.getElementById("uptime");
      el.textContent = String(Number(el.textContent) + 1);
    }}, 1000);
    fetch("/api/update")
      .then(response => response.json())
      .then(update => {{
        latestVersion.textContent = update.latestVersion || "Unavailable";
        if (update.updateAvailable && update.releaseUrl) {{
          availableUpdate = update;
          if (getSkippedUpdate() === update.latestVersion) showSkippedUpdate(update);
          else showAvailableUpdate(update);
        }} else if (update.error) {{
          updateStatus.textContent = "Update check is temporarily unavailable.";
        }} else {{
          updateStatus.textContent = "You are running the latest version.";
        }}
      }})
      .catch(() => {{
        latestVersion.textContent = "Unavailable";
        updateStatus.textContent = "Update check is temporarily unavailable.";
      }});
    skipUpdate.addEventListener("click", () => {{
      if (!availableUpdate) return;
      setSkippedUpdate(availableUpdate.latestVersion);
      showSkippedUpdate(availableUpdate);
    }});
    const restoreUpdate = () => {{
      if (!availableUpdate || !updatePanel.classList.contains("skipped")) return;
      clearSkippedUpdate();
      showAvailableUpdate(availableUpdate);
    }};
    latestVersion.addEventListener("click", restoreUpdate);
    latestVersion.addEventListener("keydown", event => {{
      if (event.key === "Enter" || event.key === " ") {{
        event.preventDefault();
        restoreUpdate();
      }}
    }});
    shutdown.addEventListener("click", async () => {{
      if (!confirm("Shut down the VDJ Companion backend?")) return;
      shutdown.disabled = true;
      message.textContent = "Shutting down...";
      try {{
        const response = await fetch("/api/shutdown", {{
          method: "POST",
          headers: {{ "X-Shutdown-Token": shutdownToken }}
        }});
        if (!response.ok) throw new Error("Shutdown request failed");
        events.close();
        message.textContent = "Backend stopped. This tab can be closed.";
      }} catch (error) {{
        shutdown.disabled = false;
        message.textContent = error.message;
      }}
    }});
  </script>
</body>
</html>"""
    )


@app.get("/assets/logo.svg", response_class=FileResponse, include_in_schema=False)
async def logo() -> FileResponse:
    return FileResponse(LOGO_PATH, media_type="image/svg+xml")


@app.get("/api/health")
async def health() -> dict:
    return _health_payload()


@app.get("/api/update", include_in_schema=False)
async def update_status() -> dict:
    return await update_checker.check()


@app.get("/api/logs/stream", include_in_schema=False)
async def log_stream(request: Request) -> StreamingResponse:
    async def events():
        last_id = 0
        while not await request.is_disconnected():
            lines = live_logs.since(last_id)
            if lines:
                for last_id, line in lines:
                    yield f"id: {last_id}\ndata: {line.replace(chr(10), ' ')}\n\n"
            else:
                yield ": keepalive\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _is_loopback(request: Request) -> bool:
    return request.client is not None and request.client.host in {"127.0.0.1", "::1", "testclient"}


async def _stop_process() -> None:
    await asyncio.sleep(0.25)
    os.kill(os.getpid(), signal.SIGTERM)


@app.post("/api/shutdown", include_in_schema=False)
async def shutdown(request: Request) -> JSONResponse:
    if not _is_loopback(request) or request.headers.get("x-shutdown-token") != shutdown_token:
        raise HTTPException(403, "Shutdown is only available from the local control panel")
    logger.info("Shutdown requested from local control panel")
    asyncio.create_task(_stop_process())
    return JSONResponse({"ok": True, "message": "Backend is shutting down"})


@app.get("/api/search", response_model=SearchResponse)
async def search(
    q: str = Query(min_length=2, max_length=200),
    limit: int = Query(default=25, ge=1, le=50),
) -> SearchResponse:
    q = q.strip()
    if len(q) < 2:
        raise HTTPException(422, "Search query must contain at least two non-space characters")
    cache_key = _search_cache_key(q)
    cached = await cache.get(cache_key, limit)
    if cached:
        provider, results = cached
        return SearchResponse(
            query=q, provider=provider, cached=True, results=results
        )
    errors: list[str] = []
    for provider in (ytdlp_search, browser_search):
        try:
            results = await provider.search(q, limit)
            if results:
                await cache.put(
                    cache_key, provider.name, results, settings.query_cache_ttl_seconds
                )
                return SearchResponse(
                    query=q, provider=provider.name, cached=False, results=results
                )
            errors.append(f"{provider.name}: no results")
        except Exception as exc:
            message = _error_message(exc)
            logger.warning("%s search failed: %s", provider.name, message)
            errors.append(f"{provider.name}: {message}")
    return SearchResponse(
        query=q,
        provider="none",
        cached=False,
        results=[],
        error="; ".join(errors),
    )


@app.get("/api/vdj/source/search", response_class=PlainTextResponse)
async def vdj_source_search(
    q: str = Query(min_length=2, max_length=200),
    limit: int = Query(default=25, ge=1, le=50),
) -> PlainTextResponse:
    response = await search(q, limit)
    rows = []
    for item in response.results:
        fields = (
            item.videoId,
            item.title,
            item.channelName or "",
            str(item.durationSeconds or 0),
            item.thumbnailUrl or "",
        )
        rows.append("\t".join(field.replace("\t", " ").replace("\r", " ").replace("\n", " ") for field in fields))
    return PlainTextResponse("\n".join(rows))


@app.get("/api/vdj/source/stream/{video_id}", response_class=PlainTextResponse)
async def vdj_source_stream(video_id: str) -> PlainTextResponse:
    resolved = await resolve_video(video_id)
    if not resolved.localStreamUrl:
        raise HTTPException(502, "No local stream URL was resolved")
    return PlainTextResponse(
        resolved.localStreamUrl.replace("/stream/youtube/", "/stream/vdj-source/", 1)
    )


@app.get("/api/resolve/youtube/{video_id}", response_model=ResolveResponse)
async def resolve_video(video_id: str) -> ResolveResponse:
    try:
        stream = await resolver.resolve(video_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        message = _error_message(exc)
        logger.warning("Resolve failed for %s: %s", video_id, message)
        raise HTTPException(502, message) from exc
    return ResolveResponse(
        ok=True,
        videoId=video_id,
        title=stream.title,
        localStreamUrl=stream_url(settings.public_base_url, video_id, stream.title),
        format=stream.format,
        expiresAt=stream.expires_at,
    )


@app.get("/stream/youtube/{video_id}.m4a")
async def youtube_stream(request: Request, video_id: str):
    return await _youtube_stream(request, video_id)


@app.get("/stream/youtube/{video_id}/{filename}")
async def named_youtube_stream(request: Request, video_id: str, filename: str):
    return await _youtube_stream(request, video_id)


@app.get("/stream/vdj-source/{video_id}/{filename}")
async def vdj_source_youtube_stream(request: Request, video_id: str, filename: str):
    return await _youtube_stream(request, video_id, default_range="bytes=0-")


async def _youtube_stream(
    request: Request, video_id: str, default_range: str | None = None
):
    try:
        return await proxy_youtube_stream(
            request,
            video_id,
            resolver,
            default_range=default_range,
            connect_timeout=settings.stream_connect_timeout_seconds,
            read_timeout=settings.stream_read_timeout_seconds,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        message = _error_message(exc)
        logger.warning("Proxy failed for %s: %s", video_id, message)
        raise HTTPException(502, message) from exc
