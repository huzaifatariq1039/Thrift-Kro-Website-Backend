import inspect
import os
import unittest
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-at-least-32-characters")

from app.crud import admin as legacy_admin
from app.schemas.admin import AdminStatsResponse as LegacyAdminStatsResponse
from app.schemas.admin_reporting import AdminStatsResponse
from app.services import admin_reporting


class AdminReportingContractTests(unittest.TestCase):
    def test_legacy_imports_delegate_to_typed_reporting_contract(self):
        self.assertIs(legacy_admin.get_platform_stats, admin_reporting.get_platform_stats)
        self.assertIs(LegacyAdminStatsResponse, AdminStatsResponse)

    def test_contract_distinguishes_checkout_and_seller_order_units(self):
        order_fields = AdminStatsResponse.model_fields["orders"].annotation.model_fields

        self.assertIn("total_checkout_orders", order_fields)
        self.assertIn("total_seller_orders", order_fields)
        self.assertNotIn("total_orders", order_fields)

    def test_financial_contract_names_settlement_and_recognition_states(self):
        revenue_fields = AdminStatsResponse.model_fields["revenue"].annotation.model_fields

        self.assertIn("settled_gmv_pkr", revenue_fields)
        self.assertIn("recognized_platform_revenue_pkr", revenue_fields)
        self.assertIn("escrow_held_pkr", revenue_fields)
        self.assertNotIn("total_platform_revenue_pkr", revenue_fields)

    def test_reporting_uses_payment_state_and_counts_all_users(self):
        source = inspect.getsource(admin_reporting.get_platform_stats)

        self.assertIn("total_users = _count(db, User.id)", source)
        self.assertIn("func.distinct(SellerOrder.checkout_order_id)", source)
        self.assertIn("OrderPayment.status == PaymentStatusEnum.SETTLED", source)
        self.assertIn("OrderPayment.status == PaymentStatusEnum.HELD", source)
        self.assertIn("SellerOrder.subtotal", source)

    def test_metric_definitions_are_documented(self):
        document = (
            Path(__file__).parents[1]
            / "docs"
            / "architecture"
            / "admin-reporting-metrics.md"
        ).read_text(encoding="utf-8")

        self.assertIn("One multi-vendor", document)
        self.assertIn("settled merchandise subtotal", document)
        self.assertIn("Held, pending, refunded, and cancelled", document)


if __name__ == "__main__":
    unittest.main()
