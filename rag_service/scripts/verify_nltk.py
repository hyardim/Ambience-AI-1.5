"""Ensure NLTK tokenizer data is installed and loadable."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


RESOURCES = ("punkt", "punkt_tab")


def _download_dir() -> Path:
    configured = os.getenv("NLTK_DATA", "").split(os.pathsep)[0].strip()
    return Path(configured) if configured else Path("/usr/local/share/nltk_data")


def _cleanup_resource(download_dir: Path, resource: str) -> None:
    tokenizers_dir = download_dir / "tokenizers"
    for rel in (f"{resource}.zip", resource):
        target = tokenizers_dir / rel
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
        elif target.exists():
            target.unlink()


def _ensure_resource(nltk: object, download_dir: Path, resource: str) -> bool:
    for attempt in range(1, 4):
        try:
            nltk.download(
                resource,
                quiet=True,
                force=True,
                raise_on_error=True,
                download_dir=str(download_dir),
            )
            nltk.data.find(f"tokenizers/{resource}")
            print(f"OK: {resource} found")
            return True
        except Exception as exc:  # noqa: BLE001
            _cleanup_resource(download_dir, resource)
            print(f"WARN: failed to install {resource} (attempt {attempt}/3): {exc}")

    print(f"ERROR: unable to install {resource} after 3 attempts")
    return False


def verify() -> None:
    failed = False

    try:
        import nltk
    except ImportError:
        print("ERROR: nltk is not installed — run: pip install nltk")
        sys.exit(1)

    download_dir = _download_dir()
    download_dir.mkdir(parents=True, exist_ok=True)

    for resource in RESOURCES:
        if not _ensure_resource(nltk, download_dir, resource):
            failed = True

    try:
        from nltk.tokenize import sent_tokenize

        result = sent_tokenize("This is a test. It should tokenize correctly.")
        assert len(result) == 2, f"Expected 2 sentences, got {len(result)}"
        print("OK: tokenizer functional")
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: tokenizer failed: {exc}")
        failed = True

    if failed:
        sys.exit(1)

    print("NLTK data verified.")


if __name__ == "__main__":
    verify()
