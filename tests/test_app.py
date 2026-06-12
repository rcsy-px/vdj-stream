from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.search.base import youtube_thumbnail_url
from backend.app.stream.naming import content_disposition, stream_filename, stream_url


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["ok"] is True


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
