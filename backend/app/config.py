from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    service_name: str = "vdj-youtube-companion"
    version: str = "0.1.0"
    host: str = "127.0.0.1"
    port: int = 8765
    public_base_url: str = "http://127.0.0.1:8765"
    search_timeout_seconds: float = 20.0
    resolve_timeout_seconds: float = 45.0
    query_cache_ttl_seconds: int = 1800
    resolve_cache_ttl_seconds: int = 1200
    headless: bool = True

    data_dir: Path = PROJECT_ROOT / "data"
    log_dir: Path = PROJECT_ROOT / "data" / "logs"
    database_path: Path = PROJECT_ROOT / "data" / "companion.sqlite3"
    ytdlp_exe: Path = PROJECT_ROOT / "tools" / "yt-dlp" / "yt-dlp.exe"
    ffmpeg_bin: Path = PROJECT_ROOT / "tools" / "ffmpeg" / "bin"
    playwright_browsers_path: Path = PROJECT_ROOT / "tools" / "playwright-browsers"

    def prepare_directories(self) -> None:
        for path in (self.data_dir, self.log_dir, self.playwright_browsers_path):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
