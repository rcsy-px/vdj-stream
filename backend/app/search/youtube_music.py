"""Public YouTube Music search, isolated so cancellation also stops HTTP work."""
import asyncio
import json
from pathlib import Path
import sys
import subprocess

from ..library import ID
from ..models import TrackSearchResult
from .base import SearchProvider, duration_to_seconds, youtube_thumbnail_url


class YouTubeMusicSearchProvider(SearchProvider):
    def __init__(self, category, timeout_seconds=20, slots=None):
        if category not in ('songs', 'videos'):
            raise ValueError('Choose songs or videos.')
        self.category = category
        self.name = 'youtube_music_' + category
        self.timeout_seconds = timeout_seconds
        self.slots = slots if slots is not None else asyncio.Semaphore(2)

    async def search(self, query, limit):
        async with asyncio.timeout(self.timeout_seconds), self.slots:
            # ytmusicapi uses synchronous HTTP. A worker makes the whole request
            # bounded, including pagination, and avoids stranded executor threads.
            process = await asyncio.create_subprocess_exec(
                sys.executable, '-m', 'backend.app.search.youtube_music',
                self.category, str(limit), query,
                cwd=Path(__file__).resolve().parents[3],
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                **({'creationflags': subprocess.CREATE_NO_WINDOW} if sys.platform == 'win32' else {}),
            )
            try:
                output, _ = await process.communicate()
            except BaseException:
                if process.returncode is None:
                    try:
                        process.kill()
                    except ProcessLookupError:
                        pass
                await process.communicate()
                raise
            if process.returncode:
                raise RuntimeError('YouTube Music search failed. Retry or select YouTube in Search source.')
            return self.parse(json.loads(output), limit)

    def parse(self, items, limit):
        results, seen = [], set()
        for item in items:
            video_id = item.get('videoId') or ''
            title = (item.get('title') or '').strip()
            expected = 'song' if self.category == 'songs' else 'video'
            if (not ID.fullmatch(video_id) or not title or video_id in seen
                    or item.get('resultType') != expected or item.get('isAvailable') is False):
                continue
            seen.add(video_id)
            artists = ', '.join(a['name'] for a in item.get('artists', []) if a.get('name'))
            thumbnails = item.get('thumbnails') or []
            duration = item.get('duration_seconds')
            results.append(TrackSearchResult(
                id='youtube:' + video_id, videoId=video_id, provider=self.name,
                title=title, channelName=artists or None,
                durationText=item.get('duration'),
                durationSeconds=duration if isinstance(duration, int) and duration >= 0 else duration_to_seconds(item.get('duration')),
                thumbnailUrl=(thumbnails[-1].get('url') if thumbnails else None) or youtube_thumbnail_url(video_id),
                watchUrl='https://www.youtube.com/watch?v=' + video_id,
                badges=['YouTube Music', self.category],
            ))
            if len(results) >= limit:
                break
        return results


if __name__ == '__main__':
    from ytmusicapi import YTMusic
    category, limit, query = sys.argv[1:]
    if category not in ('songs', 'videos') or not 1 <= int(limit) <= 50:
        raise SystemExit('Invalid search options')
    # No account, browser cookies or user library access is needed.
    items = YTMusic().search(query, filter=category, limit=int(limit))
    sys.stdout.buffer.write(json.dumps(items, ensure_ascii=False).encode('utf-8'))
