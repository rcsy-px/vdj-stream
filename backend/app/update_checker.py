import asyncio
import re
import time
from typing import Any

import httpx


VERSION_PATTERN = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def _version_tuple(version: str) -> tuple[int, int, int] | None:
    match = VERSION_PATTERN.fullmatch(version.strip())
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


class GitHubReleaseChecker:
    def __init__(
        self,
        current_version: str,
        repository: str,
        cache_ttl_seconds: int = 21600,
        timeout_seconds: float = 5.0,
    ):
        self.current_version = current_version
        self.repository = repository
        self.cache_ttl_seconds = cache_ttl_seconds
        self.timeout_seconds = timeout_seconds
        self._cached_at = 0.0
        self._cached_result: dict[str, Any] | None = None
        self._lock = asyncio.Lock()

    async def check(self) -> dict[str, Any]:
        async with self._lock:
            now = time.monotonic()
            if (
                self._cached_result is not None
                and now - self._cached_at < self.cache_ttl_seconds
            ):
                return self._cached_result
            try:
                result = await self._fetch()
            except Exception:
                result = {
                    "currentVersion": self.current_version,
                    "latestVersion": None,
                    "updateAvailable": False,
                    "releaseUrl": None,
                    "downloadUrl": None,
                    "error": "Update check unavailable",
                }
            self._cached_result = result
            self._cached_at = now
            return result

    async def _fetch(self) -> dict[str, Any]:
        url = f"https://api.github.com/repos/{self.repository}/releases/latest"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": f"VDJ-Companion/{self.current_version}",
        }
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=self.timeout_seconds, headers=headers
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            release = response.json()

        latest_version = str(release.get("tag_name", "")).removeprefix("v")
        current_tuple = _version_tuple(self.current_version)
        latest_tuple = _version_tuple(latest_version)
        assets = release.get("assets") or []
        release_prefix = f"https://github.com/{self.repository}/releases/"
        release_url = release.get("html_url")
        if not str(release_url).startswith(release_prefix):
            release_url = None
        download_url = next(
            (
                asset.get("browser_download_url")
                for asset in assets
                if str(asset.get("name", "")).endswith("-windows-x64.zip")
                and str(asset.get("browser_download_url", "")).startswith(
                    f"{release_prefix}download/"
                )
            ),
            None,
        )
        return {
            "currentVersion": self.current_version,
            "latestVersion": latest_version or None,
            "updateAvailable": bool(
                current_tuple and latest_tuple and latest_tuple > current_tuple
            ),
            "releaseUrl": release_url,
            "downloadUrl": download_url,
        }
