"""Backward-compatible retry worker entrypoint."""

from __future__ import annotations

import signal

from redis import Redis
from rq import Worker

try:
    from src.config import retry_config

    REDIS_URL = retry_config.redis_url
except Exception:
    from src.config import REDIS_URL  # type: ignore[attr-defined,no-redef]

try:
    from src.jobs.retry import QUEUE_NAME
except Exception:
    from src.retry_queue import QUEUE_NAME  # type: ignore[no-redef]


def main() -> None:
    connection = Redis.from_url(REDIS_URL)
    worker = Worker([QUEUE_NAME], connection=connection)

    def _handle_stop(_signum: int, _frame: object) -> None:
        worker.request_stop()

    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    worker.work(with_scheduler=True)


if __name__ == "__main__":
    main()
