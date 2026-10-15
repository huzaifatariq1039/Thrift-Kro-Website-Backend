"""Apply Alembic migrations under a PostgreSQL advisory lock."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from app.core.config import settings


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_LOCK_ID = 841_015_202_610_140_010
MIGRATION_LOCK_TIMEOUT = "60s"


def upgrade_database() -> None:
    """Upgrade to head, allowing only one release migrator at a time."""
    alembic_config = Config(str(PROJECT_ROOT / "alembic.ini"))
    engine = create_engine(
        settings.SQLALCHEMY_DATABASE_URI,
        poolclass=NullPool,
    )

    try:
        with engine.begin() as connection:
            connection.execute(
                text("SELECT set_config('lock_timeout', :timeout, true)"),
                {"timeout": MIGRATION_LOCK_TIMEOUT},
            )
            connection.execute(
                text("SELECT pg_advisory_xact_lock(:lock_id)"),
                {"lock_id": MIGRATION_LOCK_ID},
            )
            alembic_config.attributes["connection"] = connection
            command.upgrade(alembic_config, "head")
    finally:
        engine.dispose()


if __name__ == "__main__":
    upgrade_database()
