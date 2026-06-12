from pydantic import BaseModel, Field


class TrackSearchResult(BaseModel):
    id: str
    provider: str
    videoId: str
    title: str
    channelName: str | None = None
    channelUrl: str | None = None
    durationText: str | None = None
    durationSeconds: int | None = None
    thumbnailUrl: str | None = None
    watchUrl: str
    badges: list[str] = Field(default_factory=list)
    cached: bool = False


class SearchResponse(BaseModel):
    query: str
    provider: str
    cached: bool
    results: list[TrackSearchResult]
    error: str | None = None


class ResolvedFormat(BaseModel):
    formatId: str | None = None
    ext: str | None = None
    acodec: str | None = None
    abr: float | None = None


class ResolveResponse(BaseModel):
    ok: bool
    videoId: str
    title: str | None = None
    localStreamUrl: str | None = None
    format: ResolvedFormat | None = None
    expiresAt: int | None = None
    error: str | None = None
