import inspect
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

from app.api.v1.routers import auth, users
from app.schemas.user import UserUpdate
from app.services import websocket_auth


class SecondaryAuthControlTests(unittest.TestCase):
    def test_login_and_google_auth_enforce_secondary_identity_controls(self):
        login_source = inspect.getsource(auth.login)
        google_source = inspect.getsource(auth.google_auth)
        google_userinfo_source = inspect.getsource(auth._fetch_google_userinfo)
        google_request_source = inspect.getsource(auth._BoundedGoogleRequest)

        self.assertIn("not user.is_active", login_source)
        self.assertIn("email_verified_at", login_source)
        self.assertIn("timeout=5", google_userinfo_source)
        self.assertIn("bounded_timeout", google_request_source)
        self.assertIn("not email_verified", google_source)
        self.assertIn("not user.is_active", google_source)

    def test_websocket_auth_uses_revocable_session_validation(self):
        source = inspect.getsource(websocket_auth.authenticate_websocket_user)

        self.assertIn("validate_access_token", source)
        self.assertNotIn("query_params", inspect.getsource(websocket_auth))

    def test_profile_email_change_is_rejected_before_crud_update(self):
        current_user = SimpleNamespace(email="current@example.com", id="user-id")

        with patch.object(users.crud_user, "update_user") as update_user:
            with self.assertRaises(HTTPException) as raised:
                users.update_user_me(
                    UserUpdate(email="changed@example.com"),
                    db=object(),
                    current_user=current_user,
                )

        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("verification flow", raised.exception.detail)
        update_user.assert_not_called()

    def test_unchanged_profile_email_remains_compatible_with_existing_clients(self):
        current_user = SimpleNamespace(email="current@example.com", id="user-id")
        expected = object()

        with patch.object(users.crud_user, "update_user", return_value=expected) as update_user:
            result = users.update_user_me(
                UserUpdate(email="CURRENT@example.com", full_name="Current User"),
                db=object(),
                current_user=current_user,
            )

        self.assertIs(result, expected)
        update_user.assert_called_once()


if __name__ == "__main__":
    unittest.main()
