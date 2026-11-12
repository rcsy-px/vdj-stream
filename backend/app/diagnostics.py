import asyncio
import time

import httpx
from fastapi import HTTPException

from .logging_config import _redact
from .stream.proxy import proxy_youtube_stream


class Diagnostics:
    def __init__(self, search, browser, resolver, updates):
        self.search = search
        self.browser = browser
        self.resolver = resolver
        self.updates = updates
        self._lock = asyncio.Lock()

    @property
    def running(self):
        return self._lock.locked()

    async def run(self):
        async with self._lock:
            checks = []

            async def step(name, action, timeout=25):
                started = time.monotonic()
                record = {"name": name, "ok": False}
                try:
                    async with asyncio.timeout(timeout):
                        value, message = await action()
                    record.update(ok=True, message=message)
                    return value
                except Exception as exc:
                    message = "Timed out. Check your internet connection." if isinstance(exc, TimeoutError) else (
                        str(exc.detail) if isinstance(exc, HTTPException) else str(exc)
                    )
                    record["message"] = _redact(message)[:500] or type(exc).__name__
                    return None
                finally:
                    record["durationMs"] = round((time.monotonic() - started) * 1000)
                    checks.append(record)

            async def version():
                installed = await self.updates.installed_version()
                return installed, f"Installed yt-dlp: {installed}"

            async def search(provider):
                results = await provider.search("Daft Punk One More Time", 3)
                if not results:
                    raise RuntimeError("The test search returned no tracks.")
                return results[0].videoId, f"Test search returned {len(results)} tracks."

            await step("YouTube engine", version)
            video_id = await step("YouTube search", lambda: search(self.search))
            fallback_id = await step("Chromium fallback", lambda: search(self.browser))
            video_id = video_id or fallback_id

            async def resolve():
                stream = await self.resolver.resolve(video_id, force=True)
                return stream, f"Audio source resolved ({stream.format.ext or 'unknown format'})."

            async def audio():
                request = httpx.Request("GET", "http://127.0.0.1/diagnostic-probe", headers={"Range": "bytes=0-1023"})
                response = await proxy_youtube_stream(request, video_id, self.resolver)
                if response.status_code not in (200, 206):
                    raise RuntimeError(f"Audio probe returned HTTP {response.status_code}.")
                try:
                    async for chunk in response.body_iterator:
                        if chunk:
                            return True, f"Audio bytes received (HTTP {response.status_code})."
                    raise RuntimeError("Audio server returned an empty response.")
                finally:
                    await response.cleanup()

            if video_id:
                resolved = await step("Audio resolution", resolve, timeout=55)
                if resolved:
                    await step("Audio delivery", audio, timeout=30)
                else:
                    checks.append({"name": "Audio delivery", "ok": False, "message": "Skipped: audio resolution failed."})
            else:
                checks.append({"name": "Audio resolution", "ok": False, "message": "Skipped: neither search provider returned a track."})
            return {"ok": all(check["ok"] for check in checks), "checks": checks}
