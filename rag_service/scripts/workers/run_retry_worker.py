from redis import Redis
from rq import Connection, Worker

from src.config import REDIS_URL
from src.jobs.retry import QUEUE_NAME


def main() -> None:
    connection = Redis.from_url(REDIS_URL)
    with Connection(connection):
        worker = Worker([QUEUE_NAME])
        worker.work(with_scheduler=True)


if __name__ == "__main__":
    main()
