import os
import unittest
import uuid

from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

from app.models.audit import AuditEvent


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@unittest.skipUnless(
    TEST_DATABASE_URL,
    "Set TEST_DATABASE_URL to an isolated migrated PostgreSQL database",
)
class ObservabilityPostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
        cls.Session = sessionmaker(bind=cls.engine, autoflush=False, autocommit=False)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def test_audit_events_cannot_be_updated_or_deleted(self):
        event_id = uuid.uuid4()
        with self.Session() as db:
            db.add(
                AuditEvent(
                    id=event_id,
                    actor_id=uuid.uuid4(),
                    action="integration.created",
                    resource_type="integration_test",
                    resource_id=uuid.uuid4(),
                    details={"marker": uuid.uuid4().hex},
                )
            )
            db.commit()

            with self.assertRaises(DBAPIError):
                db.execute(
                    text("UPDATE audit_events SET action = 'tampered' WHERE id = :id"),
                    {"id": event_id},
                )
                db.commit()
            db.rollback()

            with self.assertRaises(DBAPIError):
                db.execute(text("DELETE FROM audit_events WHERE id = :id"), {"id": event_id})
                db.commit()
            db.rollback()

            remaining = db.execute(
                text("SELECT action FROM audit_events WHERE id = :id"),
                {"id": event_id},
            ).scalar_one()
            self.assertEqual(remaining, "integration.created")


if __name__ == "__main__":
    unittest.main()
