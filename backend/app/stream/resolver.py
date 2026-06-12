import asyncio
import json
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from ..models import ResolvedFormat
from .formats import ResolvedStream

VIDEO_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{11}$")


class YtDlpResolver:
    def __init__(self, executable: Path, timeout_seconds: float = 45, ttl: int = 1200):
        self.executable = executable
        self.timeout_seconds = timeout_seconds
        self.ttl = ttl
        self._cache: dict[str, tuple[int, ResolvedStream]] = {}

    async def resolve(self, video_id: str, force: bool = False) -> ResolvedStream:
        if not VIDEO_ID_PATTERN.fullmatch(video_id):
            raise ValueError("Invalid YouTube video ID")
        cached = self._cache.get(video_id)
        if cached and cached[0] > int(time.time()) and not force:
            return cached[1]
        if not self.executable.exists():
            raise RuntimeError(
                "yt-dlp is missing. Run scripts/bootstrap-tools.ps1 first."
            )
        process = await asyncio.create_subprocess_exec(
            str(self.executable),
            "--dump-single-json",
            "--no-playlist",
            "--no-warnings",
            "-f",
            "bestaudio[ext=m4a]/bestaudio",
            f"https://www.youtube.com/watch?v={video_id}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self.timeout_seconds
            )
        except TimeoutError:
            process.kill()
            await process.communicate()
            raise RuntimeError("yt-dlp resolve timed out")
        if process.returncode:
            lines = stderr.decode(errors="replace").strip().splitlines()
            raise RuntimeError(lines[-1] if lines else "yt-dlp resolve failed")
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
                ext=info.get("ext"),
                acodec=info.get("acodec"),
                abr=info.get("abr"),
            ),
            expires_at=expires,
        )
        cache_until = min(expires or int(time.time()) + self.ttl, int(time.time()) + self.ttl)
        self._cache[video_id] = (cache_until, stream)
        return stream

    @staticmethod
    def _expiry_from_url(url: str) -> int | None:
        value = parse_qs(urlparse(url).query).get("expire", [None])[0]
        return int(value) if value and value.isdigit() else None
