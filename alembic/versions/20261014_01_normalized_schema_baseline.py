"""Normalized marketplace schema baseline.

Revision ID: 20261014_01
Revises:
Create Date: 2026-10-14

Existing unversioned installations must be verified and stamped with
``python -m scripts.adopt_existing_database``. This migration intentionally
refuses to run over a non-empty application schema.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20261014_01"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


role_enum = postgresql.ENUM("BUYER", "SELLER", "ADMIN", name="roleenum", create_type=False)
business_type_enum = postgresql.ENUM(
    "INDIVIDUAL", "SHOP", "WAREHOUSE", name="businesstypeenum", create_type=False
)
verification_status_enum = postgresql.ENUM(
    "UNVERIFIED", "PENDING", "APPROVED", "REJECTED",
    name="verificationstatusenum",
    create_type=False,
)
condition_enum = postgresql.ENUM(
    "New", "Like New", "Excellent", "Very Good", "Good", "Fair", "Poor",
    name="conditionenum",
    create_type=False,
)
product_status_enum = postgresql.ENUM(
    "DRAFT", "AVAILABLE", "OUT_OF_STOCK", "ARCHIVED",
    name="productstatusenum",
    create_type=False,
)
payment_method_enum = postgresql.ENUM(
    "WALLET", "CARD", "CASH_ON_DELIVERY", name="paymentmethodenum", create_type=False
)
order_status_enum = postgresql.ENUM(
    "PENDING_PAYMENT", "PAID_FUNDS_IN_ESCROW", "PROCESSING", "SHIPPED",
    "DELIVERED", "COMPLETED_PAYOUT", "CANCELLED", "DISPUTED", "REFUNDED",
    name="orderstatusenum",
    create_type=False,
)
transaction_type_enum = postgresql.ENUM(
    "DEPOSIT", "WITHDRAWAL", "PAYMENT", "ESCROW_RELEASE", "REFUND", "PLATFORM_FEE",
    name="transactiontypeenum",
    create_type=False,
)
address_type_enum = postgresql.ENUM(
    "SHIPPING", "BILLING", "BUSINESS", name="addresstypeenum", create_type=False
)
ticket_type_enum = postgresql.ENUM(
    "COMPLAINT", "SUGGESTION", "DISPUTE", "OTHER_QUERY",
    name="tickettypeenum",
    create_type=False,
)
ticket_status_enum = postgresql.ENUM(
    "OPEN", "IN_PROGRESS", "RESOLVED", "CLOSED",
    name="ticketstatusenum",
    create_type=False,
)
notification_type_enum = postgresql.ENUM(
    "ORDER_UPDATE", "MESSAGE_RECEIVED", "PAYMENT_RECEIVED", "DISPUTE_OPENED", "SYSTEM_ALERT",
    name="notificationtypeenum",
    create_type=False,
)

ENUM_TYPES = (
    role_enum,
    business_type_enum,
    verification_status_enum,
    condition_enum,
    product_status_enum,
    payment_method_enum,
    order_status_enum,
    transaction_type_enum,
    address_type_enum,
    ticket_type_enum,
    ticket_status_enum,
    notification_type_enum,
)


def _uuid_primary_key(server_default: bool = True) -> sa.Column:
    default = sa.text("uuid_generate_v4()") if server_default else None
    return sa.Column("id", sa.UUID(), primary_key=True, server_default=default)


def _created_at() -> sa.Column:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")
    )


def _updated_at() -> sa.Column:
    return sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True)


def _assert_empty_application_schema() -> None:
    inspector = sa.inspect(op.get_bind())
    application_tables = set(inspector.get_table_names(schema="public")) - {"alembic_version"}
    if application_tables:
        raise RuntimeError(
            "Refusing to apply the baseline to a non-empty database. "
            "Run `python -m scripts.adopt_existing_database` first."
        )


def upgrade() -> None:
    offline = op.get_context().as_sql
    if not offline:
        _assert_empty_application_schema()
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    bind = op.get_bind()
    for enum_type in ENUM_TYPES:
        enum_type.create(bind, checkfirst=not offline)

    op.create_table(
        "categories",
        _uuid_primary_key(),
        sa.Column("parent_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("image_url", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true()),
        _created_at(),
        _updated_at(),
        sa.ForeignKeyConstraint(["parent_id"], ["categories.id"], ondelete="SET NULL"),
    )
    op.create_index("idx_categories_parent", "categories", ["parent_id"])

    op.create_table(
        "users",
        _uuid_primary_key(),
        sa.Column("email", sa.String(), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(), nullable=True),
        sa.Column("full_name", sa.String(), nullable=False),
        sa.Column("hex_code", sa.String(), nullable=False, unique=True),
        sa.Column("role", role_enum, nullable=False, server_default="BUYER"),
        sa.Column("avatar_url", sa.String(), nullable=True),
        sa.Column("auth_provider", sa.String(), nullable=False, server_default="local"),
        sa.Column("google_id", sa.String(), nullable=True, unique=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true()),
        _created_at(),
        _updated_at(),
    )
    op.create_index("idx_users_email", "users", ["email"])

    op.create_table(
        "cart_sessions",
        _uuid_primary_key(),
        sa.Column("user_id", sa.UUID(), nullable=False, unique=True),
        _created_at(),
        _updated_at(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "notifications",
        _uuid_primary_key(),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("type", notification_type_enum, nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("link", sa.String(), nullable=True),
        sa.Column("is_read", sa.Boolean(), server_default=sa.false()),
        _created_at(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_notifications_user", "notifications", ["user_id", "is_read"])

    op.create_table(
        "products",
        _uuid_primary_key(),
        sa.Column("seller_id", sa.UUID(), nullable=False),
        sa.Column("category_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("brand", sa.String(), nullable=True),
        sa.Column("condition", condition_enum, nullable=False, server_default="New"),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("original_price", sa.Float(), nullable=True),
        sa.Column("status", product_status_enum, nullable=False, server_default="AVAILABLE"),
        sa.Column("is_ai_verified", sa.Boolean(), server_default=sa.false()),
        sa.Column("verification_hash", sa.String(), nullable=True),
        _created_at(),
        _updated_at(),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("price >= 0.0", name="products_base_price_check"),
        sa.ForeignKeyConstraint(["seller_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="SET NULL"),
    )
    op.create_index("idx_products_catalog", "products", ["category_id", "status"])
    op.create_index("idx_products_seller", "products", ["seller_id"])
    op.create_index(
        "idx_products_name_trgm",
        "products",
        ["name"],
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )

    op.create_table(
        "seller_profiles",
        _uuid_primary_key(),
        sa.Column("user_id", sa.UUID(), nullable=True, unique=True),
        sa.Column("shop_name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("logo_url", sa.String(), nullable=True),
        sa.Column("business_type", business_type_enum, nullable=True),
        sa.Column("phone_number", sa.String(), nullable=True),
        sa.Column("address", sa.String(), nullable=True),
        sa.Column("city", sa.String(), nullable=True),
        sa.Column("cnic_number", sa.String(), nullable=True),
        sa.Column("is_verified", sa.Boolean(), server_default=sa.false()),
        sa.Column(
            "verification_status", verification_status_enum,
            nullable=False, server_default="UNVERIFIED",
        ),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rating", sa.Float(), server_default="0.0"),
        sa.Column("review_count", sa.Integer(), server_default="0"),
        _created_at(),
        _updated_at(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "user_addresses",
        _uuid_primary_key(),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("type", address_type_enum, nullable=False, server_default="SHIPPING"),
        sa.Column("full_name", sa.String(), nullable=False),
        sa.Column("phone_number", sa.String(), nullable=False),
        sa.Column("street_address", sa.String(), nullable=False),
        sa.Column("city", sa.String(), nullable=False),
        sa.Column("state_province", sa.String(), nullable=False),
        sa.Column("postal_code", sa.String(), nullable=False),
        sa.Column("country", sa.String(), nullable=False, server_default="Pakistan"),
        sa.Column("is_default", sa.Boolean(), server_default=sa.false()),
        _created_at(),
        _updated_at(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "wallets",
        _uuid_primary_key(),
        sa.Column("user_id", sa.UUID(), nullable=True, unique=True),
        sa.Column("balance", sa.Float(), server_default="0.0"),
        sa.Column("currency", sa.String(), server_default="PKR"),
        _created_at(),
        _updated_at(),
        sa.CheckConstraint("balance >= 0.0", name="wallets_balance_check"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "checkout_orders",
        _uuid_primary_key(),
        sa.Column("buyer_id", sa.UUID(), nullable=False),
        sa.Column("total_amount", sa.Float(), nullable=False),
        sa.Column("payment_method", payment_method_enum, nullable=False),
        sa.Column("shipping_address_id", sa.UUID(), nullable=True),
        sa.Column("billing_address_id", sa.UUID(), nullable=True),
        _created_at(),
        _updated_at(),
        sa.CheckConstraint("total_amount >= 0.0", name="checkout_orders_total_amount_check"),
        sa.ForeignKeyConstraint(["buyer_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["shipping_address_id"], ["user_addresses.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["billing_address_id"], ["user_addresses.id"], ondelete="SET NULL"
        ),
    )

    op.create_table(
        "product_images",
        _uuid_primary_key(),
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("image_url", sa.String(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.false()),
        sa.Column("display_order", sa.Integer(), server_default="0"),
        _created_at(),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "product_tags",
        _uuid_primary_key(),
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("tag_name", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "product_variants",
        _uuid_primary_key(),
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("sku", sa.String(), nullable=True, unique=True),
        sa.Column(
            "attributes", postgresql.JSONB(astext_type=sa.Text()),
            nullable=False, server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("price_adjustment", sa.Float(), server_default="0.0"),
        sa.Column("quantity_in_stock", sa.Integer(), nullable=False, server_default="1"),
        _created_at(),
        _updated_at(),
        sa.CheckConstraint(
            "quantity_in_stock >= 0", name="product_variants_quantity_in_stock_check"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_variants_product", "product_variants", ["product_id"])

    op.create_table(
        "seller_verification_requests",
        _uuid_primary_key(),
        sa.Column("seller_profile_id", sa.UUID(), nullable=False),
        sa.Column("business_name", sa.String(), nullable=False),
        sa.Column("business_type", business_type_enum, nullable=False),
        sa.Column("phone_number", sa.String(), nullable=True),
        sa.Column("address", sa.String(), nullable=True),
        sa.Column("city", sa.String(), nullable=True),
        sa.Column("cnic_number", sa.String(), nullable=True),
        sa.Column("cnic_front_url", sa.String(), nullable=False),
        sa.Column("cnic_back_url", sa.String(), nullable=False),
        sa.Column("business_reg_url", sa.String(), nullable=True),
        sa.Column("shop_photo_urls", sa.JSON(), server_default=sa.text("'[]'::json")),
        sa.Column("products_proof", sa.JSON(), server_default=sa.text("'[]'::json")),
        sa.Column("ai_verified", sa.Boolean(), server_default=sa.false()),
        sa.Column(
            "status", verification_status_enum, nullable=False, server_default="PENDING"
        ),
        sa.Column("rejection_reason", sa.String(), nullable=True),
        sa.Column("reviewed_by", sa.UUID(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        _updated_at(),
        sa.ForeignKeyConstraint(
            ["seller_profile_id"], ["seller_profiles.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="SET NULL"),
    )

    op.create_table(
        "transactions",
        _uuid_primary_key(),
        sa.Column("wallet_id", sa.UUID(), nullable=False),
        sa.Column("type", transaction_type_enum, nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("reference_id", sa.UUID(), nullable=True),
        sa.Column("reference_type", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="COMPLETED"),
        sa.Column("description", sa.String(), nullable=True),
        _created_at(),
        sa.ForeignKeyConstraint(["wallet_id"], ["wallets.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_transactions_wallet", "transactions", ["wallet_id"])

    op.create_table(
        "verification_logs",
        _uuid_primary_key(server_default=False),
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("seller_id", sa.UUID(), nullable=False),
        sa.Column("similarity_score", sa.Float(), nullable=True),
        sa.Column("detected_category", sa.String(), nullable=True),
        sa.Column("liveness_passed", sa.Boolean(), nullable=True),
        sa.Column("verification_hash", sa.String(), nullable=False, unique=True),
        sa.Column("is_successful", sa.Boolean(), nullable=True),
        _created_at(),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["seller_id"], ["users.id"]),
    )
    op.create_index("ix_verification_logs_id", "verification_logs", ["id"])
    op.create_index("ix_verification_logs_product_id", "verification_logs", ["product_id"])
    op.create_index("ix_verification_logs_seller_id", "verification_logs", ["seller_id"])

    op.create_table(
        "wishlist_items",
        _uuid_primary_key(),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "product_id"),
    )

    op.create_table(
        "cart_items",
        _uuid_primary_key(),
        sa.Column("cart_session_id", sa.UUID(), nullable=False),
        sa.Column("product_variant_id", sa.UUID(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("quantity > 0", name="cart_items_quantity_check"),
        sa.ForeignKeyConstraint(
            ["cart_session_id"], ["cart_sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["product_variant_id"], ["product_variants.id"], ondelete="CASCADE"
        ),
    )

    op.create_table(
        "seller_orders",
        _uuid_primary_key(),
        sa.Column("checkout_order_id", sa.UUID(), nullable=False),
        sa.Column("seller_id", sa.UUID(), nullable=False),
        sa.Column("subtotal", sa.Float(), nullable=False),
        sa.Column("shipping_fee", sa.Float(), nullable=False),
        sa.Column("platform_fee", sa.Float(), nullable=False),
        sa.Column("total_amount", sa.Float(), nullable=False),
        sa.Column(
            "status", order_status_enum, nullable=False, server_default="PENDING_PAYMENT"
        ),
        sa.Column("tracking_number", sa.String(), nullable=True),
        sa.Column("courier_name", sa.String(), nullable=True),
        sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        _updated_at(),
        sa.CheckConstraint("subtotal >= 0.0", name="seller_orders_subtotal_check"),
        sa.CheckConstraint("shipping_fee >= 0.0", name="seller_orders_shipping_fee_check"),
        sa.CheckConstraint("platform_fee >= 0.0", name="seller_orders_platform_fee_check"),
        sa.CheckConstraint("total_amount >= 0.0", name="seller_orders_total_amount_check"),
        sa.ForeignKeyConstraint(
            ["checkout_order_id"], ["checkout_orders.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["seller_id"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_index("idx_seller_orders_checkout", "seller_orders", ["checkout_order_id"])
    op.create_index("idx_seller_orders_seller", "seller_orders", ["seller_id", "status"])

    op.create_table(
        "messages",
        _uuid_primary_key(),
        sa.Column("sender_id", sa.UUID(), nullable=False),
        sa.Column("receiver_id", sa.UUID(), nullable=False),
        sa.Column("seller_order_id", sa.UUID(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("is_read", sa.Boolean(), server_default=sa.false()),
        _created_at(),
        sa.ForeignKeyConstraint(["sender_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["receiver_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["seller_order_id"], ["seller_orders.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "idx_messages_conversation",
        "messages",
        ["sender_id", "receiver_id", "created_at"],
    )

    op.create_table(
        "order_items",
        _uuid_primary_key(),
        sa.Column("seller_order_id", sa.UUID(), nullable=False),
        sa.Column("product_variant_id", sa.UUID(), nullable=False),
        sa.Column("price_at_purchase", sa.Float(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        _created_at(),
        sa.CheckConstraint("price_at_purchase >= 0.0", name="order_items_price_at_purchase_check"),
        sa.CheckConstraint("quantity > 0", name="order_items_quantity_check"),
        sa.ForeignKeyConstraint(
            ["seller_order_id"], ["seller_orders.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["product_variant_id"], ["product_variants.id"], ondelete="RESTRICT"
        ),
    )

    op.create_table(
        "order_status_history",
        _uuid_primary_key(),
        sa.Column("seller_order_id", sa.UUID(), nullable=False),
        sa.Column("status", order_status_enum, nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["seller_order_id"], ["seller_orders.id"], ondelete="CASCADE"
        ),
    )

    op.create_table(
        "support_tickets",
        _uuid_primary_key(),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("seller_order_id", sa.UUID(), nullable=True),
        sa.Column("type", ticket_type_enum, nullable=False),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", ticket_status_enum, nullable=False, server_default="OPEN"),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        _created_at(),
        _updated_at(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["seller_order_id"], ["seller_orders.id"], ondelete="SET NULL"
        ),
    )

    op.create_table(
        "reviews",
        _uuid_primary_key(),
        sa.Column("buyer_id", sa.UUID(), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("order_item_id", sa.UUID(), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("is_verified_purchase", sa.Boolean(), server_default=sa.true()),
        _created_at(),
        _updated_at(),
        sa.CheckConstraint("rating >= 1 AND rating <= 5", name="reviews_rating_check"),
        sa.ForeignKeyConstraint(["buyer_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_item_id"], ["order_items.id"], ondelete="SET NULL"),
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION update_timestamp_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = CURRENT_TIMESTAMP;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for table in (
        "users", "user_addresses", "wallets", "seller_profiles",
        "seller_verification_requests", "categories", "products",
        "product_variants", "cart_sessions", "checkout_orders",
        "seller_orders", "reviews", "support_tickets",
    ):
        op.execute(
            f"CREATE TRIGGER set_timestamp_{table} BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION update_timestamp_column()"
        )


def downgrade() -> None:
    for table in (
        "reviews", "support_tickets", "order_status_history", "order_items",
        "messages", "seller_orders", "cart_items", "wishlist_items",
        "verification_logs", "transactions", "seller_verification_requests",
        "product_variants", "product_tags", "product_images", "checkout_orders",
        "wallets", "user_addresses", "seller_profiles", "products",
        "notifications", "cart_sessions", "users", "categories",
    ):
        op.drop_table(table)

    op.execute("DROP FUNCTION IF EXISTS update_timestamp_column()")
    bind = op.get_bind()
    for enum_type in reversed(ENUM_TYPES):
        enum_type.drop(bind, checkfirst=True)
