import logging

from src.core.logging import configure_logging


def test_configure_logging_calls_basic_config(monkeypatch):
    captured = {}

    def fake_basic_config(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(logging, "basicConfig", fake_basic_config)
    configure_logging()

    assert captured["level"] == logging.INFO
    assert "%(asctime)s" in captured["format"]
