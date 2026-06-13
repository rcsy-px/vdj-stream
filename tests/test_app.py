import time
import tomllib
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.db.database import QueryCache
from backend.app.config import PROJECT_ROOT, PROJECT_VERSION
from backend.app.main import app
from backend.app.models import TrackSearchResult
from backend.app.search.base import youtube_thumbnail_url
from backend.app.stream.formats import ResolvedStream
from backend.app.stream.naming import content_disposition, stream_filename, stream_url
from backend.app.stream.proxy import proxy_youtube_stream


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["ok"] == all(
        response.json()["tools"][name] for name in ("ytDlp", "ffmpeg", "chromium")
    )


def test_status_page() -> None:
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "VirtualDJ Companion" in response.text
    assert "Online Source backend status" in response.text
    assert "https://github.com/rcsy-px" in response.text
    assert "https://ko-fi.com/rycsypx" in response.text


def test_blank_search_is_rejected() -> None:
    with TestClient(app) as client:
        response = client.get("/api/search", params={"q": "  "})
    assert response.status_code == 422


def test_blank_vdj_source_search_is_rejected() -> None:
    with TestClient(app) as client:
        response = client.get("/api/vdj/source/search", params={"q": " "})
    assert response.status_code == 422


def test_stream_name_uses_youtube_title() -> None:
    title = 'Basshunter - Now You\'re Gone (Official Video)'
    assert stream_filename(title, "abcdefghijk") == f"{title}.m4a"
    assert stream_url("http://127.0.0.1:8765", "abcdefghijk", title).endswith(
        "/Basshunter%20-%20Now%20You%27re%20Gone%20%28Official%20Video%29.m4a"
    )
    assert "Basshunter - Now You're Gone" in content_disposition(title, "abcdefghijk")


def test_youtube_thumbnail_fallback() -> None:
    assert youtube_thumbnail_url("abcdefghijk") == (
        "https://i.ytimg.com/vi/abcdefghijk/hqdefault.jpg"
    )


def test_project_versions_match() -> None:
    project = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["version"] == PROJECT_VERSION


def test_vdj_source_stream_uses_dedicated_range_route(monkeypatch) -> None:
    async def fake_resolve_video(video_id: str):
        from backend.app.models import ResolveResponse

        return ResolveResponse(
            ok=True,
            videoId=video_id,
            localStreamUrl=(
                f"http://127.0.0.1:8765/stream/youtube/{video_id}/Track.m4a"
            ),
        )

    monkeypatch.setattr("backend.app.main.resolve_video", fake_resolve_video)
    with TestClient(app) as client:
        response = client.get("/api/vdj/source/stream/abcdefghijk")
    assert response.status_code == 200
    assert response.text == (
        "http://127.0.0.1:8765/stream/vdj-source/abcdefghijk/Track.m4a"
    )


@pytest.mark.asyncio
async def test_query_cache_misses_when_cached_result_count_is_too_small(
    tmp_path: Path,
) -> None:
    cache = QueryCache(tmp_path / "cache.sqlite3", Path("backend/app/db/schema.sql"))
    await cache.initialize()
    result = TrackSearchResult(
        id="youtube:abcdefghijk",
        provider="test",
        videoId="abcdefghijk",
        title="Track",
        watchUrl="https://www.youtube.com/watch?v=abcdefghijk",
    )
    await cache.put("track", "test", [result], ttl=60)

    assert await cache.get("track", limit=2) is None
    cached = await cache.get("track", limit=1)
    assert cached is not None
    assert len(cached[1]) == 1


class FakeResolver:
    def __init__(self) -> None:
        self.calls: list[bool] = []

    async def resolve(self, video_id: str, force: bool = False) -> ResolvedStream:
        self.calls.append(force)
        return ResolvedStream(
            video_id=video_id,
            title="Track",
            upstream_url="https://audio.example/track",
        )


@pytest.mark.asyncio
async def test_proxy_defaults_range_and_refreshes_expired_url(monkeypatch) -> None:
    resolver = FakeResolver()
    statuses = iter((403, 206))
    seen_ranges: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_ranges.append(request.headers.get("range"))
        status = next(statuses)
        return httpx.Response(
            status,
            headers={
                "content-type": "audio/mp4",
                "content-range": "bytes 0-3/4",
                "accept-ranges": "bytes",
            },
            content=b"data",
        )

    class MockAsyncClient(httpx.AsyncClient):
        def __init__(self, **kwargs):
            super().__init__(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr("backend.app.stream.proxy.httpx.AsyncClient", MockAsyncClient)
    request = httpx.Request("GET", "http://127.0.0.1/stream")
    response = await proxy_youtube_stream(
        request, "abcdefghijk", resolver, default_range="bytes=0-"
    )
    body = b"".join([chunk async for chunk in response.body_iterator])

    assert response.status_code == 206
    assert body == b"data"
    assert seen_ranges == ["bytes=0-", "bytes=0-"]
    assert resolver.calls == [False, True]


@pytest.mark.asyncio
async def test_proxy_rejects_upstream_error(monkeypatch) -> None:
    resolver = FakeResolver()

    class MockAsyncClient(httpx.AsyncClient):
        def __init__(self, **kwargs):
            super().__init__(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(500, request=request)
                ),
                **kwargs,
            )

    monkeypatch.setattr("backend.app.stream.proxy.httpx.AsyncClient", MockAsyncClient)
    request = httpx.Request("GET", "http://127.0.0.1/stream")
    with pytest.raises(Exception, match="Upstream audio server returned HTTP 500"):
        await proxy_youtube_stream(request, "abcdefghijk", resolver)


def test_search_falls_back_to_ytdlp(monkeypatch) -> None:
    async def browser_failure(query: str, limit: int):
        raise RuntimeError("browser unavailable")

    async def ytdlp_success(query: str, limit: int):
        return [
            TrackSearchResult(
                id="youtube:abcdefghijk",
                provider="ytdlp_search",
                videoId="abcdefghijk",
                title="Fallback result",
                watchUrl="https://www.youtube.com/watch?v=abcdefghijk",
            )
        ]

    async def cache_miss(query: str, limit: int):
        return None

    monkeypatch.setattr("backend.app.main.browser_search.search", browser_failure)
    monkeypatch.setattr("backend.app.main.ytdlp_search.search", ytdlp_success)
    monkeypatch.setattr("backend.app.main.cache.get", cache_miss)
    with TestClient(app) as client:
        response = client.get("/api/search", params={"q": "fallback test"})

    assert response.status_code == 200
    assert response.json()["provider"] == "ytdlp_search"
    assert response.json()["results"][0]["title"] == "Fallback result"
