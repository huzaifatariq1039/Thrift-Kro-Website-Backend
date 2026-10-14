import os
import unittest
from types import SimpleNamespace
from uuid import uuid4

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

from app.models.order import OrderItem, OrderStatusEnum, PaymentMethodEnum, SellerOrder
from app.schemas.order import OrderResponse, SellerOrderSchema


def make_seller_order():
    item = OrderItem(
        id=uuid4(),
        product_variant_id=uuid4(),
        quantity=2,
        price_at_purchase=600.0,
    )
    return SellerOrder(
        id=uuid4(),
        seller_id=uuid4(),
        subtotal=1200.0,
        shipping_fee=200.0,
        platform_fee=60.0,
        total_amount=1460.0,
        status=OrderStatusEnum.PROCESSING,
        tracking_number=None,
        courier_name=None,
        shipped_at=None,
        delivered_at=None,
        created_at=None,
        order_items=[item],
    )


class OrderResponseContractTests(unittest.TestCase):
    def test_seller_order_maps_orm_order_items_to_public_items(self):
        response = SellerOrderSchema.model_validate(make_seller_order())

        self.assertEqual(len(response.items), 1)
        self.assertEqual(response.items[0].quantity, 2)
        self.assertEqual(response.items[0].price_at_purchase, 600.0)

        payload = response.model_dump(mode="json")
        self.assertIn("items", payload)
        self.assertNotIn("order_items", payload)

    def test_checkout_order_includes_nested_seller_order_items(self):
        order = SimpleNamespace(
            id=uuid4(),
            buyer_id=uuid4(),
            total_amount=1460.0,
            payment_method=PaymentMethodEnum.CASH_ON_DELIVERY,
            shipping_address_id=None,
            created_at=None,
            updated_at=None,
            seller_orders=[make_seller_order()],
            overall_status="PROCESSING",
        )

        response = OrderResponse.model_validate(order)

        self.assertEqual(len(response.seller_orders), 1)
        self.assertEqual(len(response.seller_orders[0].items), 1)
        self.assertEqual(
            response.seller_orders[0].items[0].product_variant_id,
            order.seller_orders[0].order_items[0].product_variant_id,
        )


if __name__ == "__main__":
    unittest.main()
