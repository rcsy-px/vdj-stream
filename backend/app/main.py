import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse

from .config import get_settings
from .db.database import QueryCache
from .logging_config import configure_logging
from .models import ResolveResponse, SearchResponse
from .search.chromium_youtube import ChromiumYouTubeSearchProvider
from .search.ytdlp_search import YtDlpSearchProvider
from .stream.proxy import proxy_youtube_stream
from .stream.naming import stream_url
from .stream.resolver import YtDlpResolver

settings = get_settings()
settings.prepare_directories()
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(settings.playwright_browsers_path))
configure_logging(settings)
logger = logging.getLogger(__name__)

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


def _error_message(exc: Exception) -> str:
    message = str(exc).strip()
    return message or type(exc).__name__


@asynccontextmanager
async def lifespan(_: FastAPI):
    await cache.initialize()
    yield
    await browser_search.close()


app = FastAPI(title="VirtualDJ YouTube Companion", version=settings.version, lifespan=lifespan)


def _health_payload() -> dict:
    chromium_installed = any(settings.playwright_browsers_path.glob("chromium-*"))
    return {
        "ok": True,
        "service": settings.service_name,
        "version": settings.version,
        "tools": {
            "ytDlp": settings.ytdlp_exe.exists(),
            "ffmpeg": (settings.ffmpeg_bin / "ffmpeg.exe").exists(),
            "chromium": chromium_installed,
            "playwrightBrowsersPath": str(settings.playwright_browsers_path),
        },
    }


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def status_page() -> HTMLResponse:
    health = _health_payload()
    tools = health["tools"]
    checks = (
        ("Backend", health["ok"]),
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
    main {{ width: min(420px, calc(100% - 32px)); padding: 28px; background: #1a1d24; border: 1px solid #30343e; border-radius: 16px; box-sizing: border-box; }}
    h1 {{ margin: 0 0 6px; font-size: 22px; }}
    p {{ margin: 0 0 22px; color: #9ca3af; }}
    ul {{ list-style: none; margin: 0; padding: 0; }}
    li {{ display: flex; justify-content: space-between; padding: 11px 0; border-top: 1px solid #30343e; }}
    .ok {{ color: #72db9c; }} .bad {{ color: #ff8585; }}
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
    <h1>VirtualDJ Companion</h1>
    <p>Online Source backend status</p>
    <ul>{rows}</ul>
    <footer>
      Version {health["version"]} · <a href="/api/health">JSON health</a>
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
</body>
</html>"""
    )


@app.get("/api/health")
async def health() -> dict:
    return _health_payload()


@app.get("/api/search", response_model=SearchResponse)
async def search(
    q: str = Query(min_length=2, max_length=200),
    limit: int = Query(default=25, ge=1, le=50),
) -> SearchResponse:
    q = q.strip()
    if len(q) < 2:
        raise HTTPException(422, "Search query must contain at least two non-space characters")
    cached = await cache.get(q)
    if cached:
        provider, results = cached
        return SearchResponse(
            query=q, provider=provider, cached=True, results=results
        )
    errors: list[str] = []
    for provider in (browser_search, ytdlp_search):
        try:
            results = await provider.search(q, limit)
            if results:
                await cache.put(q, provider.name, results, settings.query_cache_ttl_seconds)
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
            request, video_id, resolver, default_range=default_range
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        message = _error_message(exc)
        logger.warning("Proxy failed for %s: %s", video_id, message)
        raise HTTPException(502, message) from exc
