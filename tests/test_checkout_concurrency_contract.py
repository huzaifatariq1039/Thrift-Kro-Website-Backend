import inspect
import os
import unittest

from fastapi import FastAPI

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

from app.api.v1.routers.orders import router as orders_router
from app.api.v1.routers.shopping import router as shopping_router
from app.crud.order import create_order_from_cart
from app.models.order import CheckoutOrder


class CheckoutConcurrencyContractTests(unittest.TestCase):
    def test_checkout_routes_require_idempotency_key(self):
        app = FastAPI()
        app.include_router(orders_router, prefix="/orders")
        app.include_router(shopping_router, prefix="/shopping")
        paths = app.openapi()["paths"]

        for path in ("/orders/checkout", "/shopping/cart/checkout"):
            parameters = paths[path]["post"]["parameters"]
            header = next(p for p in parameters if p["name"] == "Idempotency-Key")
            self.assertTrue(header["required"])
            self.assertEqual(header["in"], "header")

    def test_checkout_order_has_buyer_scoped_idempotency_constraint(self):
        constraints = {
            constraint.name: tuple(column.name for column in constraint.columns)
            for constraint in CheckoutOrder.__table__.constraints
            if constraint.name
        }
        self.assertEqual(
            constraints["uq_checkout_orders_buyer_idempotency_key"],
            ("buyer_id", "idempotency_key"),
        )

    def test_checkout_locks_inventory_and_never_clamps_negative_stock(self):
        source = inspect.getsource(create_order_from_cart)
        self.assertIn("with_for_update(of=ProductVariant)", source)
        self.assertIn("with_for_update()", source)
        self.assertIn("required_stock", source)
        self.assertNotIn("quantity_in_stock = 0", source)


if __name__ == "__main__":
    unittest.main()
