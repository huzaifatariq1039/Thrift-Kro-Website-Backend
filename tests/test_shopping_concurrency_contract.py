import inspect
import os
import unittest
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

from app.api.v1.routers import shopping as shopping_router
from app.crud.shopping import _get_or_create_cart_session, add_to_cart, toggle_wishlist


class ShoppingConcurrencyContractTests(unittest.TestCase):
    def test_cart_creation_and_line_updates_use_postgres_conflict_handling(self):
        session_source = inspect.getsource(_get_or_create_cart_session)
        cart_source = inspect.getsource(add_to_cart)

        self.assertIn("on_conflict_do_nothing", session_source)
        self.assertIn("with_for_update", session_source)
        self.assertIn("on_conflict_do_update", cart_source)
        self.assertIn("CartItem.cart_session_id", cart_source)
        self.assertIn("CartItem.product_variant_id", cart_source)

    def test_wishlist_toggle_serializes_on_its_owner(self):
        source = inspect.getsource(toggle_wishlist)

        self.assertIn("db.query(User.id)", source)
        self.assertIn("with_for_update", source)

    def test_shopping_routes_are_buyer_only(self):
        source = inspect.getsource(shopping_router)

        self.assertNotIn("get_current_active_user", source)
        self.assertGreaterEqual(source.count("Depends(get_current_buyer)"), 7)

    def test_guest_cart_scope_is_an_explicit_launch_decision(self):
        policy = (
            Path(__file__).parents[1]
            / "docs"
            / "architecture"
            / "shopping-session-policy.md"
        ).read_text(encoding="utf-8")

        self.assertIn("Guest carts are deferred", policy)
        self.assertIn("identifier rotation", policy)
        self.assertIn("transactional sign-in merge rule", policy)


if __name__ == "__main__":
    unittest.main()
