"""Serialize seller verification submissions and enforce one pending request.

Revision ID: 20261016_13
Revises: 20261016_12
Create Date: 2026-10-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261016_13"
down_revision: Union[str, Sequence[str], None] = "20261016_12"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PENDING_INDEX = "uq_seller_verification_one_pending"
HISTORY_INDEX = "idx_seller_verification_seller_created"


def _indexes() -> set[str]:
    return {
        index["name"]
        for index in sa.inspect(op.get_bind()).get_indexes(
            "seller_verification_requests"
        )
    }


def _assert_no_duplicate_pending_requests() -> None:
    conflicts = op.get_bind().execute(
        sa.text(
            """
            SELECT seller_profile_id, array_agg(id ORDER BY created_at, id)
            FROM seller_verification_requests
            WHERE status = 'PENDING'
            GROUP BY seller_profile_id
            HAVING COUNT(*) > 1
            ORDER BY seller_profile_id
            LIMIT 5
            """
        )
    ).all()
    if conflicts:
        examples = "; ".join(
            f"seller {seller_id}: {', '.join(str(request_id) for request_id in request_ids)}"
            for seller_id, request_ids in conflicts
        )
        raise RuntimeError(
            "Cannot enforce one pending seller-verification request; resolve "
            f"conflicting rows first. Examples: {examples}"
        )


def upgrade() -> None:
    _assert_no_duplicate_pending_requests()
    indexes = _indexes()
    if PENDING_INDEX not in indexes:
        op.create_index(
            PENDING_INDEX,
            "seller_verification_requests",
            ["seller_profile_id"],
            unique=True,
            postgresql_where=sa.text("status = 'PENDING'"),
        )
    if HISTORY_INDEX not in indexes:
        op.create_index(
            HISTORY_INDEX,
            "seller_verification_requests",
            ["seller_profile_id", "created_at", "id"],
        )


def downgrade() -> None:
    indexes = _indexes()
    if HISTORY_INDEX in indexes:
        op.drop_index(HISTORY_INDEX, table_name="seller_verification_requests")
    if PENDING_INDEX in indexes:
        op.drop_index(PENDING_INDEX, table_name="seller_verification_requests")
