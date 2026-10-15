import os
import unittest
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

from app.crud.product import create_product
from app.models.product import Category, ConditionEnum
from app.models.user import RoleEnum, User
from app.schemas.product import ProductCreate


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@unittest.skipUnless(
    TEST_DATABASE_URL,
    "Set TEST_DATABASE_URL to an isolated migrated PostgreSQL database",
)
class CatalogPostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
        cls.Session = sessionmaker(bind=cls.engine, autoflush=False, autocommit=False)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def test_product_creation_persists_normalized_relations(self):
        marker = uuid.uuid4().hex
        with self.Session() as db:
            seller = User(
                email=f"catalog-seller-{marker}@example.test",
                full_name="Catalog Seller",
                hex_code=f"catalog-seller-{marker}",
                role=RoleEnum.SELLER,
            )
            category = Category(name=f"Jackets {marker}", slug=f"jackets-{marker}")
            db.add_all([seller, category])
            db.flush()

            product = create_product(
                db,
                ProductCreate.model_validate(
                    {
                        "name": f"Jacket {marker}",
                        "price": 2500,
                        "condition": ConditionEnum.GOOD,
                        "category_id": category.id,
                        "images": [
                            {
                                "image_url": "https://media.example.test/jacket.jpg",
                                "is_primary": True,
                            }
                        ],
                        "variants": [
                            {
                                "sku": f"JACKET-{marker}",
                                "attributes": {"size": "M"},
                                "quantity_in_stock": 2,
                            }
                        ],
                        "tags": ["denim"],
                    }
                ),
                seller.id,
            )

            self.assertEqual(product.category.id, category.id)
            self.assertEqual(len(product.images), 1)
            self.assertTrue(product.images[0].is_primary)
            self.assertEqual(len(product.variants), 1)
            self.assertEqual(product.variants[0].attributes, {"size": "M"})
            self.assertEqual([tag.tag_name for tag in product.tags], ["denim"])
            self.assertFalse(product.is_ai_verified)


if __name__ == "__main__":
    unittest.main()
