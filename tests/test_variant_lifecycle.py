import inspect
import os
import unittest

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

from app.crud.order import create_order_from_cart
from app.crud.shopping import add_to_cart
from app.models.product import ProductVariant
from app.models.shopping import CartItem
from app.services.product_variants import reconcile_product_variants


class VariantLifecycleTests(unittest.TestCase):
    def test_variants_have_explicit_archive_state(self):
        self.assertIn("is_active", ProductVariant.__table__.c)
        self.assertIn("archived_at", ProductVariant.__table__.c)

    def test_cart_reference_cannot_cascade_delete(self):
        foreign_key = next(iter(CartItem.__table__.c.product_variant_id.foreign_keys))
        self.assertEqual(foreign_key.ondelete, "RESTRICT")

    def test_reconciliation_archives_instead_of_deleting(self):
        source = inspect.getsource(reconcile_product_variants)
        self.assertNotIn(".delete(", source)
        self.assertIn("variant.is_active = False", source)
        self.assertIn("with_for_update()", source)

    def test_cart_and_checkout_reject_archived_variants(self):
        self.assertIn("not variant.is_active", inspect.getsource(add_to_cart))
        self.assertIn("not variant.is_active", inspect.getsource(create_order_from_cart))


if __name__ == "__main__":
    unittest.main()
