"""Add checkout idempotency key.

Revision ID: 20261014_02
Revises: 20261014_01
Create Date: 2026-10-14
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261014_02"
down_revision: Union[str, Sequence[str], None] = "20261014_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "checkout_orders",
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
    )
    op.create_unique_constraint(
        "uq_checkout_orders_buyer_idempotency_key",
        "checkout_orders",
        ["buyer_id", "idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_checkout_orders_buyer_idempotency_key",
        "checkout_orders",
        type_="unique",
    )
    op.drop_column("checkout_orders", "idempotency_key")
