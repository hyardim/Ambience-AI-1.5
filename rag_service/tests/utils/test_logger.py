import json
import logging
from pathlib import Path

import pytest

from src.utils.logger import JsonFormatter, setup_logger


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
            h for h in logger.handlers if type(h) is logging.StreamHandler
        ]
        assert len(stream_handlers) == 1

    def test_file_handler_exists(self) -> None:
        logger = setup_logger("test.file")
        file_handlers = [
            h for h in logger.handlers if isinstance(h, logging.FileHandler)
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
        assert logger.level == logging.DEBUG

    def test_logger_does_not_propagate(self) -> None:
        logger = setup_logger("test.propagate")
        assert logger.propagate is False

    def test_default_name(self) -> None:
        logger = setup_logger()
        assert isinstance(logger, logging.Logger)

    def test_log_file_created(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LOG_FILE", str(tmp_path / "test.log"))
        logger = setup_logger("test.logfile.tmp")
        file_handler = next(
            h for h in logger.handlers if isinstance(h, logging.FileHandler)
        )
        assert file_handler.baseFilename is not None

    def test_log_record_is_valid_json(self) -> None:
        formatter = JsonFormatter(datefmt="%Y-%m-%dT%H:%M:%S")
        record = logging.LogRecord(
            name="test.json",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg='quote "safe" payload',
            args=(),
            exc_info=None,
        )

        json.loads(formatter.format(record))

    def test_log_record_includes_extra_fields(self) -> None:
        formatter = JsonFormatter(datefmt="%Y-%m-%dT%H:%M:%S")
        record = logging.LogRecord(
            name="test.extra",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="event",
            args=(),
            exc_info=None,
        )
        record.job_id = "abc123"  # type: ignore[attr-defined]

        payload = json.loads(formatter.format(record))
        assert payload["job_id"] == "abc123"

    def test_log_record_includes_stack_info(self) -> None:
        """Line 55: stack_info branch in JsonFormatter."""
        formatter = JsonFormatter(datefmt="%Y-%m-%dT%H:%M:%S")
        record = logging.LogRecord(
            name="test.stack",
            level=logging.WARNING,
            pathname=__file__,
            lineno=1,
            msg="with stack",
            args=(),
            exc_info=None,
        )
        record.stack_info = 'Stack (most recent call last):\n  File "test.py", line 1'

        payload = json.loads(formatter.format(record))
        assert "stack_info" in payload
        assert "Stack (most recent call last)" in payload["stack_info"]
