import re
import unicodedata
from urllib.parse import quote


def stream_filename(title: str, video_id: str) -> str:
    normalized = unicodedata.normalize("NFKC", title).strip()
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", normalized)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return (cleaned[:140].rstrip(" .") or f"YouTube {video_id}") + ".m4a"


def stream_url(base_url: str, video_id: str, title: str) -> str:
    filename = quote(stream_filename(title, video_id), safe="")
    return f"{base_url}/stream/youtube/{video_id}/{filename}"


def content_disposition(title: str, video_id: str) -> str:
    filename = stream_filename(title, video_id)
    ascii_name = (
        unicodedata.normalize("NFKD", filename)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    ascii_name = re.sub(r'["\\\r\n]', " ", ascii_name).strip() or f"YouTube {video_id}.m4a"
    return f'inline; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(filename, safe="")}'
