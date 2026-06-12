from collections.abc import AsyncIterator

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse

from .naming import content_disposition
from .resolver import YtDlpResolver

PASSTHROUGH_HEADERS = ("content-type", "content-length", "content-range", "accept-ranges")


async def proxy_youtube_stream(
    request: Request,
    video_id: str,
    resolver: YtDlpResolver,
    default_range: str | None = None,
) -> StreamingResponse:
    range_header = request.headers.get("range") or default_range
    response: httpx.Response | None = None
    client: httpx.AsyncClient | None = None
    for attempt in range(2):
        stream = await resolver.resolve(video_id, force=attempt > 0)
        headers = dict(stream.http_headers)
        if range_header:
            headers["Range"] = range_header
        client = httpx.AsyncClient(follow_redirects=True, timeout=None)
        upstream_request = client.build_request("GET", stream.upstream_url, headers=headers)
        response = await client.send(upstream_request, stream=True)
        if response.status_code not in (403, 410) or attempt == 1:
            break
        await response.aclose()
        await client.aclose()

    if response is None or client is None:
        raise HTTPException(502, "Unable to connect to upstream stream")
    if response.status_code >= 400:
        status = response.status_code
        await response.aclose()
        await client.aclose()
        raise HTTPException(502, f"Upstream audio server returned HTTP {status}")

    async def body() -> AsyncIterator[bytes]:
        try:
            async for chunk in response.aiter_bytes():
                yield chunk
        finally:
            await response.aclose()
            await client.aclose()

    headers = {
        key.title(): value
        for key in PASSTHROUGH_HEADERS
        if (value := response.headers.get(key)) is not None
    }
    headers["Content-Disposition"] = content_disposition(stream.title, video_id)
    return StreamingResponse(
        body(),
        status_code=206 if response.status_code == 206 else 200,
        media_type=response.headers.get("content-type", "audio/mp4"),
        headers=headers,
    )
