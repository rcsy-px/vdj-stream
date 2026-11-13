import asyncio
import re
import secrets
import time
import sys
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

    async def check(self, force: bool = False) -> dict[str, Any]:
        async with self._lock:
            now = time.monotonic()
            if (
                self._cached_result is not None
                and not force
                and now - self._cached_at < (
                    min(60, self.cache_ttl_seconds)
                    if self._cached_result.get("error") else self.cache_ttl_seconds
                )
            ):
                return self._cached_result
            try:
                result = await self._fetch()
            except Exception as exc:
                result = {
                    "currentVersion": self.current_version,
                    "latestVersion": None,
                    "updateAvailable": False,
                    "releaseUrl": None,
                    "downloadUrl": None,
                    "error": "Update check unavailable",
                    "errorDetail": self._error_detail(exc),
                }
            self._cached_result = result
            self._cached_at = now
            return result

    @staticmethod
    def _error_detail(exc: Exception) -> str:
        if isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code
            if status in (403, 429):
                return "GitHub refused the request or its rate limit was reached. Try again later."
            if status == 404:
                return "No public release was found for this repository."
            return f"GitHub returned HTTP {status}. Try again later."
        if isinstance(exc, httpx.TimeoutException):
            return "GitHub took too long to respond. Check your connection and retry."
        if isinstance(exc, httpx.ConnectError):
            return "Cannot connect to GitHub. Check your internet connection and network permissions."
        return "The release information could not be read. Please retry."

    async def _fetch(self) -> dict[str, Any]:
        # Each actual fetch has a unique URL, so intermediaries cannot reuse a
        # pre-publication response. Automatic polling is still bounded by check().
        url = f"https://api.github.com/repos/{self.repository}/releases/latest?_={secrets.token_hex(16)}"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": f"VDJ-Companion/{self.current_version}",
            "Cache-Control": "no-cache, no-store, max-age=0",
            "Pragma": "no-cache",
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
        if latest_tuple is None:
            raise ValueError("Invalid release version")
        assets = release.get("assets") or []
        release_prefix = f"https://github.com/{self.repository}/releases/"
        release_url = release.get("html_url")
        if not str(release_url).startswith(release_prefix):
            release_url = None
        download_url = next(
            (
                asset.get("browser_download_url")
                for asset in assets
                if str(asset.get("name", "")).endswith(
                    "-macos-universal.zip" if sys.platform == "darwin" else "-windows-x64.zip"
                )
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
                and (sys.platform != "darwin" or download_url)
            ),
            "releaseUrl": release_url,
            "downloadUrl": download_url,
        }
