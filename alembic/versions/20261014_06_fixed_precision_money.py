"""Use fixed-precision monetary columns and enforce accounting invariants.

Revision ID: 20261014_06
Revises: 20261014_05
Create Date: 2026-10-14
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261014_06"
down_revision: Union[str, Sequence[str], None] = "20261014_05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MONEY = sa.Numeric(precision=14, scale=2)

MONEY_COLUMNS = {
    "products": ("price", "original_price"),
    "product_variants": ("price_adjustment",),
    "wallets": ("balance",),
    "transactions": ("amount",),
    "checkout_orders": ("total_amount",),
    "seller_orders": ("subtotal", "shipping_fee", "platform_fee", "total_amount"),
    "order_payments": ("amount", "platform_fee", "seller_amount"),
    "order_items": ("price_at_purchase",),
}


def upgrade() -> None:
    op.execute("UPDATE wallets SET balance = 0.00 WHERE balance IS NULL")
    op.execute(
        "UPDATE product_variants SET price_adjustment = 0.00 "
        "WHERE price_adjustment IS NULL"
    )

    for table_name, columns in MONEY_COLUMNS.items():
        for column_name in columns:
            is_nullable = table_name == "products" and column_name == "original_price"
            op.alter_column(
                table_name,
                column_name,
                type_=MONEY,
                postgresql_using=f"round({column_name}::numeric, 2)",
                nullable=is_nullable,
                existing_nullable=is_nullable,
            )

    op.create_check_constraint(
        "products_original_price_check",
        "products",
        "original_price IS NULL OR original_price >= 0.0",
    )
    op.create_check_constraint(
        "product_variants_price_adjustment_range_check",
        "product_variants",
        "price_adjustment BETWEEN -10000000.00 AND 10000000.00",
    )
    op.create_check_constraint(
        "transactions_amount_nonzero_check",
        "transactions",
        "amount <> 0.0",
    )
    op.create_check_constraint(
        "seller_orders_total_components_check",
        "seller_orders",
        "total_amount = subtotal + shipping_fee + platform_fee",
    )
    op.create_check_constraint(
        "order_payments_allocation_check",
        "order_payments",
        "amount = platform_fee + seller_amount",
    )


def downgrade() -> None:
    op.drop_constraint("order_payments_allocation_check", "order_payments", type_="check")
    op.drop_constraint("seller_orders_total_components_check", "seller_orders", type_="check")
    op.drop_constraint("transactions_amount_nonzero_check", "transactions", type_="check")
    op.drop_constraint(
        "product_variants_price_adjustment_range_check",
        "product_variants",
        type_="check",
    )
    op.drop_constraint("products_original_price_check", "products", type_="check")

    for table_name, columns in MONEY_COLUMNS.items():
        for column_name in columns:
            op.alter_column(
                table_name,
                column_name,
                type_=sa.Float(),
                postgresql_using=f"{column_name}::double precision",
                existing_nullable=(table_name == "products" and column_name == "original_price"),
            )
