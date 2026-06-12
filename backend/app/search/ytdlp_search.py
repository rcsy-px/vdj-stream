import asyncio
import json
from pathlib import Path

from ..models import TrackSearchResult
from .base import SearchProvider, duration_to_seconds, youtube_thumbnail_url


class YtDlpSearchProvider(SearchProvider):
    name = "ytdlp_search"

    def __init__(self, executable: Path, timeout_seconds: float = 45):
        self.executable = executable
        self.timeout_seconds = timeout_seconds

    async def search(self, query: str, limit: int) -> list[TrackSearchResult]:
        if not self.executable.exists():
            raise RuntimeError(
                "yt-dlp is missing. Run scripts/bootstrap-tools.ps1 first."
            )
        process = await asyncio.create_subprocess_exec(
            str(self.executable),
            "--dump-json",
            "--flat-playlist",
            "--no-warnings",
            f"ytsearch{limit}:{query}",
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
            raise RuntimeError("yt-dlp search timed out")
        if process.returncode:
            message = stderr.decode(errors="replace").strip().splitlines()
            raise RuntimeError(message[-1] if message else "yt-dlp search failed")

        results: list[TrackSearchResult] = []
        seen: set[str] = set()
        for line in stdout.decode("utf-8", errors="replace").splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            video_id = item.get("id")
            title = item.get("title")
            if not video_id or not title or video_id in seen:
                continue
            seen.add(video_id)
            duration = item.get("duration")
            duration_text = item.get("duration_string")
            if not duration_text and duration:
                minutes, seconds = divmod(int(duration), 60)
                duration_text = f"{minutes}:{seconds:02d}"
            thumbnails = item.get("thumbnails") or []
            thumbnail = item.get("thumbnail") or (
                thumbnails[-1].get("url") if thumbnails else None
            )
            results.append(
                TrackSearchResult(
                    id=f"youtube:{video_id}",
                    provider=self.name,
                    videoId=video_id,
                    title=title,
                    channelName=item.get("channel") or item.get("uploader"),
                    channelUrl=item.get("channel_url") or item.get("uploader_url"),
                    durationText=duration_text,
                    durationSeconds=int(duration)
                    if duration
                    else duration_to_seconds(duration_text),
                    thumbnailUrl=thumbnail or youtube_thumbnail_url(video_id),
                    watchUrl=f"https://www.youtube.com/watch?v={video_id}",
                    badges=["yt-dlp-fallback"],
                )
            )
        return results[:limit]
