"""Add explicit order payment allocations and COD completion.

Revision ID: 20261014_04
Revises: 20261014_03
Create Date: 2026-10-14
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20261014_04"
down_revision: Union[str, Sequence[str], None] = "20261014_03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


payment_status_enum = postgresql.ENUM(
    "PENDING", "HELD", "SETTLED", "REFUNDED", "CANCELLED",
    name="paymentstatusenum",
    create_type=False,
)
payment_method_enum = postgresql.ENUM(
    "WALLET", "CARD", "CASH_ON_DELIVERY",
    name="paymentmethodenum",
    create_type=False,
)


def upgrade() -> None:
    op.execute("ALTER TYPE orderstatusenum ADD VALUE IF NOT EXISTS 'COMPLETED'")
    payment_status_enum.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "order_payments",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("seller_order_id", sa.UUID(), nullable=False),
        sa.Column("payment_method", payment_method_enum, nullable=False),
        sa.Column("status", payment_status_enum, nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("platform_fee", sa.Float(), nullable=False),
        sa.Column("seller_amount", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="PKR"),
        sa.Column("provider_reference", sa.String(), nullable=True),
        sa.Column("recorded_by_id", sa.UUID(), nullable=True),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("amount >= 0.0", name="order_payments_amount_check"),
        sa.CheckConstraint("platform_fee >= 0.0", name="order_payments_platform_fee_check"),
        sa.CheckConstraint("seller_amount >= 0.0", name="order_payments_seller_amount_check"),
        sa.ForeignKeyConstraint(["seller_order_id"], ["seller_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recorded_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("seller_order_id", name="uq_order_payments_seller_order_id"),
        sa.UniqueConstraint("provider_reference", name="uq_order_payments_provider_reference"),
    )


def downgrade() -> None:
    op.drop_table("order_payments")
    payment_status_enum.drop(op.get_bind(), checkfirst=True)
    # PostgreSQL cannot remove one enum value safely. COMPLETED remains reserved.
