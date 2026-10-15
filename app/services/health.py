"""Read-only process and database readiness checks."""

from functools import lru_cache
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def expected_migration_heads() -> frozenset[str]:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(config)
    return frozenset(script.get_heads())


def database_is_ready(db: Session) -> bool:
    """Return true only when PostgreSQL is reachable and exactly at code head."""
    try:
        current_heads = frozenset(
            db.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
        )
    except SQLAlchemyError:
        return False
    return current_heads == expected_migration_heads()
