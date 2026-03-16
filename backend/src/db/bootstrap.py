import argparse
from pathlib import Path

from alembic import command
from alembic.config import Config
from src.core import security
from src.core.config import settings
from src.db.models import User, UserRole
from src.db.session import SessionLocal

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI_PATH = PROJECT_ROOT / "alembic.ini"
ALEMBIC_SCRIPT_PATH = PROJECT_ROOT / "alembic"


def build_alembic_config() -> Config:
    config = Config(str(ALEMBIC_INI_PATH))
    config.set_main_option("script_location", str(ALEMBIC_SCRIPT_PATH))
    config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    return config


def run_migrations() -> None:
    command.upgrade(build_alembic_config(), "head")


def ensure_default_users() -> None:
    if not settings.AUTH_BOOTSTRAP_DEMO_USERS:
        return

    defaults = [
        {
            "email": "gp@example.com",
            "password": "password123",
            "full_name": "Dr. GP User",
            "role": UserRole.GP,
            "specialty": None,
        },
        {
            "email": "specialist@example.com",
            "password": "password123",
            "full_name": "Dr. Specialist User",
            "role": UserRole.SPECIALIST,
            "specialty": "neurology",
        },
        {
            "email": "admin@example.com",
            "password": "password123",
            "full_name": "System Admin",
            "role": UserRole.ADMIN,
            "specialty": None,
        },
    ]

    db = SessionLocal()
    try:
        for item in defaults:
            exists = db.query(User).filter(User.email == item["email"]).first()
            if exists:
                continue
            db.add(
                User(
                    email=item["email"],
                    hashed_password=security.get_password_hash(item["password"]),
                    full_name=item["full_name"],
                    role=item["role"],
                    specialty=item["specialty"],
                )
            )
        db.commit()
    finally:
        db.close()


def prepare_database() -> None:
    run_migrations()
    ensure_default_users()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Backend database operations")
    parser.add_argument(
        "command",
        choices=("migrate", "seed-demo-users", "prepare"),
        help="Database operation to run",
    )
    args = parser.parse_args(argv)

    if args.command == "migrate":
        run_migrations()
    elif args.command == "seed-demo-users":
        ensure_default_users()
    else:
        prepare_database()


if __name__ == "__main__":  # pragma: no cover
    main()
