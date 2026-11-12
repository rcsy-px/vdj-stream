import re
import unicodedata
from urllib.parse import quote


def audio_extension(ext: str) -> str:
    ext = ext.lower()
    if ext not in {"m4a", "mp4", "webm", "opus", "ogg", "mp3", "aac", "wav", "flac"}:
        raise ValueError("Unsupported audio container returned by yt-dlp")
    return ext


def stream_filename(title: str, video_id: str, ext: str = "m4a") -> str:
    normalized = unicodedata.normalize("NFKC", title).strip()
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", normalized)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return (cleaned[:140].rstrip(" .") or f"YouTube {video_id}") + "." + audio_extension(ext)


def stream_url(base_url: str, video_id: str, title: str, ext: str = "m4a") -> str:
    filename = quote(stream_filename(title, video_id, ext), safe="")
    return f"{base_url}/stream/youtube/{video_id}/{filename}"


def content_disposition(title: str, video_id: str, ext: str = "m4a") -> str:
    filename = stream_filename(title, video_id, ext)
    ascii_name = (
        unicodedata.normalize("NFKD", filename)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    ascii_name = re.sub(r'["\\\r\n]', " ", ascii_name).strip() or f"YouTube {video_id}.{audio_extension(ext)}"
    return f'inline; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(filename, safe="")}'
