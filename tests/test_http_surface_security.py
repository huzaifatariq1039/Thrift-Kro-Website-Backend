import asyncio
import inspect
import json
import os
import unittest
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

from app.api.v1.routers import products, vto
from app.core.http_security import (
    load_http_security_policy,
    unhandled_exception_response,
)
from app.core.observability import ObservabilityMiddleware
from app.services import upload


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class HttpSurfaceSecurityTests(unittest.TestCase):
    def test_missing_development_configuration_denies_cross_origin_access(self):
        policy = load_http_security_policy({})

        self.assertEqual(policy.allowed_origins, ())
        self.assertFalse(policy.docs_enabled)

        explicit_development = load_http_security_policy(
            {
                "ALLOWED_ORIGINS": "http://localhost:5173",
                "ENABLE_API_DOCS": "true",
            }
        )
        self.assertEqual(
            explicit_development.allowed_origins,
            ("http://localhost:5173",),
        )
        self.assertTrue(explicit_development.docs_enabled)

    def test_production_requires_explicit_non_wildcard_origins_and_disables_docs(self):
        with self.assertRaises(RuntimeError):
            load_http_security_policy({"APP_ENV": "production"})
        with self.assertRaises(RuntimeError):
            load_http_security_policy(
                {"APP_ENV": "production", "ALLOWED_ORIGINS": "*"}
            )

        policy = load_http_security_policy(
            {
                "APP_ENV": "production",
                "ALLOWED_ORIGINS": "https://thriftkro.example.com",
                "ENABLE_API_DOCS": "true",
            }
        )
        self.assertEqual(
            policy.allowed_origins,
            ("https://thriftkro.example.com",),
        )
        self.assertFalse(policy.docs_enabled)

    def test_origin_entries_cannot_include_paths(self):
        with self.assertRaises(RuntimeError):
            load_http_security_policy(
                {
                    "APP_ENV": "production",
                    "ALLOWED_ORIGINS": "https://thriftkro.example.com/api",
                }
            )

    def test_unhandled_exception_response_is_correlated_and_redacted(self):
        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/failure",
                "headers": [],
                "request_id": "request-123",
            }
        )
        with self.assertLogs("app.core.http_security", level="ERROR") as logs:
            response = asyncio.run(
                unhandled_exception_response(
                    request,
                    RuntimeError("postgres password and provider response"),
                )
            )
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 500)
        self.assertEqual(payload["code"], "internal_error")
        self.assertEqual(payload["request_id"], "request-123")
        self.assertNotIn("postgres", response.body.decode())
        self.assertNotIn("provider response", response.body.decode())
        self.assertNotIn("provider response", "\n".join(logs.output))

    def test_fallback_handler_preserves_the_observability_request_id(self):
        app = FastAPI()
        app.add_exception_handler(Exception, unhandled_exception_response)
        app.add_middleware(ObservabilityMiddleware)

        @app.get("/failure")
        def failure():
            raise RuntimeError("database connection includes a secret")

        client = TestClient(app, raise_server_exceptions=False)
        with self.assertLogs("app.core.http_security", level="ERROR") as logs:
            response = client.get("/failure")
        payload = response.json()

        self.assertEqual(response.status_code, 500)
        self.assertEqual(payload["request_id"], response.headers["X-Request-ID"])
        self.assertNotIn("secret", response.text)
        self.assertNotIn("secret", "\n".join(logs.output))

    def test_provider_and_database_failures_use_stable_public_messages(self):
        product_source = inspect.getsource(products.import_products_csv)
        upload_source = inspect.getsource(upload.upload_image_to_cloudinary)
        vto_source = inspect.getsource(vto.generate_vton)

        self.assertNotIn('error=f"Database error:', product_source)
        self.assertIn("Product import could not be completed", product_source)
        self.assertIn("Image storage is temporarily unavailable", upload_source)
        self.assertNotIn('f"VTON generation failed:', vto_source)
        self.assertIn("Virtual try-on is temporarily unavailable", vto_source)

    def test_application_wires_the_runtime_policy_into_fastapi(self):
        source = (PROJECT_ROOT / "app" / "main.py").read_text(encoding="utf-8")

        self.assertIn("load_http_security_policy()", source)
        self.assertIn("docs_url=", source)
        self.assertIn("app.add_exception_handler", source)
        self.assertNotIn('os.getenv("ALLOWED_ORIGINS", "*")', source)


if __name__ == "__main__":
    unittest.main()
