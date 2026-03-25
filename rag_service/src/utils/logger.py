import json
import logging
import sys
from pathlib import Path
from typing import Any

from ..config import logging_config


def _resolve_log_level(level_name: str) -> int:
    return getattr(logging, level_name.upper(), logging.INFO)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, Any] = {
            "ts": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.pathname:
            data["file"] = record.filename
            data["line"] = record.lineno
        for key, value in record.__dict__.items():
            if key in {
                "name",
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "exc_info",
                "exc_text",
                "stack_info",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
                "taskName",
            }:
                continue
            if key not in data:
                data[key] = value
        if record.exc_info:
            data["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            data["stack_info"] = record.stack_info
        return json.dumps(data, default=str)


def setup_logger(name: str = __name__) -> logging.Logger:
    """Get a logger for a given module."""
    logger = logging.getLogger(name)

    # Avoid duplicate handlers
    if logger.handlers:
        return logger

    configured_level = _resolve_log_level(logging_config.log_level)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    json_format = JsonFormatter(datefmt="%Y-%m-%dT%H:%M:%S")

    # Console handler - uses configured log level
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(configured_level)
    console_handler.setFormatter(json_format)

    # File handler - always DEBUG for full verbosity
    log_path = Path(logging_config.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_path)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(json_format)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger
