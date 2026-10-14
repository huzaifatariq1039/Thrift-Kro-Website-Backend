"""Add stable product variant lifecycle and preserve cart references.

Revision ID: 20261014_08
Revises: 20261014_07
Create Date: 2026-10-14
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261014_08"
down_revision: Union[str, Sequence[str], None] = "20261014_07"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _cart_variant_fk_name() -> str:
    inspector = sa.inspect(op.get_bind())
    for foreign_key in inspector.get_foreign_keys("cart_items"):
        if foreign_key.get("constrained_columns") == ["product_variant_id"]:
            return foreign_key["name"]
    raise RuntimeError("cart_items.product_variant_id foreign key was not found")


def upgrade() -> None:
    op.add_column(
        "product_variants",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "product_variants",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_product_variants_product_active",
        "product_variants",
        ["product_id", "is_active"],
    )
    op.create_check_constraint(
        "product_variants_archive_state_check",
        "product_variants",
        "(is_active AND archived_at IS NULL) OR (NOT is_active AND archived_at IS NOT NULL)",
    )

    op.drop_constraint(_cart_variant_fk_name(), "cart_items", type_="foreignkey")
    op.create_foreign_key(
        "fk_cart_items_product_variant_id",
        "cart_items",
        "product_variants",
        ["product_variant_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("fk_cart_items_product_variant_id", "cart_items", type_="foreignkey")
    op.create_foreign_key(
        "cart_items_product_variant_id_fkey",
        "cart_items",
        "product_variants",
        ["product_variant_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint(
        "product_variants_archive_state_check",
        "product_variants",
        type_="check",
    )
    op.drop_index("idx_product_variants_product_active", table_name="product_variants")
    op.drop_column("product_variants", "archived_at")
    op.drop_column("product_variants", "is_active")
