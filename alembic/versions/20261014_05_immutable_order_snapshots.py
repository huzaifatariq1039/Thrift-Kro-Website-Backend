"""Preserve immutable order fulfillment and product snapshots.

Revision ID: 20261014_05
Revises: 20261014_04
Create Date: 2026-10-14
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20261014_05"
down_revision: Union[str, Sequence[str], None] = "20261014_04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "checkout_orders",
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="PKR"),
    )
    op.add_column(
        "checkout_orders",
        sa.Column("shipping_address_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "checkout_orders",
        sa.Column("billing_address_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "seller_orders",
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="PKR"),
    )

    op.add_column("order_items", sa.Column("product_id_snapshot", sa.UUID(), nullable=True))
    op.add_column("order_items", sa.Column("product_name_snapshot", sa.String(), nullable=True))
    op.add_column("order_items", sa.Column("product_image_snapshot", sa.String(), nullable=True))
    op.add_column("order_items", sa.Column("sku_snapshot", sa.String(), nullable=True))
    op.add_column(
        "order_items",
        sa.Column(
            "variant_attributes_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "order_items",
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="PKR"),
    )

    op.execute(
        """
        UPDATE checkout_orders AS orders
        SET shipping_address_snapshot = jsonb_build_object(
            'type', addresses.type::text,
            'full_name', addresses.full_name,
            'phone_number', addresses.phone_number,
            'street_address', addresses.street_address,
            'city', addresses.city,
            'state_province', addresses.state_province,
            'postal_code', addresses.postal_code,
            'country', addresses.country
        )
        FROM user_addresses AS addresses
        WHERE orders.shipping_address_id = addresses.id
        """
    )
    op.execute(
        """
        UPDATE checkout_orders AS orders
        SET billing_address_snapshot = jsonb_build_object(
            'type', addresses.type::text,
            'full_name', addresses.full_name,
            'phone_number', addresses.phone_number,
            'street_address', addresses.street_address,
            'city', addresses.city,
            'state_province', addresses.state_province,
            'postal_code', addresses.postal_code,
            'country', addresses.country
        )
        FROM user_addresses AS addresses
        WHERE orders.billing_address_id = addresses.id
        """
    )
    op.execute(
        """
        UPDATE order_items AS items
        SET product_id_snapshot = products.id,
            product_name_snapshot = products.name,
            product_image_snapshot = (
                SELECT images.image_url
                FROM product_images AS images
                WHERE images.product_id = products.id
                ORDER BY images.is_primary DESC, images.display_order ASC, images.created_at ASC
                LIMIT 1
            ),
            sku_snapshot = variants.sku,
            variant_attributes_snapshot = COALESCE(variants.attributes, '{}'::jsonb)
        FROM product_variants AS variants
        JOIN products ON products.id = variants.product_id
        WHERE items.product_variant_id = variants.id
        """
    )

    op.alter_column("order_items", "product_id_snapshot", nullable=False)
    op.alter_column("order_items", "product_name_snapshot", nullable=False)


def downgrade() -> None:
    op.drop_column("order_items", "currency")
    op.drop_column("order_items", "variant_attributes_snapshot")
    op.drop_column("order_items", "sku_snapshot")
    op.drop_column("order_items", "product_image_snapshot")
    op.drop_column("order_items", "product_name_snapshot")
    op.drop_column("order_items", "product_id_snapshot")
    op.drop_column("seller_orders", "currency")
    op.drop_column("checkout_orders", "billing_address_snapshot")
    op.drop_column("checkout_orders", "shipping_address_snapshot")
    op.drop_column("checkout_orders", "currency")
