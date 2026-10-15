import asyncio
import inspect
import os
import unittest

from fastapi import HTTPException
from pydantic import ValidationError

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

import app.crud.product as crud_product
from app.api.v1.routers import ai, products
from app.models.product import ConditionEnum
from app.schemas.product import ProductCreate


def valid_product_payload() -> dict:
    return {
        "name": "Verified fields stay server-owned",
        "price": 1000,
        "condition": ConditionEnum.GOOD,
        "images": [{"image_url": "https://media.example.test/product.jpg"}],
        "variants": [{"attributes": {"size": "M"}, "quantity_in_stock": 1}],
    }


class ProductVerificationTrustTests(unittest.TestCase):
    def test_product_create_rejects_client_owned_verification_fields(self):
        for field, value in (
            ("is_ai_verified", True),
            ("condition_score", 99),
            ("verification_hash", "client-forged-proof"),
        ):
            with self.subTest(field=field):
                payload = valid_product_payload()
                payload[field] = value
                with self.assertRaisesRegex(ValidationError, "server-managed"):
                    ProductCreate.model_validate(payload)

    def test_product_create_path_has_no_verification_override(self):
        self.assertNotIn("is_ai_verified", inspect.signature(crud_product.create_product).parameters)
        self.assertNotIn("condition_score", inspect.signature(crud_product.create_product).parameters)

        route_source = inspect.getsource(products.create_product)
        self.assertNotIn("product.is_ai_verified", route_source)
        self.assertNotIn("product.condition_score", route_source)

        persistence_source = inspect.getsource(crud_product.create_product)
        self.assertIn("is_ai_verified=False", persistence_source)
        self.assertIn("verification_hash=None", persistence_source)

    def test_legacy_mock_endpoint_reports_engine_as_unavailable(self):
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(ai.verify_product(current_seller=object()))

        self.assertEqual(raised.exception.status_code, 503)
        self.assertIn("not available", raised.exception.detail)


if __name__ == "__main__":
    unittest.main()
