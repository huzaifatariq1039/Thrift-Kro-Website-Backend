"""Run the complete suite against a disposable local PostgreSQL database."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import uuid

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url


TEMP_DATABASE_PATTERN = re.compile(r"^thriftkro_test_[0-9a-f]{32}$")


def _validate_temporary_database_name(database_name: str) -> None:
    if not TEMP_DATABASE_PATTERN.fullmatch(database_name):
        raise ValueError("Refusing to manage a database outside the test namespace")


def _admin_url(base_url: URL) -> URL:
    return base_url.set(database="postgres")


def _create_database(base_url: URL, database_name: str) -> None:
    _validate_temporary_database_name(database_name)
    engine = create_engine(_admin_url(base_url), isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": database_name},
            ).scalar()
            if exists:
                raise RuntimeError("Generated temporary database already exists")
            connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
    finally:
        engine.dispose()


def _drop_database(base_url: URL, database_name: str) -> None:
    _validate_temporary_database_name(database_name)
    engine = create_engine(_admin_url(base_url), isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) "
                    "FROM pg_stat_activity "
                    "WHERE datname = :name AND pid <> pg_backend_pid()"
                ),
                {"name": database_name},
            )
            connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{database_name}"')
    finally:
        engine.dispose()


def main() -> int:
    configured_url = os.getenv("DATABASE_URL")
    if not configured_url:
        raise RuntimeError("DATABASE_URL is required to reach the local PostgreSQL server")

    base_url = make_url(configured_url)
    if not base_url.drivername.startswith("postgresql"):
        raise RuntimeError("Disposable integration tests require PostgreSQL")

    database_name = f"thriftkro_test_{uuid.uuid4().hex}"
    test_url = base_url.set(database=database_name)
    test_environment = os.environ.copy()
    test_environment.update(
        {
            "DATABASE_URL": test_url.render_as_string(hide_password=False),
            "TEST_DATABASE_URL": test_url.render_as_string(hide_password=False),
            "SECRET_KEY": "local-test-secret-key-with-at-least-32-characters",
        }
    )

    print("Creating isolated PostgreSQL test database...")
    _create_database(base_url, database_name)
    try:
        print("Applying migrations to the empty database...")
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            check=True,
            env=test_environment,
        )
        print("Running contract and PostgreSQL integration tests...")
        subprocess.run(
            [
                sys.executable,
                "-m",
                "unittest",
                "discover",
                "-s",
                "tests",
                "-p",
                "test_*.py",
                "-v",
            ],
            check=True,
            env=test_environment,
        )
    finally:
        print("Removing isolated PostgreSQL test database...")
        _drop_database(base_url, database_name)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
