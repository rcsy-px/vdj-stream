import asyncio
import logging
import os
import secrets
import signal
import time
import sys
import json
import httpx
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse, Response

from .config import get_settings
from .browser_tools import chromium_executable
from .ytdlp_runner import YtDlpRunner, YtDlpBusyError
from .diagnostics import Diagnostics
from .db.database import QueryCache
from .logging_config import configure_logging
from .models import ResolveResponse, SearchResponse
from .search.chromium_youtube import ChromiumYouTubeSearchProvider
from .search.ytdlp_search import YtDlpSearchProvider
from .search.youtube_music import YouTubeMusicSearchProvider
from .stream.proxy import proxy_youtube_stream
from .stream.naming import stream_url
from .stream.resolver import YtDlpResolver
from .update_checker import GitHubReleaseChecker
from .ytdlp_updates import YtDlpUpdates
from .macos_releases import MacReleaseChecker
from .macos_updates import MacAppUpdates
from .windows_updates import WindowsAppUpdates
from .library import Library, track_parts
from .library_api import routes as library_routes
from urllib.parse import quote

settings = get_settings()
settings.prepare_directories()
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(settings.playwright_browsers_path))
live_logs = configure_logging(settings)
logger = logging.getLogger(__name__)
started_at = int(time.time())
shutdown_token = secrets.token_urlsafe(24)

cache = QueryCache(settings.database_path, Path(__file__).parent / "db" / "schema.sql")
browser_search = ChromiumYouTubeSearchProvider(
    headless=settings.headless, timeout_seconds=settings.search_timeout_seconds,
    browser_root=settings.playwright_browsers_path
)
ytdlp_runner = YtDlpRunner(settings.ytdlp_exe)
ytdlp_search = YtDlpSearchProvider(settings.ytdlp_exe, settings.search_timeout_seconds, runner=ytdlp_runner)
music_slots = asyncio.Semaphore(2)
music_search = {source: YouTubeMusicSearchProvider(category, settings.search_timeout_seconds, music_slots)
                for source, category in [('music_songs', 'songs'), ('music_videos', 'videos')]}
resolver = YtDlpResolver(
    settings.ytdlp_exe,
    settings.resolve_timeout_seconds,
    settings.resolve_cache_ttl_seconds,
    runner=ytdlp_runner,
)
update_checker = (MacReleaseChecker if sys.platform == 'darwin' else GitHubReleaseChecker)(
    settings.version,
    settings.github_repository,
    settings.update_check_cache_ttl_seconds,
    settings.update_check_timeout_seconds,
)
app_updates = (WindowsAppUpdates if sys.platform == 'win32' else MacAppUpdates)(Path(__file__).resolve().parents[2], update_checker)
ytdlp_updates = YtDlpUpdates(settings.ytdlp_exe, runner=ytdlp_runner)
diagnostics = Diagnostics(ytdlp_search, browser_search, resolver, ytdlp_updates)
library = Library(settings.data_dir / 'library', ytdlp_runner, settings.ffmpeg_bin)
library.initialize()


def _error_message(exc: Exception) -> str:
    message = str(exc).strip()
    return message or type(exc).__name__


@asynccontextmanager
async def lifespan(_: FastAPI):
    await cache.initialize()
    await library.start()
    yield
    await library.close()
    await browser_search.close()


app = FastAPI(title="VirtualDJ YouTube Companion", version=settings.version, lifespan=lifespan)
app.include_router(library_routes(library, shutdown_token, lambda: app_updates.in_progress))
LOGO_PATH = settings.data_dir.parent / "docs" / "assets" / "companion-bot.png"
WEB_ROOT = Path(__file__).parent / "web"
app.mount("/static", StaticFiles(directory=WEB_ROOT), name="static")
SEARCH_CACHE_NAMESPACE = "v2-ytdlp-primary"


def _search_cache_key(query: str, source: str = 'youtube') -> str:
    return f"{SEARCH_CACHE_NAMESPACE}:{source}:{query}"


def _health_payload() -> dict:
    chromium_installed = chromium_executable(settings.playwright_browsers_path) is not None
    tools = {
        "ytDlp": settings.ytdlp_exe.exists(),
        "ffmpeg": (settings.ffmpeg_bin / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")).exists(),
        "chromium": chromium_installed,
        "playwrightBrowsersPath": str(settings.playwright_browsers_path),
    }
    result = {
        "ok": tools["ytDlp"] and tools["ffmpeg"] and tools["chromium"],
        "service": settings.service_name,
        "version": settings.version,
        "startedAt": started_at,
        "uptimeSeconds": max(0, int(time.time()) - started_at),
        "tools": tools,
    }
    if sys.platform in ('darwin', 'win32'):
        try:
            platform_name = 'windows' if sys.platform == 'win32' else 'macos'
            result['appUpdateResult'] = json.loads((settings.data_dir / f'{platform_name}-update-result.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            pass
    return result


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def status_page() -> HTMLResponse:
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    html = html.replace("__CONTROL_TOKEN__", shutdown_token)
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


@app.get("/assets/logo.png", response_class=FileResponse, include_in_schema=False)
async def logo() -> FileResponse:
    return FileResponse(LOGO_PATH, media_type="image/png")


@app.get("/assets/logo.svg", response_class=FileResponse, include_in_schema=False)
async def framed_logo() -> FileResponse:
    return FileResponse(LOGO_PATH.with_suffix(".svg"), media_type="image/svg+xml")


@app.get("/api/health")
async def health() -> dict:
    return _health_payload()


@app.get("/api/update", include_in_schema=False)
async def update_status(response: Response, refresh: bool = False) -> dict:
    response.headers["Cache-Control"] = "no-store"
    result = dict(await update_checker.check(force=refresh))
    result['canInstall'] = app_updates.supported and bool(result.get('downloadUrl') and result.get('checksumUrl'))
    return result


@app.post('/api/update/install', include_in_schema=False)
async def install_app_update(request: Request):
    if not _is_loopback(request) or request.headers.get('x-shutdown-token') != shutdown_token:
        raise HTTPException(403, 'Updates are only available from the local control panel')
    if not app_updates.supported:
        raise HTTPException(409, 'Start Companion with its START launcher to install updates.')
    if diagnostics.running or ytdlp_updates._update_lock.locked() or library.tasks:
        raise HTTPException(409, 'Wait for diagnostics or the yt-dlp update to finish.')
    try:
        result = await app_updates.prepare()
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        logger.warning('Could not prepare app update: %s', exc)
        raise HTTPException(502, 'Could not download or verify the update. Nothing was installed.') from exc
    asyncio.create_task(_stop_process())
    return {'ok': True, 'id': result['id'], 'version': result['version']}


@app.get("/api/ytdlp", include_in_schema=False)
async def ytdlp_status(response: Response, refresh: bool = False) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return await ytdlp_updates.check(force=refresh)


@app.post("/api/ytdlp/update", include_in_schema=False)
async def update_ytdlp(request: Request) -> dict:
    if not _is_loopback(request) or request.headers.get("x-shutdown-token") != shutdown_token:
        raise HTTPException(403, "Updates are only available from the local control panel")
    if app_updates.in_progress:
        raise HTTPException(409, 'An application update is running.')
    if library.tasks:
        raise HTTPException(409, 'Finish or cancel library downloads before updating yt-dlp.')
    try:
        result = await ytdlp_updates.update()
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc
    resolver.clear_cache()
    return result


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
    await library.close()
    callback = getattr(app.state, 'request_shutdown', None)
    if callback:
        callback()
        return
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
    try:
        async with asyncio.timeout(settings.request_timeout_seconds):
            return await _search(q, limit)
    except YtDlpBusyError as exc:
        raise HTTPException(503, str(exc), headers={"Retry-After": "5"}) from exc
    except TimeoutError as exc:
        raise HTTPException(504, "Search timed out. Please try again.") from exc


async def _search(q: str, limit: int) -> SearchResponse:
    q = q.strip()
    if len(q) < 2:
        raise HTTPException(422, "Search query must contain at least two non-space characters")
    source = library.search_source()
    cache_key = _search_cache_key(q, source)
    cached = await cache.get(cache_key, limit)
    if cached:
        provider, results = cached
        return SearchResponse(
            query=q, provider=provider, cached=True, results=results
        )
    errors: list[str] = []
    completed = False
    providers = (ytdlp_search, browser_search) if source == 'youtube' else (music_search[source],)
    for provider in providers:
        try:
            results = await asyncio.wait_for(provider.search(q, limit), settings.search_timeout_seconds)
            completed = True
            if results:
                await cache.put(
                    cache_key, provider.name, results, settings.query_cache_ttl_seconds
                )
                return SearchResponse(
                    query=q, provider=provider.name, cached=False, results=results
                )
        except YtDlpBusyError:
            raise
        except Exception as exc:
            message = _error_message(exc)
            logger.warning("%s search failed: %s", provider.name, message)
            errors.append(f"{provider.name}: {message}")
    return SearchResponse(
        query=q,
        provider="none",
        cached=False,
        results=[],
        error="; ".join(errors) if not completed else None,
    )


@app.get("/api/vdj/source/search", response_class=PlainTextResponse)
async def vdj_source_search(
    q: str = Query(min_length=2, max_length=200),
    limit: int = Query(default=25, ge=1, le=50),
) -> PlainTextResponse:
    response = await search(q, limit)
    if response.error:
        return PlainTextResponse("Search failed. Check Live logs or change Search source in Companion.", status_code=502)
    library.remember_search(q, response.results)
    return PlainTextResponse(library.tsv('last-search'))


@app.get("/api/vdj/source/stream/{video_id}", response_class=PlainTextResponse)
async def vdj_source_stream(video_id: str) -> PlainTextResponse:
    try:
        _, video = track_parts(video_id)
        saved = library.media(video_id)
        if not video and not saved:
            saved = await library.recover_media(video_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if video and not saved:
        try:
            saved = await library.prepare_video(video_id)
        except TimeoutError as exc:
            raise HTTPException(409, str(exc))
        except ValueError as exc:
            raise HTTPException(503, str(exc))
        except RuntimeError as exc:
            raise HTTPException(502, str(exc))
    if saved:
        return PlainTextResponse(f'{settings.public_base_url}/stream/library/{quote(video_id)}/{quote(saved.name)}')
    resolved = await resolve_video(video_id)
    if not resolved.localStreamUrl:
        raise HTTPException(502, "No local stream URL was resolved")
    return PlainTextResponse(
        resolved.localStreamUrl.replace("/stream/youtube/", "/stream/vdj-source/", 1)
    )


@app.get("/api/resolve/youtube/{video_id}", response_model=ResolveResponse)
async def resolve_video(video_id: str) -> ResolveResponse:
    try:
        async with asyncio.timeout(settings.request_timeout_seconds):
            stream = await resolver.resolve(video_id)
    except YtDlpBusyError as exc:
        raise HTTPException(503, str(exc), headers={"Retry-After": "5"}) from exc
    except TimeoutError as exc:
        raise HTTPException(504, "Track resolution timed out. Please try again.") from exc
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
        localStreamUrl=stream_url(settings.public_base_url, video_id, stream.title, stream.format.ext or "m4a"),
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
        async with asyncio.timeout(settings.request_timeout_seconds):
            return await proxy_youtube_stream(
                request, video_id, resolver, default_range=default_range,
                connect_timeout=settings.stream_connect_timeout_seconds,
                read_timeout=settings.stream_read_timeout_seconds,
            )
    except YtDlpBusyError as exc:
        raise HTTPException(503, str(exc), headers={"Retry-After": "5"}) from exc
    except (TimeoutError, httpx.TimeoutException) as exc:
        raise HTTPException(504, "Audio server timed out. Please reload the track.") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except HTTPException as exc:
        if exc.status_code >= 500:
            logger.warning("Proxy failed for %s (HTTP %s): %s", video_id, exc.status_code, exc.detail)
        raise
    except Exception as exc:
        message = _error_message(exc)
        logger.warning("Proxy failed for %s: %s", video_id, message)
        raise HTTPException(502, message) from exc


@app.post("/api/diagnostics", include_in_schema=False)
async def run_diagnostics(request: Request) -> dict:
    if app_updates.in_progress:
        raise HTTPException(409, 'An application update is running.')
    if not _is_loopback(request) or request.headers.get("x-shutdown-token") != shutdown_token:
        raise HTTPException(403, "Diagnostics are only available from the local control panel")
    if diagnostics.running:
        raise HTTPException(409, "Diagnostics are already running")
    return await diagnostics.run()
