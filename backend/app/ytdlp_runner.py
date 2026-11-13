"""Bounded yt-dlp processes with writer-priority updates and cancellation cleanup."""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

logger = logging.getLogger(__name__)


class YtDlpBusyError(RuntimeError):
    pass


class YtDlpRunner:
    def __init__(self, executable: Path, concurrency: int = 2, queue_timeout: float = 5):
        self.executable = executable
        self.concurrency = concurrency
        self.queue_timeout = queue_timeout
        self._condition = asyncio.Condition()
        self._active = 0
        self._writers = 0
        self._exclusive = False

    @property
    def updating(self) -> bool:
        return self._exclusive or self._writers > 0

    @asynccontextmanager
    async def _slot(self, exclusive: bool, wait: float):
        async with self._condition:
            if exclusive:
                self._writers += 1
            try:
                async with asyncio.timeout(wait):
                    await self._condition.wait_for(
                        lambda: not self._exclusive and (
                            self._active == 0 if exclusive
                            else self._writers == 0 and self._active < self.concurrency
                        )
                    )
                if exclusive:
                    self._exclusive = True
                else:
                    self._active += 1
            except TimeoutError as exc:
                raise YtDlpBusyError(
                    "YouTube engine is busy or updating. Please retry in a moment."
                ) from exc
            finally:
                if exclusive:
                    self._writers -= 1
                self._condition.notify_all()
        try:
            yield
        finally:
            async with self._condition:
                if exclusive:
                    self._exclusive = False
                else:
                    self._active -= 1
                self._condition.notify_all()

    async def run(self, *args: str, timeout: float = 45) -> str:
        async with self._slot(False, self.queue_timeout):
            return await self._execute(*args, timeout=timeout)

    @asynccontextmanager
    async def exclusive(self):
        # All reads drain before replacing the EXE; new reads wait briefly.
        async with self._slot(True, 60):
            yield self._execute

    async def _execute(self, *args: str, timeout: float = 45) -> str:
        if not self.executable.is_file():
            raise RuntimeError("yt-dlp is missing. Run the platform launcher (START.bat or START.command) to install it.")
        process = await asyncio.create_subprocess_exec(
            str(self.executable), "--ignore-config", *args,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout)
        except (TimeoutError, asyncio.CancelledError):
            if process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
            await process.communicate()
            raise
        if process.returncode:
            logger.warning("yt-dlp failed: %s", stderr.decode(errors="replace")[-1500:])
            raise RuntimeError("yt-dlp failed. Check Live logs for details and try updating the engine.")
        return stdout.decode("utf-8", errors="replace").strip()
