"""Standardize mutable defaults and creation-time update timestamps.

Revision ID: 20261020_16
Revises: 20261018_15
Create Date: 2026-10-20
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261020_16"
down_revision: Union[str, Sequence[str], None] = "20261018_15"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


UPDATED_AT_TABLES = (
    "cart_sessions",
    "categories",
    "checkout_orders",
    "order_payments",
    "product_variants",
    "products",
    "reviews",
    "seller_orders",
    "seller_profiles",
    "seller_verification_requests",
    "support_tickets",
    "user_addresses",
    "users",
    "wallets",
)

JSON_LIST_COLUMNS = (
    "shop_photo_urls",
    "products_proof",
)


def upgrade() -> None:
    for table_name in UPDATED_AT_TABLES:
        op.execute(
            sa.text(
                f'UPDATE "{table_name}" '
                "SET updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP) "
                "WHERE updated_at IS NULL"
            )
        )
        op.alter_column(
            table_name,
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        )

    for column_name in JSON_LIST_COLUMNS:
        op.execute(
            sa.text(
                "UPDATE seller_verification_requests "
                f"SET {column_name} = '[]'::json WHERE {column_name} IS NULL"
            )
        )
        op.alter_column(
            "seller_verification_requests",
            column_name,
            existing_type=sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        )


def downgrade() -> None:
    for column_name in JSON_LIST_COLUMNS:
        op.alter_column(
            "seller_verification_requests",
            column_name,
            existing_type=sa.JSON(),
            nullable=True,
            server_default=sa.text("'[]'::json"),
        )

    for table_name in reversed(UPDATED_AT_TABLES):
        op.alter_column(
            table_name,
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=True,
            server_default=None,
        )
