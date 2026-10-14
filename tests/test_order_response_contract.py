import os
import unittest
from types import SimpleNamespace
from uuid import uuid4

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

from app.models.order import CheckoutOrder, OrderItem, OrderStatusEnum, PaymentMethodEnum, SellerOrder
from app.schemas.order import OrderResponse, SellerOrderSchema


def make_seller_order():
    product_id = uuid4()
    item = OrderItem(
        id=uuid4(),
        product_variant_id=uuid4(),
        product_id_snapshot=product_id,
        product_name_snapshot="Snapshot Jacket",
        product_image_snapshot="https://example.test/jacket.jpg",
        sku_snapshot="JACKET-BLK-M",
        variant_attributes_snapshot={"color": "black", "size": "M"},
        quantity=2,
        price_at_purchase=600.0,
        currency="PKR",
    )
    seller_order = SellerOrder(
        id=uuid4(),
        seller_id=uuid4(),
        subtotal=1200.0,
        shipping_fee=200.0,
        platform_fee=60.0,
        total_amount=1460.0,
        currency="PKR",
        status=OrderStatusEnum.PROCESSING,
        tracking_number=None,
        courier_name=None,
        shipped_at=None,
        delivered_at=None,
        created_at=None,
        order_items=[item],
    )
    seller_order.checkout_order = CheckoutOrder(
        shipping_address_snapshot={
            "type": "SHIPPING",
            "full_name": "Original Buyer",
            "phone_number": "+920000000000",
            "street_address": "1 Checkout Road",
            "city": "Lahore",
            "state_province": "Punjab",
            "postal_code": "54000",
            "country": "Pakistan",
        }
    )
    return seller_order


class OrderResponseContractTests(unittest.TestCase):
    def test_seller_order_maps_orm_order_items_to_public_items(self):
        response = SellerOrderSchema.model_validate(make_seller_order())

        self.assertEqual(len(response.items), 1)
        self.assertEqual(response.items[0].quantity, 2)
        self.assertEqual(response.items[0].price_at_purchase, 600.0)
        self.assertEqual(response.items[0].product_name, "Snapshot Jacket")
        self.assertEqual(response.items[0].sku, "JACKET-BLK-M")
        self.assertEqual(response.shipping_address.street_address, "1 Checkout Road")

        payload = response.model_dump(mode="json")
        self.assertIn("items", payload)
        self.assertNotIn("order_items", payload)

    def test_checkout_order_includes_nested_seller_order_items(self):
        order = SimpleNamespace(
            id=uuid4(),
            buyer_id=uuid4(),
            total_amount=1460.0,
            currency="PKR",
            payment_method=PaymentMethodEnum.CASH_ON_DELIVERY,
            shipping_address_id=None,
            shipping_address_snapshot={
                "type": "SHIPPING",
                "full_name": "Original Buyer",
                "phone_number": "+920000000000",
                "street_address": "1 Checkout Road",
                "city": "Lahore",
                "state_province": "Punjab",
                "postal_code": "54000",
                "country": "Pakistan",
            },
            billing_address_snapshot=None,
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
        self.assertEqual(response.shipping_address.full_name, "Original Buyer")

    def test_response_uses_purchase_snapshot_instead_of_mutable_catalog_data(self):
        seller_order = make_seller_order()
        seller_order.order_items[0].product_variant = SimpleNamespace(
            sku="CHANGED-SKU",
            attributes={"color": "changed"},
            product=SimpleNamespace(name="Changed Product", images=[]),
        )

        response = SellerOrderSchema.model_validate(seller_order)

        self.assertEqual(response.items[0].product_name, "Snapshot Jacket")
        self.assertEqual(response.items[0].sku, "JACKET-BLK-M")
        self.assertEqual(response.items[0].variant_attributes, {"color": "black", "size": "M"})


if __name__ == "__main__":
    unittest.main()
