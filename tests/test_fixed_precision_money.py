import os
import unittest
from decimal import Decimal

from sqlalchemy import Numeric

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

from app.core.money import money
from app.models.order import CheckoutOrder, OrderItem, OrderPayment, SellerOrder
from app.models.product import Product, ProductVariant
from app.models.user import Transaction, Wallet


class FixedPrecisionMoneyTests(unittest.TestCase):
    def test_money_rounds_half_up_to_two_decimal_places(self):
        self.assertEqual(money("1.005"), Decimal("1.01"))
        self.assertEqual(money(2), Decimal("2.00"))
        self.assertEqual(money("10.999"), Decimal("11.00"))

    def test_all_monetary_columns_use_numeric_14_2(self):
        columns = (
            Product.price,
            Product.original_price,
            ProductVariant.price_adjustment,
            Wallet.balance,
            Transaction.amount,
            CheckoutOrder.total_amount,
            SellerOrder.subtotal,
            SellerOrder.shipping_fee,
            SellerOrder.platform_fee,
            SellerOrder.total_amount,
            OrderPayment.amount,
            OrderPayment.platform_fee,
            OrderPayment.seller_amount,
            OrderItem.price_at_purchase,
        )

        for column in columns:
            column_type = column.property.columns[0].type
            self.assertIsInstance(column_type, Numeric)
            self.assertEqual(column_type.precision, 14)
            self.assertEqual(column_type.scale, 2)

    def test_financial_invariants_exist_in_model_metadata(self):
        expected = {
            "products_original_price_check": Product,
            "product_variants_price_adjustment_range_check": ProductVariant,
            "wallets_balance_check": Wallet,
            "transactions_amount_nonzero_check": Transaction,
            "checkout_orders_total_amount_check": CheckoutOrder,
            "seller_orders_total_components_check": SellerOrder,
            "order_payments_allocation_check": OrderPayment,
            "order_items_price_at_purchase_check": OrderItem,
        }

        for constraint_name, model in expected.items():
            names = {constraint.name for constraint in model.__table__.constraints}
            self.assertIn(constraint_name, names)


if __name__ == "__main__":
    unittest.main()
