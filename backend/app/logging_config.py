import logging
import re
import threading
from collections import deque
from logging.handlers import RotatingFileHandler

from .config import Settings


def _redact(line: str) -> str:
    line = re.sub(
        r"(?i)\b(authorization|cookie|token|key|secret|password)=([^&\s]+)",
        r"\1=[redacted]",
        line,
    )
    return re.sub(r"(https?://[^\s?]+)\?[^\s]+", r"\1?[redacted]", line)


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return _redact(super().format(record))


class LiveLogHandler(logging.Handler):
    def __init__(self, capacity: int = 300):
        super().__init__()
        self._lines: deque[tuple[int, str]] = deque(maxlen=capacity)
        self._next_id = 1
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            line = self.format(record)
            with self._lock:
                self._lines.append((self._next_id, line))
                self._next_id += 1
        except Exception:
            self.handleError(record)

    def since(self, last_id: int = 0) -> list[tuple[int, str]]:
        with self._lock:
            return [(line_id, line) for line_id, line in self._lines if line_id > last_id]


def configure_logging(settings: Settings) -> LiveLogHandler:
    settings.prepare_directories()
    formatter = RedactingFormatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    file_handler = RotatingFileHandler(
        settings.log_dir / "companion.log",
        maxBytes=2_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    live_handler = LiveLogHandler()
    live_handler.setFormatter(formatter)
    logging.basicConfig(
        level=logging.INFO,
        handlers=[console_handler, file_handler, live_handler],
        force=True,
    )
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).addHandler(live_handler)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    return live_handler
