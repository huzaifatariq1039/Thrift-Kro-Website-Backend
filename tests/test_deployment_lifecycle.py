import inspect
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

from app.api.deps import get_db
from app.api.health import router as health_router
from app.services.health import database_is_ready, expected_migration_heads
from scripts import migrate


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class _ScalarResult:
    def __init__(self, values):
        self.values = values

    def scalars(self):
        return self

    def all(self):
        return self.values


class _Database:
    def __init__(self, revisions=None, error=None):
        self.revisions = revisions or []
        self.error = error

    def execute(self, _statement):
        if self.error:
            raise self.error
        return _ScalarResult(self.revisions)


class DeploymentLifecycleTests(unittest.TestCase):
    def test_application_startup_is_read_only(self):
        source = (PROJECT_ROOT / "app" / "main.py").read_text(encoding="utf-8")
        self.assertNotIn("create_all", source)
        self.assertNotIn("command.upgrade", source)
        self.assertNotIn("create_user", source)
        self.assertIn("engine.dispose()", source)

    def test_readiness_requires_database_at_exact_migration_head(self):
        expected = expected_migration_heads()
        self.assertEqual(expected, frozenset({"20261014_10"}))
        self.assertTrue(database_is_ready(_Database(expected)))
        self.assertFalse(database_is_ready(_Database(["20261014_09"])))

        database_error = OperationalError("SELECT 1", {}, Exception("offline"))
        self.assertFalse(database_is_ready(_Database(error=database_error)))

    def test_health_endpoints_distinguish_liveness_and_readiness(self):
        app = FastAPI()
        app.include_router(health_router)
        app.dependency_overrides[get_db] = lambda: object()

        with TestClient(app) as client:
            self.assertEqual(client.get("/health/live").status_code, 200)
            with patch("app.api.health.database_is_ready", return_value=False):
                unavailable = client.get("/health/ready")
            with patch("app.api.health.database_is_ready", return_value=True):
                ready = client.get("/health/ready")

        self.assertEqual(unavailable.status_code, 503)
        self.assertEqual(unavailable.json(), {"status": "not_ready"})
        self.assertEqual(ready.status_code, 200)
        self.assertEqual(ready.json(), {"status": "ready"})

    def test_release_migrations_are_serialized(self):
        source = inspect.getsource(migrate.upgrade_database)
        self.assertIn("pg_advisory_xact_lock", source)
        self.assertIn('command.upgrade(alembic_config, "head")', source)
        self.assertIn('alembic_config.attributes["connection"]', source)

    def test_railway_gates_deployment_on_migration_and_readiness(self):
        configuration = json.loads(
            (PROJECT_ROOT / "railway.json").read_text(encoding="utf-8")
        )
        deploy = configuration["deploy"]
        self.assertEqual(deploy["preDeployCommand"], ["python -m scripts.migrate"])
        self.assertEqual(deploy["healthcheckPath"], "/health/ready")
        self.assertIn("--timeout-graceful-shutdown 30", deploy["startCommand"])


if __name__ == "__main__":
    unittest.main()
