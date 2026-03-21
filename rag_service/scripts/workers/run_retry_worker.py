"""Backward-compatible retry worker entrypoint."""

from __future__ import annotations

import signal

from redis import Redis
from rq import Worker

from src.config import retry_config
from src.jobs.retry import QUEUE_NAME

REDIS_URL = retry_config.redis_url


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
