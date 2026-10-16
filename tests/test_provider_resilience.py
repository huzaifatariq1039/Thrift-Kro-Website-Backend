import asyncio
import inspect
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import requests
from fastapi import HTTPException
from urllib3.exceptions import HTTPError as Urllib3HTTPError

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

from app.api.v1.routers import auth
from app.services import upload
from app.services.provider_resilience import (
    ProviderCircuitBreaker,
    ProviderCircuitOpenError,
    RetryPolicy,
    call_with_resilience,
    is_transient_requests_error,
)


class ProviderResilienceTests(unittest.TestCase):
    def test_transient_failure_retries_with_a_hard_attempt_cap(self):
        attempts = 0
        circuit = ProviderCircuitBreaker("test", failure_threshold=3)

        def operation():
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise requests.Timeout("temporary")
            return "ok"

        result = call_with_resilience(
            operation,
            circuit=circuit,
            retry_if=is_transient_requests_error,
            policy=RetryPolicy(max_attempts=2, base_delay_seconds=0),
        )

        self.assertEqual(result, "ok")
        self.assertEqual(attempts, 2)

    def test_non_transient_failure_is_not_retried_or_counted_by_circuit(self):
        attempts = 0
        circuit = ProviderCircuitBreaker("test", failure_threshold=1)

        def operation():
            nonlocal attempts
            attempts += 1
            raise ValueError("invalid caller input")

        with self.assertRaises(ValueError):
            call_with_resilience(
                operation,
                circuit=circuit,
                retry_if=is_transient_requests_error,
                policy=RetryPolicy(max_attempts=2, base_delay_seconds=0),
            )
        self.assertEqual(attempts, 1)
        circuit.before_call()

    def test_circuit_opens_after_repeated_logical_provider_failures(self):
        now = [100.0]
        circuit = ProviderCircuitBreaker(
            "test",
            failure_threshold=2,
            recovery_seconds=30,
            clock=lambda: now[0],
        )

        def fail():
            raise requests.Timeout("temporary")

        for _ in range(2):
            with self.assertRaises(requests.Timeout):
                call_with_resilience(
                    fail,
                    circuit=circuit,
                    retry_if=is_transient_requests_error,
                    policy=RetryPolicy(max_attempts=1, base_delay_seconds=0),
                )

        with self.assertRaises(ProviderCircuitOpenError) as opened:
            circuit.before_call()
        self.assertGreaterEqual(opened.exception.retry_after, 30)

        now[0] += 31
        circuit.before_call()

    def test_google_userinfo_retries_transient_failure_with_network_timeout(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"sub": "google-id"}
        auth._GOOGLE_IDENTITY_CIRCUIT.reset()

        with (
            patch.object(auth, "_GOOGLE_RETRY_POLICY", RetryPolicy(2, 0)),
            patch.object(
                auth.requests,
                "get",
                side_effect=[requests.Timeout("temporary"), response],
            ) as get,
        ):
            result = auth._fetch_google_userinfo("provider-token")

        self.assertEqual(result, {"sub": "google-id"})
        self.assertEqual(get.call_count, 2)
        self.assertTrue(all(call.kwargs["timeout"] == 5 for call in get.call_args_list))

    def test_google_certificate_fetch_timeout_is_capped(self):
        bounded_request = auth._BoundedGoogleRequest()

        with patch.object(
            auth.google_requests.Request,
            "__call__",
            return_value=Mock(),
        ) as provider_request:
            bounded_request("https://google.example/certs", timeout=120)

        self.assertEqual(provider_request.call_args.kwargs["timeout"], 5)

    def test_cloudinary_upload_is_timeout_bounded_idempotent_and_retried(self):
        upload._CLOUDINARY_CIRCUIT.reset()
        validated = SimpleNamespace(content=b"safe-image", extension="png")
        uploaded = {"secure_url": "https://res.cloudinary.com/example/image.png"}

        with (
            patch.object(
                upload,
                "read_validated_image_upload",
                new=AsyncMock(return_value=validated),
            ),
            patch.object(upload, "_CLOUDINARY_RETRY_POLICY", RetryPolicy(2, 0)),
            patch.object(
                upload.cloudinary.uploader,
                "upload",
                side_effect=[Urllib3HTTPError("temporary"), uploaded],
            ) as provider_upload,
        ):
            result = asyncio.run(upload.upload_image_to_cloudinary(object()))

        self.assertEqual(result, uploaded["secure_url"])
        self.assertEqual(provider_upload.call_count, 2)
        for call in provider_upload.call_args_list:
            self.assertEqual(call.kwargs["timeout"], 15)
            self.assertTrue(call.kwargs["overwrite"])

    def test_open_cloudinary_circuit_maps_to_redacted_503(self):
        circuit_error = ProviderCircuitOpenError("cloudinary_upload", 12)
        with (
            patch.object(
                upload,
                "read_validated_image_upload",
                new=AsyncMock(
                    return_value=SimpleNamespace(content=b"safe-image", extension="png")
                ),
            ),
            patch.object(
                upload,
                "call_with_resilience",
                side_effect=circuit_error,
            ),
        ):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(upload.upload_image_to_cloudinary(object()))

        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(raised.exception.headers["Retry-After"], "12")
        self.assertNotIn("cloudinary", raised.exception.detail.lower())

    def test_transaction_ownership_and_vton_deferment_are_explicit(self):
        source = inspect.getsource(call_with_resilience)
        self.assertIn("policy.max_attempts", source)
        policy = (
            os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "docs",
                "architecture",
                "transaction-ownership.md",
            )
        )
        with open(policy, encoding="utf-8") as document:
            contents = document.read()
        self.assertIn("commit exactly once", contents)
        self.assertIn("VTON inference architecture is outside", contents)


if __name__ == "__main__":
    unittest.main()
