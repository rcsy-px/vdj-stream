from dataclasses import dataclass, field

from ..models import ResolvedFormat


@dataclass
class ResolvedStream:
    video_id: str
    title: str
    upstream_url: str
    http_headers: dict[str, str] = field(default_factory=dict)
    format: ResolvedFormat = field(default_factory=ResolvedFormat)
    expires_at: int | None = None
