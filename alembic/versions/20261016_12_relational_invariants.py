"""Enforce relational invariants and index collection access paths.

Revision ID: 20261016_12
Revises: 20261015_11
Create Date: 2026-10-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261016_12"
down_revision: Union[str, Sequence[str], None] = "20261015_11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector():
    return sa.inspect(op.get_bind())


def _assert_no_rows(table: str, predicate: str, description: str) -> None:
    rows = op.get_bind().execute(
        sa.text(f"SELECT id FROM {table} WHERE {predicate} ORDER BY id LIMIT 5")
    ).scalars().all()
    if rows:
        sample = ", ".join(str(row_id) for row_id in rows)
        raise RuntimeError(
            f"Cannot enforce {description}; repair conflicting rows first. "
            f"Example row IDs: {sample}"
        )


def _assert_no_duplicates(table: str, columns: tuple[str, ...], description: str) -> None:
    column_list = ", ".join(columns)
    rows = op.get_bind().execute(
        sa.text(
            f"SELECT {column_list} FROM {table} "
            f"GROUP BY {column_list} HAVING COUNT(*) > 1 LIMIT 5"
        )
    ).all()
    if rows:
        sample = "; ".join(", ".join(str(value) for value in row) for row in rows)
        raise RuntimeError(
            f"Cannot enforce {description}; repair duplicate rows first. "
            f"Example keys: {sample}"
        )


def _has_unique_columns(table: str, columns: tuple[str, ...]) -> bool:
    expected = list(columns)
    if any(
        constraint.get("column_names") == expected
        for constraint in _inspector().get_unique_constraints(table)
    ):
        return True
    return any(
        index.get("unique") and index.get("column_names") == expected
        for index in _inspector().get_indexes(table)
    )


def _ensure_unique_constraint(name: str, table: str, columns: tuple[str, ...]) -> None:
    if not _has_unique_columns(table, columns):
        op.create_unique_constraint(name, table, list(columns))


def _ensure_check(name: str, table: str, condition: str) -> None:
    names = {constraint.get("name") for constraint in _inspector().get_check_constraints(table)}
    if name not in names:
        op.create_check_constraint(name, table, condition)


def _ensure_index(name: str, table: str, columns: tuple[str, ...]) -> None:
    indexes = _inspector().get_indexes(table)
    if any(index.get("name") == name for index in indexes):
        return
    if any(index.get("column_names") == list(columns) and not index.get("unique") for index in indexes):
        return
    op.create_index(name, table, list(columns))


def _drop_index_if_present(name: str, table: str) -> None:
    if any(index.get("name") == name for index in _inspector().get_indexes(table)):
        op.drop_index(name, table_name=table)


def upgrade() -> None:
    _assert_no_duplicates(
        "cart_items",
        ("cart_session_id", "product_variant_id"),
        "one cart line per session and product variant",
    )
    _assert_no_duplicates(
        "wishlist_items",
        ("user_id", "product_id"),
        "one wishlist entry per user and product",
    )
    _assert_no_rows(
        "product_images",
        "is_primary IS TRUE AND product_id IN ("
        "SELECT product_id FROM product_images WHERE is_primary IS TRUE "
        "GROUP BY product_id HAVING COUNT(*) > 1)",
        "one primary image per product",
    )
    _assert_no_rows(
        "product_variants",
        "quantity_in_stock < 0",
        "non-negative product stock",
    )
    _assert_no_rows("cart_items", "quantity <= 0", "positive cart quantities")
    _assert_no_rows("order_items", "quantity <= 0", "positive order quantities")
    _assert_no_rows("reviews", "rating < 1 OR rating > 5", "review ratings from 1 to 5")

    _ensure_unique_constraint(
        "uq_cart_items_session_variant",
        "cart_items",
        ("cart_session_id", "product_variant_id"),
    )
    _ensure_unique_constraint(
        "uq_wishlist_items_user_product",
        "wishlist_items",
        ("user_id", "product_id"),
    )
    _ensure_check(
        "product_variants_quantity_in_stock_check",
        "product_variants",
        "quantity_in_stock >= 0",
    )
    _ensure_check("cart_items_quantity_check", "cart_items", "quantity > 0")
    _ensure_check("order_items_quantity_check", "order_items", "quantity > 0")
    _ensure_check("reviews_rating_check", "reviews", "rating >= 1 AND rating <= 5")

    image_indexes = _inspector().get_indexes("product_images")
    if not any(index.get("name") == "uq_product_images_primary_per_product" for index in image_indexes):
        op.create_index(
            "uq_product_images_primary_per_product",
            "product_images",
            ["product_id"],
            unique=True,
            postgresql_where=sa.text("is_primary IS TRUE"),
        )

    for name, table, columns in (
        ("idx_checkout_orders_buyer_created", "checkout_orders", ("buyer_id", "created_at", "id")),
        ("idx_seller_orders_seller_created", "seller_orders", ("seller_id", "created_at", "id")),
        ("idx_cart_items_session_added", "cart_items", ("cart_session_id", "added_at")),
        ("idx_cart_items_variant", "cart_items", ("product_variant_id",)),
        ("idx_wishlist_items_user_added", "wishlist_items", ("user_id", "added_at")),
        ("idx_wishlist_items_product", "wishlist_items", ("product_id",)),
        ("idx_product_images_product_display", "product_images", ("product_id", "display_order")),
        ("idx_product_tags_product", "product_tags", ("product_id",)),
        ("idx_order_items_seller_order", "order_items", ("seller_order_id",)),
        ("idx_order_items_variant", "order_items", ("product_variant_id",)),
        (
            "idx_order_status_history_seller_created",
            "order_status_history",
            ("seller_order_id", "created_at"),
        ),
        ("idx_reviews_product_created", "reviews", ("product_id", "created_at", "id")),
        ("idx_messages_seller_order", "messages", ("seller_order_id",)),
        ("idx_support_tickets_user_created", "support_tickets", ("user_id", "created_at")),
        ("idx_support_tickets_seller_order", "support_tickets", ("seller_order_id",)),
    ):
        _ensure_index(name, table, columns)


def downgrade() -> None:
    for name, table in reversed((
        ("idx_checkout_orders_buyer_created", "checkout_orders"),
        ("idx_seller_orders_seller_created", "seller_orders"),
        ("idx_cart_items_session_added", "cart_items"),
        ("idx_cart_items_variant", "cart_items"),
        ("idx_wishlist_items_user_added", "wishlist_items"),
        ("idx_wishlist_items_product", "wishlist_items"),
        ("idx_product_images_product_display", "product_images"),
        ("idx_product_tags_product", "product_tags"),
        ("idx_order_items_seller_order", "order_items"),
        ("idx_order_items_variant", "order_items"),
        ("idx_order_status_history_seller_created", "order_status_history"),
        ("idx_reviews_product_created", "reviews"),
        ("idx_messages_seller_order", "messages"),
        ("idx_support_tickets_user_created", "support_tickets"),
        ("idx_support_tickets_seller_order", "support_tickets"),
    )):
        _drop_index_if_present(name, table)

    _drop_index_if_present("uq_product_images_primary_per_product", "product_images")
    unique_names = {
        constraint.get("name")
        for constraint in _inspector().get_unique_constraints("cart_items")
    }
    if "uq_cart_items_session_variant" in unique_names:
        op.drop_constraint("uq_cart_items_session_variant", "cart_items", type_="unique")
