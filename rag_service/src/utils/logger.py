import logging
import sys
from pathlib import Path

from ..config import config


def setup_logger(name: str = __name__) -> logging.Logger:
    """Set up logger with file and console handlers."""
    logger = logging.getLogger(name)
    logger.setLevel(config.log_level)

    # Avoid duplicate handlers
    if logger.handlers:
        return logger

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(config.log_level)
    console_format = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    console_handler.setFormatter(console_format)

    # File handler
    config.log_file.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(config.log_file)
    file_handler.setLevel(logging.DEBUG)
    file_format = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
    )
    file_handler.setFormatter(file_format)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger