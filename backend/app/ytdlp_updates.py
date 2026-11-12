"""Inspect and explicitly update the project's portable yt-dlp executable."""

import asyncio
import logging
from pathlib import Path

from .ytdlp_runner import YtDlpRunner
from .update_checker import GitHubReleaseChecker, _version_tuple

logger = logging.getLogger(__name__)


class YtDlpUpdates:
    def __init__(self, executable: Path, runner: YtDlpRunner | None = None):
        self.executable = executable
        self.runner = runner or YtDlpRunner(executable)
        self.releases = GitHubReleaseChecker("0.0.0", "yt-dlp/yt-dlp", 3600, 10)
        self._update_lock = asyncio.Lock()
        self.last_error: str | None = None

    async def _run(self, *args: str, timeout: float = 15) -> str:
        return await self.runner.run(*args, timeout=timeout)

    async def installed_version(self, run=None) -> str:
        version = await (run or self._run)("--version", timeout=15)
        if _version_tuple(version) is None:
            raise RuntimeError("The installed yt-dlp version could not be read.")
        return version

    async def check(self, force: bool = False) -> dict:
        installed = None
        local_error = None
        # The executable can be replaced by its updater; don't execute it mid-update.
        if not self._update_lock.locked():
            try:
                installed = await self.installed_version()
            except Exception as exc:
                local_error = str(exc) or "Could not read the installed yt-dlp version."
        release = await self.releases.check(force=force)
        latest = release.get("latestVersion")
        current_tuple = _version_tuple(installed or "")
        latest_tuple = _version_tuple(latest or "")
        return {
            "currentVersion": installed,
            "latestVersion": latest,
            "updateAvailable": bool(current_tuple and latest_tuple and latest_tuple > current_tuple),
            "releaseUrl": release.get("releaseUrl"),
            "updating": self._update_lock.locked(),
            "error": local_error or release.get("error"),
            "errorDetail": local_error or release.get("errorDetail"),
            "lastUpdateError": self.last_error,
        }

    async def update(self) -> dict:
        if self._update_lock.locked():
            raise RuntimeError("A yt-dlp update is already running.")
        async with self._update_lock:
            self.last_error = None
            try:
                async with self.runner.exclusive() as run:
                    before = await self.installed_version(run)
                    logger.info("Updating yt-dlp from %s using the official stable channel", before)
                    await run("--update-to", "stable", timeout=180)
                    after = await self.installed_version(run)
                    logger.info("yt-dlp update finished: %s", after)
            except Exception as exc:
                self.last_error = (
                    "The update timed out. Check your connection and retry."
                    if isinstance(exc, TimeoutError) else str(exc)
                )
                logger.warning("yt-dlp update failed: %s", self.last_error)
                raise RuntimeError(self.last_error) from exc
        result = await self.check(force=True)
        result["message"] = (
            f"Updated yt-dlp to {after}. Reload the track in VirtualDJ."
            if before != after else f"yt-dlp {after} is already installed."
        )
        return result
