from abc import ABC, abstractmethod
import re

from ..models import TrackSearchResult


class SearchProvider(ABC):
    name: str

    @abstractmethod
    async def search(self, query: str, limit: int) -> list[TrackSearchResult]:
        raise NotImplementedError

    async def close(self) -> None:
        return None


def youtube_thumbnail_url(video_id: str) -> str:
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"


def duration_to_seconds(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"\b\d{1,2}:\d{2}(?::\d{2})?\b", value)
    if not match:
        return None
    try:
        parts = [int(part) for part in match.group(0).split(":")]
    except ValueError:
        return None
    if not 1 < len(parts) < 4:
        return None
    total = 0
    for part in parts:
        total = total * 60 + part
    return total
