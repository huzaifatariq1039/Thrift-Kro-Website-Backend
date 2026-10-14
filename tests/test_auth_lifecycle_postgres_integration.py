import os
import unittest
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

from app.models.auth import AuthAccount, AuthSecurityEvent, AuthThrottle
from app.models.user import RoleEnum, User
from app.services.auth_lifecycle import (
    AuthenticationError,
    RateLimitExceeded,
    clear_rate_limit,
    consume_rate_limit,
    issue_session,
    rotate_refresh_token,
    validate_access_token,
)


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@unittest.skipUnless(
    TEST_DATABASE_URL,
    "Set TEST_DATABASE_URL to an isolated migrated PostgreSQL database",
)
class AuthLifecyclePostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
        cls.Session = sessionmaker(bind=cls.engine, autoflush=False, autocommit=False)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        self.marker = uuid.uuid4().hex
        with self.Session() as db:
            user = User(
                email=f"auth-{self.marker}@example.test",
                full_name="Auth Lifecycle User",
                hex_code=f"auth-{self.marker}",
                role=RoleEnum.BUYER,
                is_active=True,
            )
            db.add(user)
            db.flush()
            db.add(AuthAccount(user_id=user.id, auth_version=1))
            db.commit()
            self.user_id = user.id

    def tearDown(self):
        with self.Session() as db:
            db.query(AuthSecurityEvent).filter(
                AuthSecurityEvent.user_id == self.user_id
            ).delete(synchronize_session=False)
            db.query(User).filter(User.id == self.user_id).delete(synchronize_session=False)
            db.query(AuthThrottle).filter(
                AuthThrottle.scope == "test_auth_limit"
            ).delete(synchronize_session=False)
            db.commit()

    def test_refresh_rotation_and_reuse_revoke_the_entire_family(self):
        with self.Session() as db:
            user = db.get(User, self.user_id)
            first = issue_session(
                db,
                user,
                ip_address="192.0.2.10",
                user_agent="integration-test",
            )
            self.assertEqual(validate_access_token(db, first.access_token).user.id, user.id)

            second = rotate_refresh_token(
                db,
                first.refresh_token,
                ip_address="192.0.2.10",
                user_agent="integration-test",
            )
            with self.assertRaises(AuthenticationError):
                validate_access_token(db, first.access_token)
            self.assertEqual(validate_access_token(db, second.access_token).user.id, user.id)

            with self.assertRaises(AuthenticationError):
                rotate_refresh_token(
                    db,
                    first.refresh_token,
                    ip_address="192.0.2.11",
                    user_agent="replay-test",
                )
            with self.assertRaises(AuthenticationError):
                validate_access_token(db, second.access_token)

    def test_database_rate_limit_blocks_and_can_be_cleared(self):
        key = f"limit-{self.marker}"
        with self.Session() as db:
            for _ in range(2):
                consume_rate_limit(
                    db,
                    scope="test_auth_limit",
                    key=key,
                    limit=2,
                    window_seconds=60,
                    block_seconds=60,
                )
            with self.assertRaises(RateLimitExceeded):
                consume_rate_limit(
                    db,
                    scope="test_auth_limit",
                    key=key,
                    limit=2,
                    window_seconds=60,
                    block_seconds=60,
                )
            clear_rate_limit(db, scope="test_auth_limit", key=key)
            consume_rate_limit(
                db,
                scope="test_auth_limit",
                key=key,
                limit=2,
                window_seconds=60,
                block_seconds=60,
            )


if __name__ == "__main__":
    unittest.main()
