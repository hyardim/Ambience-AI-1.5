import logging

import pytest

from src.utils.logger import setup_logger


class TestSetupLogger:
    def test_returns_logger(self) -> None:
        logger = setup_logger("test.basic")
        assert isinstance(logger, logging.Logger)

    def test_logger_name(self) -> None:
        logger = setup_logger("test.name")
        assert logger.name == "test.name"

    def test_has_two_handlers(self) -> None:
        logger = setup_logger("test.handlers")
        assert len(logger.handlers) == 2

    def test_no_duplicate_handlers(self) -> None:
        setup_logger("test.duplicate")
        logger = setup_logger("test.duplicate")
        assert len(logger.handlers) == 2

    def test_console_handler_exists(self) -> None:
        logger = setup_logger("test.console")
        stream_handlers = [
            h for h in logger.handlers
            if type(h) is logging.StreamHandler
        ]
        assert len(stream_handlers) == 1

    def test_file_handler_exists(self) -> None:
        logger = setup_logger("test.file")
        file_handlers = [
            h for h in logger.handlers
            if isinstance(h, logging.FileHandler)
        ]
        assert len(file_handlers) == 1

    def test_file_handler_level_is_debug(self) -> None:
        logger = setup_logger("test.filelevel")
        file_handler = next(
            h for h in logger.handlers if isinstance(h, logging.FileHandler)
        )
        assert file_handler.level == logging.DEBUG

    def test_console_handler_level(self) -> None:
        logger = setup_logger("test.consolelevel")
        console_handler = next(
            h for h in logger.handlers if type(h) is logging.StreamHandler
        )
        assert console_handler.level == logging.INFO

    def test_default_name(self) -> None:
        logger = setup_logger()
        assert isinstance(logger, logging.Logger)

    def test_log_file_created(self, tmp_path: pytest.TempPathFactory) -> None:
        logger = setup_logger("test.logfile")
        file_handler = next(
            h for h in logger.handlers if isinstance(h, logging.FileHandler)
        )
        assert file_handler.baseFilename is not None
