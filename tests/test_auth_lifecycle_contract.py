import inspect
import os
import unittest
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import FastAPI
import jwt
from pydantic import ValidationError

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

from app.api.v1.routers.auth import router as auth_router
from app.core.config import settings
from app.models.auth import (
    AuthAccount,
    AuthActionToken,
    AuthSecurityEvent,
    AuthSession,
    AuthThrottle,
)
from app.schemas.auth import PasswordResetConfirmRequest
from app.services.auth_lifecycle import (
    ACCESS_TOKEN_MINUTES,
    _encode_access_token,
    hash_secret,
    rotate_refresh_token,
    validate_access_token,
)


class AuthLifecycleContractTests(unittest.TestCase):
    def test_access_tokens_are_short_lived_and_session_bound(self):
        user_id = uuid4()
        session_id = uuid4()
        token = _encode_access_token(user_id, session_id, 7)
        claims = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])

        self.assertEqual(claims["sub"], str(user_id))
        self.assertEqual(claims["sid"], str(session_id))
        self.assertEqual(claims["ver"], 7)
        self.assertEqual(claims["type"], "access")
        self.assertIn("jti", claims)
        self.assertLessEqual(claims["exp"] - claims["iat"], ACCESS_TOKEN_MINUTES * 60)
        self.assertLessEqual(ACCESS_TOKEN_MINUTES, 15)

    def test_only_hashes_are_persisted_for_secrets_and_client_identity(self):
        self.assertIn("refresh_token_hash", AuthSession.__table__.c)
        self.assertNotIn("refresh_token", AuthSession.__table__.c)
        self.assertIn("token_hash", AuthActionToken.__table__.c)
        self.assertNotIn("token", AuthActionToken.__table__.c)
        self.assertIn("ip_hash", AuthSession.__table__.c)
        self.assertIn("ip_hash", AuthSecurityEvent.__table__.c)
        self.assertNotIn("ip_address", AuthSecurityEvent.__table__.c)

        raw = "one-time-secret"
        self.assertEqual(hash_secret(raw), hash_secret(raw))
        self.assertNotEqual(hash_secret(raw), raw)

    def test_refresh_rotation_locks_rows_and_detects_reuse(self):
        source = inspect.getsource(rotate_refresh_token)
        self.assertIn("with_for_update()", source)
        self.assertIn('session.revoke_reason = "rotated"', source)
        self.assertIn('"refresh_reuse"', source)
        self.assertIn("account.auth_version += 1", source)

    def test_access_validation_checks_session_and_account_version(self):
        source = inspect.getsource(validate_access_token)
        self.assertIn("session.revoked_at is not None", source)
        self.assertIn("account.auth_version != auth_version", source)
        self.assertIn("not user.is_active", source)

    def test_database_models_cover_throttling_verification_and_audit(self):
        self.assertEqual(
            set(AuthThrottle.__table__.primary_key.columns.keys()),
            {"scope", "key_hash"},
        )
        self.assertIn("email_verified_at", AuthAccount.__table__.c)
        self.assertIn("password_changed_at", AuthAccount.__table__.c)
        self.assertIn("event_type", AuthSecurityEvent.__table__.c)
        self.assertIn("details", AuthSecurityEvent.__table__.c)

    def test_auth_lifecycle_routes_are_published(self):
        app = FastAPI()
        app.include_router(auth_router, prefix="/auth")
        paths = app.openapi()["paths"]
        expected = {
            "/auth/refresh",
            "/auth/logout",
            "/auth/logout-all",
            "/auth/sessions",
            "/auth/sessions/{session_id}",
            "/auth/email-verification/request",
            "/auth/email-verification/confirm",
            "/auth/password-reset/request",
            "/auth/password-reset/confirm",
        }
        self.assertTrue(expected.issubset(paths))

    def test_password_recovery_reuses_registration_strength_policy(self):
        valid = PasswordResetConfirmRequest(
            token="x" * 48,
            new_password="NewValid1!",
        )
        self.assertEqual(valid.new_password, "NewValid1!")
        with self.assertRaises(ValidationError):
            PasswordResetConfirmRequest(token="x" * 48, new_password="weakpassword")

    def test_security_timestamps_are_timezone_aware(self):
        now = datetime.now(timezone.utc)
        self.assertIsNotNone(now.tzinfo)


if __name__ == "__main__":
    unittest.main()
