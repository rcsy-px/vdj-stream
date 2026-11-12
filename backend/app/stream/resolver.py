import asyncio
import json
import re
import time
from pathlib import Path
from collections import OrderedDict
from urllib.parse import parse_qs, urlparse

from ..models import ResolvedFormat
from .formats import ResolvedStream
from .naming import audio_extension
from ..ytdlp_runner import YtDlpRunner

VIDEO_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{11}$")


class YtDlpResolver:
    def __init__(self, executable: Path, timeout_seconds: float = 45, ttl: int = 1200,
                 runner: YtDlpRunner | None = None, max_cache_entries: int = 256):
        self.executable = executable
        self.runner = runner or YtDlpRunner(executable)
        self.max_cache_entries = max_cache_entries
        self.timeout_seconds = timeout_seconds
        self.ttl = ttl
        self._cache: OrderedDict[str, tuple[int, ResolvedStream]] = OrderedDict()
        self._locks: dict[str, tuple[asyncio.Lock, int]] = {}

    def clear_cache(self) -> None:
        self._cache.clear()

    async def resolve(self, video_id: str, force: bool = False) -> ResolvedStream:
        if not VIDEO_ID_PATTERN.fullmatch(video_id):
            raise ValueError("Invalid YouTube video ID")
        lock, users = self._locks.get(video_id, (asyncio.Lock(), 0))
        self._locks[video_id] = (lock, users + 1)
        try:
            async with lock:
                return await self._resolve_locked(video_id, force)
        finally:
            _, users = self._locks[video_id]
            if users == 1:
                del self._locks[video_id]
            else:
                self._locks[video_id] = (lock, users - 1)

    async def _resolve_locked(self, video_id: str, force: bool) -> ResolvedStream:
        now = int(time.time())
        for key, (expiry, _) in list(self._cache.items()):
            if expiry <= now:
                del self._cache[key]
        cached = self._cache.get(video_id)
        if cached and cached[0] > int(time.time()) and not force:
            self._cache.move_to_end(video_id)
            return cached[1]
        stdout = await self.runner.run(
            "--dump-single-json", "--no-playlist", "--no-warnings",
            "-f", "bestaudio[ext=m4a]/bestaudio",
            f"https://www.youtube.com/watch?v={video_id}",
            timeout=self.timeout_seconds,
        )
        info = json.loads(stdout)
        upstream_url = info.get("url")
        if not upstream_url:
            raise RuntimeError("yt-dlp did not return a playable audio URL")
        expires = self._expiry_from_url(upstream_url)
        stream = ResolvedStream(
            video_id=video_id,
            title=info.get("title") or video_id,
            upstream_url=upstream_url,
            http_headers={
                str(key): str(value)
                for key, value in (info.get("http_headers") or {}).items()
                if key.lower() not in {"cookie", "authorization"}
            },
            format=ResolvedFormat(
                formatId=str(info.get("format_id")) if info.get("format_id") else None,
                ext=audio_extension(info.get("ext") or "m4a"),
                acodec=info.get("acodec"),
                abr=info.get("abr"),
            ),
            expires_at=expires,
        )
        cache_until = min(expires or int(time.time()) + self.ttl, int(time.time()) + self.ttl)
        self._cache[video_id] = (cache_until, stream)
        self._cache.move_to_end(video_id)
        while len(self._cache) > self.max_cache_entries:
            self._cache.popitem(last=False)
        return stream

    @staticmethod
    def _expiry_from_url(url: str) -> int | None:
        value = parse_qs(urlparse(url).query).get("expire", [None])[0]
        return int(value) if value and value.isdigit() else None
