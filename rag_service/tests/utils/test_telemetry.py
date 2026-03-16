from __future__ import annotations

from pathlib import Path

from src.utils.telemetry import append_jsonl


def test_append_jsonl_writes_line(tmp_path: Path) -> None:
    path = tmp_path / "metrics" / "events.jsonl"

    append_jsonl(path, {"event": "retrieve", "count": 2})

    content = path.read_text(encoding="utf-8")
    assert '"event": "retrieve"' in content
    assert '"count": 2' in content
    assert '"timestamp":' in content


def test_append_jsonl_swallows_write_errors(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "metrics" / "events.jsonl"

    def boom(self: Path, *args: object, **kwargs: object):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "open", boom)

    append_jsonl(path, {"event": "retrieve"})
