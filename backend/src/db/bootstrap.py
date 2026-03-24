import argparse
from pathlib import Path
from typing import TypedDict

from sqlalchemy import inspect
from alembic.config import Config

from alembic import command
from src.core import security
from src.core.config import settings
from src.db.models import User, UserRole
from src.db.session import SessionLocal, engine

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI_PATH = PROJECT_ROOT / "alembic.ini"
ALEMBIC_SCRIPT_PATH = PROJECT_ROOT / "alembic"
DEMO_SEED_ALLOWED_ENVS = {"development", "test"}
MANAGED_BACKEND_TABLES = frozenset(
    {
        "audit_logs",
        "chats",
        "email_verification_tokens",
        "file_attachments",
        "messages",
        "notifications",
        "password_reset_tokens",
        "users",
    }
)


class DefaultUserSpec(TypedDict):
    email: str
    password: str
    full_name: str
    role: UserRole
    specialty: str | None


def build_alembic_config() -> Config:
    config = Config(str(ALEMBIC_INI_PATH))
    config.set_main_option("script_location", str(ALEMBIC_SCRIPT_PATH))
    config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    return config


def _existing_public_tables() -> set[str]:
    inspector = inspect(engine)
    if engine.dialect.name == "postgresql":
        return set(inspector.get_table_names(schema="public"))
    return set(inspector.get_table_names())


def _ensure_supported_migration_state() -> None:
    existing_tables = _existing_public_tables()
    if "alembic_version" in existing_tables:
        return

    legacy_backend_tables = sorted(existing_tables & MANAGED_BACKEND_TABLES)
    if not legacy_backend_tables:
        return

    joined_tables = ", ".join(legacy_backend_tables)
    raise RuntimeError(
        "Detected backend tables without Alembic migration history: "
        f"{joined_tables}. This usually means the stack is reusing an older "
        "local postgres_data/ directory. For a fresh local bootstrap, stop the "
        "stack and remove postgres_data/ before starting again. If you need to "
        "preserve the data, back it up first and add a one-off migration or "
        "Alembic stamp for the legacy schema before restarting the backend."
    )


def run_migrations() -> None:
    _ensure_supported_migration_state()
    command.upgrade(build_alembic_config(), "head")


def _required_demo_passwords() -> tuple[str, str, str]:
    values = (
        settings.DEMO_GP_PASSWORD,
        settings.DEMO_SPECIALIST_PASSWORD,
        settings.DEMO_ADMIN_PASSWORD,
    )
    if not all(values):
        raise RuntimeError(
            "Demo user seeding requires DEMO_GP_PASSWORD, "
            "DEMO_SPECIALIST_PASSWORD, and DEMO_ADMIN_PASSWORD"
        )
    return values


def ensure_default_users() -> None:
    if not settings.AUTH_BOOTSTRAP_DEMO_USERS:
        return
    if settings.APP_ENV not in DEMO_SEED_ALLOWED_ENVS:
        return

    gp_password, specialist_password, admin_password = _required_demo_passwords()

    defaults: list[DefaultUserSpec] = [
        {
            "email": "gp@example.com",
            "password": gp_password,
            "full_name": "Dr. GP User",
            "role": UserRole.GP,
            "specialty": None,
        },
        {
            "email": "specialist@example.com",
            "password": specialist_password,
            "full_name": "Dr. Specialist User",
            "role": UserRole.SPECIALIST,
            "specialty": "neurology",
        },
        {
            "email": "admin@example.com",
            "password": admin_password,
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
