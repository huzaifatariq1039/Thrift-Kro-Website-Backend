import os
import unittest
import uuid
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

import app.crud.category as crud_category
import app.crud.product as crud_product
from app.crud.product import create_product
from app.models.product import Category, ConditionEnum, Product
from app.models.media import (
    MediaAsset,
    MediaModerationStatusEnum,
    MediaPurposeEnum,
    MediaStatusEnum,
    MediaVisibilityEnum,
)
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
            image_url = f"https://media.example.test/{marker}/jacket.jpg"
            asset = MediaAsset(
                owner_id=seller.id,
                provider="cloudinary",
                provider_public_id=f"thriftkro/products/{marker}",
                secure_url=image_url,
                purpose=MediaPurposeEnum.PRODUCT_IMAGE,
                visibility=MediaVisibilityEnum.PUBLIC,
                status=MediaStatusEnum.PENDING,
                moderation_status=MediaModerationStatusEnum.NOT_REVIEWED,
                content_type="image/jpeg",
                byte_size=128,
                width=10,
                height=10,
            )
            db.add(asset)
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
                                "image_url": image_url,
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
            self.assertEqual(product.images[0].media_asset_id, asset.id)
            self.assertEqual(asset.status, MediaStatusEnum.ATTACHED)
            self.assertEqual(len(product.variants), 1)
            self.assertEqual(product.variants[0].attributes, {"size": "M"})
            self.assertEqual([tag.tag_name for tag in product.tags], ["denim"])
            self.assertFalse(product.is_ai_verified)

    def test_public_queries_hide_archived_catalog_records(self):
        marker = uuid.uuid4().hex
        with self.Session() as db:
            seller = User(
                email=f"catalog-visibility-{marker}@example.test",
                full_name="Catalog Visibility Seller",
                hex_code=f"catalog-visibility-{marker}",
                role=RoleEnum.SELLER,
            )
            active_root = Category(name=f"Active {marker}", slug=f"active-{marker}")
            inactive_root = Category(
                name=f"Inactive {marker}",
                slug=f"inactive-{marker}",
                is_active=False,
            )
            active_child = Category(
                name=f"Active Child {marker}",
                slug=f"active-child-{marker}",
                parent=active_root,
            )
            inactive_child = Category(
                name=f"Inactive Child {marker}",
                slug=f"inactive-child-{marker}",
                parent=active_root,
                is_active=False,
            )
            db.add_all(
                [seller, active_root, inactive_root, active_child, inactive_child]
            )
            db.flush()
            live_product = Product(
                seller_id=seller.id,
                category_id=active_root.id,
                name=f"Live {marker}",
                condition=ConditionEnum.GOOD,
                price=100,
            )
            deleted_product = Product(
                seller_id=seller.id,
                category_id=active_root.id,
                name=f"Deleted {marker}",
                condition=ConditionEnum.GOOD,
                price=100,
                deleted_at=datetime.now(timezone.utc),
            )
            db.add_all([live_product, deleted_product])
            db.commit()
            seller_id = seller.id
            active_root_id = active_root.id
            inactive_root_id = inactive_root.id
            active_child_id = active_child.id
            deleted_product_id = deleted_product.id
            live_product_id = live_product.id

        with self.Session() as db:
            public_product_ids = {
                product.id for product in crud_product.get_products(db, limit=100)
            }
            self.assertIn(live_product_id, public_product_ids)
            self.assertNotIn(deleted_product_id, public_product_ids)
            self.assertIsNone(crud_product.get_public_product(db, deleted_product_id))
            self.assertIsNotNone(crud_product.get_product(db, deleted_product_id))
            seller_product_ids = {
                product.id
                for product in crud_product.get_products(
                    db,
                    seller_id=seller_id,
                    include_deleted=True,
                    limit=100,
                )
            }
            self.assertIn(deleted_product_id, seller_product_ids)

            public_roots = crud_category.get_categories(db, limit=100)
            public_root_ids = {category.id for category in public_roots}
            self.assertIn(active_root_id, public_root_ids)
            self.assertNotIn(inactive_root_id, public_root_ids)

            active_root_result = next(
                category for category in public_roots if category.id == active_root_id
            )
            self.assertEqual(
                {category.id for category in active_root_result.subcategories},
                {active_child_id},
            )
            self.assertIsNone(
                crud_category.get_active_category(db, inactive_root_id)
            )
            self.assertIsNotNone(crud_category.get_category(db, inactive_root_id))
            admin_category_ids = {
                category.id
                for category in crud_category.get_all_categories(
                    db,
                    include_inactive=True,
                    limit=100,
                )
            }
            self.assertIn(inactive_root_id, admin_category_ids)


if __name__ == "__main__":
    unittest.main()
