"""Structured logging configuration for SuperDeepAnalyze."""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(log_level: str = "INFO") -> None:
    """Initialize logging to both stdout and rotating file.

    Log file: data/logs/superdeep.log (max 10MB, 5 backups)
    """
    from app.config import settings
    log_dir = settings.DATA_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "superdeep.log"

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Root logger
    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Console handler
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(formatter)
    root.addHandler(console)

    # Rotating file handler
    file_handler = RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)


def get_logger(name: str, **context) -> logging.LoggerAdapter:
    """Get a logger with optional context (session_id, kb_id, etc.)."""
    logger = logging.getLogger(name)
    if context:
        return logging.LoggerAdapter(logger, context)
    return logger
