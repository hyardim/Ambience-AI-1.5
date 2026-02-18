import logging
import sys
from pathlib import Path

from ..config import logging_config


def setup_logger(name: str = __name__) -> logging.Logger:
    """Get a logger for a given module."""
    logger = logging.getLogger(name)


    # Avoid duplicate handlers
    if logger.handlers:
        return logger

    logger.setLevel(logging_config.log_level)

    console_format = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_format = logging.Formatter(
        fmt=(
            "%(asctime)s | %(levelname)-8s | %(name)s | "
            "%(filename)s:%(lineno)d | %(message)s"
        ),
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler - uses configured log level
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging_config.log_level)
    console_handler.setFormatter(console_format)

    # File handler - always DEBUG for full verbosity
    log_path = Path(logging_config.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_path)
    file_handler.setLevel(logging.DEBUG)

    file_handler.setFormatter(file_format)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger
