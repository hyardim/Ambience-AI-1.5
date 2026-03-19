from redis import Redis
from rq import Worker

from src.config import retry_config
from src.jobs.retry import QUEUE_NAME


def main() -> None:
    connection = Redis.from_url(retry_config.redis_url)
    worker = Worker([QUEUE_NAME], connection=connection)
    worker.work(with_scheduler=True)


if __name__ == "__main__":
    main()
