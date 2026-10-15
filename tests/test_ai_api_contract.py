import asyncio
import inspect
import os
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import ANY, patch
from uuid import uuid4

from fastapi import HTTPException

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

from app.api.v1.routers import ai


class RecordingWebSocket:
    def __init__(self):
        self.close_code = None
        self.close_reason = None

    async def close(self, code: int, reason: str):
        self.close_code = code
        self.close_reason = reason


class AIApiContractTests(unittest.TestCase):
    def test_status_uses_current_product_fields_and_successful_evidence(self):
        product_id = uuid4()
        verified_at = datetime.now(timezone.utc)
        product = SimpleNamespace(
            id=product_id,
            is_ai_verified=True,
            verification_hash="server-proof",
        )
        evidence = SimpleNamespace(
            similarity_score=0.91,
            detected_category="Jacket",
            verification_hash="server-proof",
            created_at=verified_at,
        )

        with (
            patch.object(ai.crud_product, "get_product", return_value=product),
            patch.object(
                ai.crud_verification,
                "get_successful_verification",
                return_value=evidence,
            ) as get_evidence,
        ):
            result = ai.get_verification_status(product_id, db=object())

        self.assertTrue(result.is_verified)
        self.assertEqual(result.similarity_score, 0.91)
        self.assertEqual(result.detected_category, "Jacket")
        self.assertEqual(result.verification_hash, "server-proof")
        self.assertEqual(result.verified_at, verified_at)
        get_evidence.assert_called_once_with(
            ANY,
            product_id=product_id,
            verification_hash="server-proof",
        )

    def test_status_does_not_trust_a_badge_without_matching_evidence(self):
        product_id = uuid4()
        product = SimpleNamespace(
            id=product_id,
            is_ai_verified=True,
            verification_hash="orphaned-proof",
        )

        with (
            patch.object(ai.crud_product, "get_product", return_value=product),
            patch.object(
                ai.crud_verification,
                "get_successful_verification",
                return_value=None,
            ),
        ):
            result = ai.get_verification_status(product_id, db=object())

        self.assertFalse(result.is_verified)
        self.assertIsNone(result.similarity_score)
        self.assertIsNone(result.verification_hash)
        self.assertIsNone(result.verified_at)

    def test_missing_product_is_a_404(self):
        with patch.object(ai.crud_product, "get_product", return_value=None):
            with self.assertRaises(HTTPException) as raised:
                ai.get_verification_status(uuid4(), db=object())

        self.assertEqual(raised.exception.status_code, 404)

    def test_deferred_websocket_closes_without_running_inference(self):
        websocket = RecordingWebSocket()

        asyncio.run(
            ai.websocket_verify(
                websocket=websocket,
                product_id=str(uuid4()),
                token="unused-while-deferred",
            )
        )

        self.assertEqual(websocket.close_code, 1013)
        self.assertIn("not available", websocket.close_reason)

        source = inspect.getsource(ai.websocket_verify)
        for obsolete_attribute in (
            "condition_score",
            "verified_at",
            "image_url",
        ):
            self.assertNotIn(obsolete_attribute, source)


if __name__ == "__main__":
    unittest.main()
