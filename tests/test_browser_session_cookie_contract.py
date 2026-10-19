import inspect
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

from fastapi import Request, Response

from app.api.v1.routers import auth


class BrowserSessionCookieContractTests(unittest.TestCase):
    @staticmethod
    def _request(*, remember=False):
        headers = [(b"x-session-transport", b"cookie")]
        if remember:
            headers.append((b"x-remember-session", b"true"))
        return Request({"type": "http", "method": "POST", "path": "/", "headers": headers})

    def test_refresh_cookie_is_http_only_and_environment_appropriate(self):
        source = inspect.getsource(auth._set_refresh_cookie)
        self.assertIn("httponly=True", source)
        self.assertIn("secure=secure", source)
        self.assertIn('samesite="none" if secure else "lax"', source)
        self.assertIn("_REFRESH_COOKIE_PATH", source)
        self.assertIn("_remember_session(request)", source)

    def test_browser_can_refresh_from_cookie_while_api_clients_keep_body_support(self):
        source = inspect.getsource(auth.refresh_token)
        self.assertIn("body: RefreshTokenRequest | None = None", source)
        self.assertIn("request.cookies.get(_REFRESH_COOKIE_NAME)", source)
        self.assertIn("_set_refresh_cookie(response, request, pair.refresh_token)", source)
        self.assertIn("expose_refresh_token=not cookie_session", source)

    def test_cookie_session_does_not_expose_refresh_secret_in_json(self):
        source = inspect.getsource(auth._token_response)
        self.assertIn("expose_refresh_token", source)
        self.assertIn("pair.refresh_token if expose_refresh_token else None", source)
        self.assertTrue(auth.AuthTokenResponse.model_fields["refresh_token"].is_required() is False)
        router_source = inspect.getsource(auth)
        self.assertEqual(router_source.count("response_model_exclude_none=True"), 3)

    def test_login_rotation_and_logout_manage_the_cookie(self):
        self.assertIn("_set_refresh_cookie", inspect.getsource(auth.login))
        self.assertIn("_set_refresh_cookie", inspect.getsource(auth.google_auth))
        self.assertIn("_delete_refresh_cookie", inspect.getsource(auth.logout))
        self.assertIn("_delete_refresh_cookie", inspect.getsource(auth.logout_all))

    def test_production_cookie_flags_and_remembered_lifetime(self):
        response = Response()
        with patch.dict(os.environ, {"APP_ENV": "production"}):
            auth._set_refresh_cookie(response, self._request(remember=True), "secret")
        cookie = response.headers["set-cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("Secure", cookie)
        self.assertIn("SameSite=none", cookie)
        self.assertIn("Max-Age=", cookie)
        self.assertIn("Path=/api/v1/auth", cookie)

    def test_non_remembered_cookie_is_browser_session_scoped(self):
        response = Response()
        auth._set_refresh_cookie(response, self._request(), "secret")
        cookie = response.headers["set-cookie"]
        self.assertNotIn("Max-Age=", cookie)
        self.assertNotIn("Expires=", cookie)


if __name__ == "__main__":
    unittest.main()
