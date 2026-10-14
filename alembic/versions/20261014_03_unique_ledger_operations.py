"""Prevent duplicate ledger operations.

Revision ID: 20261014_03
Revises: 20261014_02
Create Date: 2026-10-14
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20261014_03"
down_revision: Union[str, Sequence[str], None] = "20261014_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_transactions_reference_operation",
        "transactions",
        ["reference_type", "reference_id", "type"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_transactions_reference_operation",
        "transactions",
        type_="unique",
    )
