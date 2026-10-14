"""Enforce verified-purchase review integrity and trusted aggregates.

Revision ID: 20261014_10
Revises: 20261014_09
Create Date: 2026-10-14
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261014_10"
down_revision: Union[str, Sequence[str], None] = "20261014_09"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _review_order_item_fk_name() -> str:
    inspector = sa.inspect(op.get_bind())
    for foreign_key in inspector.get_foreign_keys("reviews"):
        if foreign_key.get("constrained_columns") == ["order_item_id"]:
            return foreign_key["name"]
    raise RuntimeError("reviews.order_item_id foreign key was not found")


def _recalculate_seller_aggregates() -> None:
    op.execute(
        sa.text(
            """
            UPDATE seller_profiles
            SET rating = 0.0,
                review_count = 0
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE seller_profiles AS sp
            SET rating = aggregates.rating,
                review_count = aggregates.review_count
            FROM (
                SELECT
                    p.seller_id,
                    ROUND(AVG(r.rating)::numeric, 2)::double precision AS rating,
                    COUNT(r.id)::integer AS review_count
                FROM reviews AS r
                JOIN products AS p ON p.id = r.product_id
                WHERE r.is_verified_purchase IS TRUE
                GROUP BY p.seller_id
            ) AS aggregates
            WHERE sp.user_id = aggregates.seller_id
            """
        )
    )


def upgrade() -> None:
    # Re-evaluate historical reviews from immutable order snapshots. Only one
    # canonical review per buyer/product can become trusted; other historical
    # rows remain retained but unverified and are excluded from public reads.
    op.execute("UPDATE reviews SET is_verified_purchase = false, order_item_id = NULL")
    op.execute(
        sa.text(
            """
            WITH canonical_reviews AS (
                SELECT DISTINCT ON (buyer_id, product_id)
                    id, buyer_id, product_id
                FROM reviews
                ORDER BY buyer_id, product_id, created_at NULLS LAST, id
            ),
            eligible_order_items AS (
                SELECT DISTINCT ON (co.buyer_id, oi.product_id_snapshot)
                    co.buyer_id,
                    oi.product_id_snapshot AS product_id,
                    oi.id AS order_item_id
                FROM order_items AS oi
                JOIN seller_orders AS so ON so.id = oi.seller_order_id
                JOIN checkout_orders AS co ON co.id = so.checkout_order_id
                WHERE so.status IN ('DELIVERED', 'COMPLETED', 'COMPLETED_PAYOUT')
                ORDER BY co.buyer_id, oi.product_id_snapshot, oi.created_at, oi.id
            )
            UPDATE reviews AS r
            SET is_verified_purchase = true,
                order_item_id = eligible.order_item_id
            FROM canonical_reviews AS canonical
            JOIN eligible_order_items AS eligible
              ON eligible.buyer_id = canonical.buyer_id
             AND eligible.product_id = canonical.product_id
            WHERE r.id = canonical.id
            """
        )
    )

    op.alter_column(
        "reviews",
        "is_verified_purchase",
        existing_type=sa.Boolean(),
        nullable=False,
        server_default=sa.false(),
    )
    op.drop_constraint(_review_order_item_fk_name(), "reviews", type_="foreignkey")
    op.create_foreign_key(
        "fk_reviews_order_item_id",
        "reviews",
        "order_items",
        ["order_item_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "reviews_verified_requires_order_item",
        "reviews",
        "is_verified_purchase IS FALSE OR order_item_id IS NOT NULL",
    )
    op.create_index(
        "uq_reviews_verified_buyer_product",
        "reviews",
        ["buyer_id", "product_id"],
        unique=True,
        postgresql_where=sa.text("is_verified_purchase IS TRUE"),
    )
    op.create_index(
        "uq_reviews_order_item",
        "reviews",
        ["order_item_id"],
        unique=True,
        postgresql_where=sa.text("order_item_id IS NOT NULL"),
    )
    _recalculate_seller_aggregates()


def downgrade() -> None:
    op.drop_index("uq_reviews_order_item", table_name="reviews")
    op.drop_index("uq_reviews_verified_buyer_product", table_name="reviews")
    op.drop_constraint("reviews_verified_requires_order_item", "reviews", type_="check")
    op.drop_constraint("fk_reviews_order_item_id", "reviews", type_="foreignkey")
    op.create_foreign_key(
        "reviews_order_item_id_fkey",
        "reviews",
        "order_items",
        ["order_item_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.alter_column(
        "reviews",
        "is_verified_purchase",
        existing_type=sa.Boolean(),
        nullable=True,
        server_default=sa.true(),
    )
