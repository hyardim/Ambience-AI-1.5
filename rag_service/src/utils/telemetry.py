from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    """Append a JSON line to a telemetry file, best-effort."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        enriched = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **payload,
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(enriched, default=str) + "\n")
    except Exception:
        # Telemetry should never break user-facing flows.
        return
