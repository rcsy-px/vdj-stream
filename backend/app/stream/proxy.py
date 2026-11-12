from collections.abc import AsyncIterator

import anyio
import httpx
from fastapi import HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from .naming import content_disposition
from .resolver import YtDlpResolver

PASSTHROUGH_HEADERS = (
    "content-type", "content-length", "content-range", "accept-ranges", "content-encoding",
)


class ManagedStreamResponse(StreamingResponse):
    """Close upstream even if ASGI disconnects before iterating the response body."""
    def __init__(self, *args, cleanup, **kwargs):
        super().__init__(*args, **kwargs)
        self.cleanup = cleanup

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self.cleanup()


async def proxy_youtube_stream(
    request: Request,
    video_id: str,
    resolver: YtDlpResolver,
    default_range: str | None = None,
    connect_timeout: float = 10.0,
    read_timeout: float = 30.0,
) -> Response:
    range_header = request.headers.get("range") or default_range
    response = None
    client = None

    async def close():
        with anyio.CancelScope(shield=True):
            try:
                if response is not None:
                    await response.aclose()
            finally:
                if client is not None:
                    await client.aclose()

    try:
        for attempt in range(2):
            stream = await resolver.resolve(video_id, force=attempt > 0)
            headers = {**stream.http_headers, "Accept-Encoding": "identity"}
            if range_header:
                headers["Range"] = range_header
            timeout = httpx.Timeout(
                connect=connect_timeout, read=read_timeout,
                write=connect_timeout, pool=connect_timeout,
            )
            client = httpx.AsyncClient(follow_redirects=True, timeout=timeout)
            upstream_request = client.build_request("GET", stream.upstream_url, headers=headers)
            response = await client.send(upstream_request, stream=True)
            if response.status_code not in (403, 410) or attempt == 1:
                break
            await close()
            response = None
            client = None

        if response.status_code == 416:
            headers = {"Content-Range": response.headers["content-range"]} if "content-range" in response.headers else {}
            await close()
            return Response(status_code=416, headers=headers)
        if response.status_code >= 400:
            raise HTTPException(502, f"Upstream audio server returned HTTP {response.status_code}")

        headers = {
            key.title(): value for key in PASSTHROUGH_HEADERS
            if (value := response.headers.get(key)) is not None
        }
        headers["Content-Disposition"] = content_disposition(stream.title, video_id, stream.format.ext or "m4a")

        async def body() -> AsyncIterator[bytes]:
            try:
                if response.is_stream_consumed:
                    yield response.content
                else:
                    async for chunk in response.aiter_raw():
                        yield chunk
            finally:
                await close()

        return ManagedStreamResponse(
            body(), cleanup=close,
            status_code=206 if response.status_code == 206 else 200,
            media_type=response.headers.get("content-type", "application/octet-stream"),
            headers=headers,
        )
    except BaseException:
        await close()
        raise
