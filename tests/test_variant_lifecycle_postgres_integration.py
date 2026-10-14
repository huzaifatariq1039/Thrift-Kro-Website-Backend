import os
import unittest
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

from app.models.product import ConditionEnum, Product, ProductStatusEnum, ProductVariant
from app.models.shopping import CartItem, CartSession
from app.models.user import RoleEnum, User
from app.services.product_variants import reconcile_product_variants


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@unittest.skipUnless(
    TEST_DATABASE_URL,
    "Set TEST_DATABASE_URL to an isolated migrated PostgreSQL database",
)
class VariantLifecyclePostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
        cls.Session = sessionmaker(bind=cls.engine, autoflush=False, autocommit=False)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def test_update_preserves_identity_and_archives_omitted_variant(self):
        marker = uuid.uuid4().hex
        with self.Session() as db:
            seller = User(
                email=f"variant-seller-{marker}@example.test",
                full_name="Variant Seller",
                hex_code=f"variant-seller-{marker}",
                role=RoleEnum.SELLER,
            )
            buyer = User(
                email=f"variant-buyer-{marker}@example.test",
                full_name="Variant Buyer",
                hex_code=f"variant-buyer-{marker}",
                role=RoleEnum.BUYER,
            )
            db.add_all([seller, buyer])
            db.flush()
            product = Product(
                seller_id=seller.id,
                name=f"Stable variants {marker}",
                condition=ConditionEnum.GOOD,
                price=1000,
                status=ProductStatusEnum.AVAILABLE,
            )
            db.add(product)
            db.flush()
            kept = ProductVariant(
                product_id=product.id,
                sku=f"keep-{marker}",
                attributes={"size": "M"},
                quantity_in_stock=2,
            )
            omitted = ProductVariant(
                product_id=product.id,
                sku=f"archive-{marker}",
                attributes={"size": "L"},
                quantity_in_stock=1,
            )
            cart = CartSession(user_id=buyer.id)
            db.add_all([kept, omitted, cart])
            db.flush()
            db.add(CartItem(
                cart_session_id=cart.id,
                product_variant_id=omitted.id,
                quantity=1,
            ))
            db.commit()
            kept_id = kept.id
            omitted_id = omitted.id
            product_id = product.id

        with self.Session() as db:
            reconcile_product_variants(db, product_id, [{
                "sku": f"keep-{marker}",
                "attributes": {"size": "M", "color": "black"},
                "price_adjustment": 50,
                "quantity_in_stock": 3,
            }])
            db.commit()

        with self.Session() as db:
            kept = db.get(ProductVariant, kept_id)
            omitted = db.get(ProductVariant, omitted_id)
            cart_item = db.query(CartItem).filter(CartItem.product_variant_id == omitted_id).one()
            self.assertTrue(kept.is_active)
            self.assertEqual(kept.quantity_in_stock, 3)
            self.assertFalse(omitted.is_active)
            self.assertEqual(omitted.quantity_in_stock, 0)
            self.assertIsNotNone(omitted.archived_at)
            self.assertEqual(cart_item.product_variant_id, omitted_id)


if __name__ == "__main__":
    unittest.main()
