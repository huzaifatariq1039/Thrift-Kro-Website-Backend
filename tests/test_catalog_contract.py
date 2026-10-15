import os
import unittest

from pydantic import ValidationError
from sqlalchemy.orm.interfaces import MANYTOONE, ONETOMANY

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

from app.main import app
from app.models.product import Category
from app.schemas.product import ProductCreate


def normalized_product_payload() -> dict:
    return {
        "name": "Normalized denim jacket",
        "description": "A catalog-contract fixture",
        "price": 2500,
        "original_price": 5000,
        "brand": "Thrift Kro",
        "condition": "Good",
        "images": [
            {
                "image_url": "https://media.example.test/jacket.jpg",
                "is_primary": True,
                "display_order": 0,
            }
        ],
        "variants": [
            {
                "sku": "JACKET-M",
                "attributes": {"size": "M"},
                "quantity_in_stock": 2,
            }
        ],
        "tags": ["denim", "jacket"],
    }


class CatalogContractTests(unittest.TestCase):
    def test_product_create_accepts_only_the_normalized_contract(self):
        product = ProductCreate.model_validate(normalized_product_payload())

        self.assertEqual(product.images[0].image_url, "https://media.example.test/jacket.jpg")
        self.assertEqual(product.variants[0].attributes, {"size": "M"})

        for legacy_field, value in (
            ("image_url", "https://media.example.test/legacy.jpg"),
            ("category", "jackets"),
            ("department", "men"),
            ("size", "M"),
        ):
            with self.subTest(legacy_field=legacy_field):
                payload = normalized_product_payload()
                payload[legacy_field] = value
                with self.assertRaises(ValidationError):
                    ProductCreate.model_validate(payload)

    def test_product_create_requires_images_and_variants(self):
        for missing_field in ("images", "variants"):
            with self.subTest(missing_field=missing_field):
                payload = normalized_product_payload()
                del payload[missing_field]
                with self.assertRaises(ValidationError):
                    ProductCreate.model_validate(payload)

    def test_openapi_exposes_catalog_provider_routes(self):
        openapi = app.openapi()
        paths = openapi["paths"]
        schema = openapi["components"]["schemas"]["ProductCreate"]

        self.assertIn("/api/v1/categories/", paths)
        self.assertIn("/api/v1/products/seller/me", paths)
        self.assertEqual(paths["/api/v1/products/"]["post"]["responses"].keys() & {"201"}, {"201"})
        self.assertTrue({"images", "variants"}.issubset(schema["required"]))
        self.assertEqual(schema["additionalProperties"], False)
        self.assertFalse(
            {"image_url", "category", "department", "size", "is_ai_verified"}
            & schema["properties"].keys()
        )

    def test_category_hierarchy_has_correct_relationship_directions(self):
        relationships = Category.__mapper__.relationships

        self.assertEqual(relationships["parent"].direction, MANYTOONE)
        self.assertFalse(relationships["parent"].uselist)
        self.assertEqual(relationships["subcategories"].direction, ONETOMANY)
        self.assertTrue(relationships["subcategories"].uselist)


if __name__ == "__main__":
    unittest.main()
