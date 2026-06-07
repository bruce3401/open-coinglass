from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import structlog

# 10MB per file, keep 3 backups = max 40MB
MAX_BYTES = 10 * 1024 * 1024
BACKUP_COUNT = 3


def setup_logging(level: str = "INFO", log_file: str | None = None) -> None:
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Configure stdlib root logger
    root = logging.getLogger()
    root.setLevel(log_level)
    root.handlers.clear()

    fmt = logging.Formatter("%(message)s")

    # Always: stderr
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(fmt)
    root.addHandler(stderr_handler)

    # Optional: rotating file
    if log_file:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(str(path), maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT)
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)

    # Configure structlog to use stdlib logging
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
