import json
import time
from pathlib import Path

import aiosqlite

from ..models import TrackSearchResult
from ..search.base import youtube_thumbnail_url


class QueryCache:
    def __init__(self, database_path: Path, schema_path: Path):
        self.database_path = database_path
        self.schema_path = schema_path

    async def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.database_path) as db:
            await db.executescript(self.schema_path.read_text(encoding="utf-8"))
            now = int(time.time())
            await db.execute(
                "DELETE FROM query_cache WHERE created_at + ttl_seconds < ?", (now,)
            )
            await db.execute(
                "DELETE FROM video_metadata WHERE last_seen < ?", (now - 30 * 86400,)
            )
            await db.commit()

    async def get(
        self, query: str, limit: int | None = None
    ) -> tuple[str, list[TrackSearchResult]] | None:
        normalized = self._normalize(query)
        async with aiosqlite.connect(self.database_path) as db:
            cursor = await db.execute(
                "SELECT provider, results_json, created_at, ttl_seconds "
                "FROM query_cache WHERE query = ?",
                (normalized,),
            )
            row = await cursor.fetchone()
        if not row or row[2] + row[3] < int(time.time()):
            return None
        results = [
            TrackSearchResult.model_validate(
                {
                    **item,
                    "thumbnailUrl": item.get("thumbnailUrl")
                    or youtube_thumbnail_url(item["videoId"]),
                    "cached": True,
                }
            )
            for item in json.loads(row[1])
        ]
        if limit is not None and len(results) < limit:
            return None
        return row[0], results[:limit] if limit is not None else results

    async def put(
        self, query: str, provider: str, results: list[TrackSearchResult], ttl: int
    ) -> None:
        now = int(time.time())
        payload = json.dumps(
            [result.model_dump() for result in results], ensure_ascii=False
        )
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO query_cache VALUES (?, ?, ?, ?, ?)",
                (self._normalize(query), provider, payload, now, ttl),
            )
            await db.executemany(
                "INSERT OR REPLACE INTO video_metadata VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        result.videoId,
                        result.title,
                        result.channelName,
                        result.channelUrl,
                        result.durationText,
                        result.durationSeconds,
                        result.thumbnailUrl,
                        result.watchUrl,
                        now,
                    )
                    for result in results
                ],
            )
            await db.commit()

    @staticmethod
    def _normalize(query: str) -> str:
        return " ".join(query.casefold().split())
