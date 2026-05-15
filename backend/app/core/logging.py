from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from app.core.paths import APP_LOG_PATH


class _SafeRotatingFileHandler(RotatingFileHandler):
    """RotatingFileHandler that silently skips rollover checks when the file
    stream is temporarily unreadable (OSError on Windows under concurrent writes)."""

    def shouldRollover(self, record: logging.LogRecord) -> int:
        try:
            return super().shouldRollover(record)
        except OSError:
            return 0


def setup_logging() -> None:
    root_logger = logging.getLogger()
    if getattr(root_logger, "_auto_hr_configured", False):
        return

    root_logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = _SafeRotatingFileHandler(
        APP_LOG_PATH,
        maxBytes=2 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    root_logger.addHandler(file_handler)
    root_logger.addHandler(stream_handler)
    root_logger._auto_hr_configured = True  # type: ignore[attr-defined]


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)
