"""Structured logging configuration for Universal Video Downloader Bot.

Ensures sensitive parameters (tokens, passwords, API keys) are redacted,
outputs structured messages with job and user context, and configures
both console and rotating file logging.
"""

import io
import logging
import logging.handlers
import os
import re
import sys
from pathlib import Path
from typing import Optional

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    if isinstance(sys.stdout, io.TextIOWrapper):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if isinstance(sys.stderr, io.TextIOWrapper):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


# Regex to detect sensitive tokens or query parameters in URLs or logs
SENSITIVE_PATTERNS = [
    re.compile(r"bot\d+:[A-Za-z0-9_-]+", re.IGNORECASE),
    re.compile(r"(token|auth|key|secret|password|sig)=([A-Za-z0-9_%-]+)", re.IGNORECASE),
]


class SensitiveDataFilter(logging.Filter):
    """Logging filter that scrubs sensitive credentials from log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self._redact(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: self._redact_value(v) for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(self._redact_value(v) for v in record.args)
        return True

    def _redact_value(self, val: object) -> object:
        if isinstance(val, str):
            return self._redact(val)
        return val

    def _redact(self, text: str) -> str:
        for pattern in SENSITIVE_PATTERNS:
            text = pattern.sub("[REDACTED]", text)
        return text


def setup_logging(
    log_level: str = "INFO",
    log_dir: str = "./logs",
    log_filename: str = "bot.log",
) -> None:
    """Initialize structured console and file logging."""
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    log_file_path = Path(log_dir) / log_filename

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicates
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-7s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    sensitive_filter = SensitiveDataFilter()

    # 1. Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.addFilter(sensitive_filter)
    console_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    root_logger.addHandler(console_handler)

    # 2. Rotating File Handler (Max 10 MB per file, keep 5 backups)
    file_handler = logging.handlers.RotatingFileHandler(
        filename=str(log_file_path),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(sensitive_filter)
    file_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    root_logger.addHandler(file_handler)

    # Silence overly verbose external loggers
    logging.getLogger("aiogram").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a logger configured with the given name."""
    return logging.getLogger(name)
