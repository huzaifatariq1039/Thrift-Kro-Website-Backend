"""Safely adopt the existing unversioned pgAdmin database into Alembic.

The default mode is read-only. ``--apply`` performs only the two known schema
repairs and records the normalized baseline revision. It never creates, drops,
truncates, or reseeds application tables.
"""

import argparse
from dataclasses import dataclass, field
from typing import Mapping, Set

from sqlalchemy import inspect, text

from app.core.database import engine


BASELINE_REVISION = "20261014_01"

EXPECTED_COLUMNS = {
    "cart_items": {"id", "cart_session_id", "product_variant_id", "quantity", "added_at"},
    "cart_sessions": {"id", "user_id", "created_at", "updated_at"},
    "categories": {
        "id", "parent_id", "name", "slug", "description", "image_url", "is_active",
        "created_at", "updated_at",
    },
    "checkout_orders": {
        "id", "buyer_id", "total_amount", "payment_method", "shipping_address_id",
        "billing_address_id", "created_at", "updated_at",
    },
    "messages": {
        "id", "sender_id", "receiver_id", "seller_order_id", "content", "is_read", "created_at",
    },
    "notifications": {
        "id", "user_id", "type", "title", "message", "link", "is_read", "created_at",
    },
    "order_items": {
        "id", "seller_order_id", "product_variant_id", "price_at_purchase", "quantity", "created_at",
    },
    "order_status_history": {"id", "seller_order_id", "status", "notes", "created_at"},
    "product_images": {
        "id", "product_id", "image_url", "is_primary", "display_order", "created_at",
    },
    "product_tags": {"id", "product_id", "tag_name"},
    "product_variants": {
        "id", "product_id", "sku", "attributes", "price_adjustment", "quantity_in_stock",
        "created_at", "updated_at",
    },
    "products": {
        "id", "seller_id", "category_id", "name", "description", "brand", "condition", "price",
        "original_price", "status", "is_ai_verified", "verification_hash", "created_at",
        "updated_at", "deleted_at",
    },
    "reviews": {
        "id", "buyer_id", "product_id", "order_item_id", "rating", "comment",
        "is_verified_purchase", "created_at", "updated_at",
    },
    "seller_orders": {
        "id", "checkout_order_id", "seller_id", "subtotal", "shipping_fee", "platform_fee",
        "total_amount", "status", "tracking_number", "courier_name", "shipped_at", "delivered_at",
        "created_at", "updated_at",
    },
    "seller_profiles": {
        "id", "user_id", "shop_name", "description", "logo_url", "business_type", "phone_number",
        "address", "city", "cnic_number", "is_verified", "verification_status", "verified_at",
        "rating", "review_count", "created_at", "updated_at",
    },
    "seller_verification_requests": {
        "id", "seller_profile_id", "business_name", "business_type", "phone_number", "address",
        "city", "cnic_number", "cnic_front_url", "cnic_back_url", "business_reg_url",
        "shop_photo_urls", "products_proof", "ai_verified", "status", "rejection_reason",
        "reviewed_by", "reviewed_at", "created_at", "updated_at",
    },
    "support_tickets": {
        "id", "user_id", "seller_order_id", "type", "subject", "description", "status",
        "resolution_notes", "created_at", "updated_at",
    },
    "transactions": {
        "id", "wallet_id", "type", "amount", "reference_id", "reference_type", "status",
        "description", "created_at",
    },
    "user_addresses": {
        "id", "user_id", "type", "full_name", "phone_number", "street_address", "city",
        "state_province", "postal_code", "country", "is_default", "created_at", "updated_at",
    },
    "users": {
        "id", "email", "hashed_password", "full_name", "hex_code", "role", "avatar_url",
        "auth_provider", "google_id", "is_active", "created_at", "updated_at",
    },
    "verification_logs": {
        "id", "product_id", "seller_id", "similarity_score", "detected_category",
        "liveness_passed", "verification_hash", "is_successful", "created_at",
    },
    "wallets": {"id", "user_id", "balance", "currency", "created_at", "updated_at"},
    "wishlist_items": {"id", "user_id", "product_id", "added_at"},
}

REQUIRED_CHECKS = {
    "cart_items": {"cart_items_quantity_check"},
    "checkout_orders": {"checkout_orders_total_amount_check"},
    "order_items": {"order_items_price_at_purchase_check", "order_items_quantity_check"},
    "product_variants": {"product_variants_quantity_in_stock_check"},
    "products": {"products_base_price_check"},
    "reviews": {"reviews_rating_check"},
    "seller_orders": {
        "seller_orders_platform_fee_check", "seller_orders_shipping_fee_check",
        "seller_orders_subtotal_check", "seller_orders_total_amount_check",
    },
    "wallets": {"wallets_balance_check"},
}

EXPECTED_CONDITION_VALUES = ["New", "Like New", "Excellent", "Very Good", "Good", "Fair", "Poor"]
EXPECTED_NOTIFICATION_TYPES = {
    "ORDER_UPDATE", "MESSAGE_RECEIVED", "PAYMENT_RECEIVED", "DISPUTE_OPENED", "SYSTEM_ALERT"
}


@dataclass
class AdoptionReport:
    errors: list[str] = field(default_factory=list)
    repairs: list[str] = field(default_factory=list)

    @property
    def compatible(self) -> bool:
        return not self.errors


def compare_schema(
    actual_tables: Set[str],
    actual_columns: Mapping[str, Set[str]],
) -> AdoptionReport:
    report = AdoptionReport()
    expected_tables = set(EXPECTED_COLUMNS)

    missing_tables = sorted(expected_tables - actual_tables)
    extra_tables = sorted(actual_tables - expected_tables)
    if missing_tables:
        report.errors.append(f"missing tables: {', '.join(missing_tables)}")
    if extra_tables:
        report.errors.append(f"unexpected tables: {', '.join(extra_tables)}")

    for table in sorted(expected_tables & actual_tables):
        expected = EXPECTED_COLUMNS[table]
        actual = actual_columns[table]
        missing = expected - actual
        extra = actual - expected
        if table == "notifications" and missing == {"title"}:
            report.repairs.append("add and backfill notifications.title")
            missing = set()
        if missing:
            report.errors.append(f"{table} missing columns: {', '.join(sorted(missing))}")
        if extra:
            report.errors.append(f"{table} unexpected columns: {', '.join(sorted(extra))}")
    return report


def inspect_database(connection) -> tuple[str, AdoptionReport, bool]:
    inspector = inspect(connection)
    database_name = connection.execute(text("SELECT current_database()" )).scalar_one()
    all_tables = set(inspector.get_table_names(schema="public"))
    has_version_table = "alembic_version" in all_tables
    application_tables = all_tables - {"alembic_version"}
    columns = {
        table: {column["name"] for column in inspector.get_columns(table, schema="public")}
        for table in application_tables
    }
    report = compare_schema(application_tables, columns)

    for table, required in REQUIRED_CHECKS.items():
        if table not in application_tables:
            continue
        actual = {
            constraint["name"]
            for constraint in inspector.get_check_constraints(table, schema="public")
        }
        missing = required - actual
        if missing:
            report.errors.append(
                f"{table} missing safety constraints: {', '.join(sorted(missing))}"
            )

    enum_map = {
        item["name"]: item["labels"]
        for item in inspector.get_enums(schema="public")
    }
    if enum_map.get("conditionenum") != EXPECTED_CONDITION_VALUES:
        report.errors.append("conditionenum values do not match the normalized baseline")
    if set(enum_map.get("notificationtypeenum", [])) != EXPECTED_NOTIFICATION_TYPES:
        report.errors.append("notificationtypeenum values do not match the normalized baseline")

    notification_type = next(
        (
            column["type"]
            for column in inspector.get_columns("notifications", schema="public")
            if column["name"] == "type"
        ),
        None,
    )
    if notification_type is not None and getattr(notification_type, "name", None) != "notificationtypeenum":
        report.repairs.append("convert notifications.type to notificationtypeenum")

    return database_name, report, has_version_table


def apply_adoption(connection) -> None:
    connection.execute(text("SELECT pg_advisory_xact_lock(8675309)"))
    _, report, has_version_table = inspect_database(connection)
    if has_version_table:
        raise RuntimeError("alembic_version already exists; refusing to overwrite migration state")
    if not report.compatible:
        raise RuntimeError("Schema verification failed: " + "; ".join(report.errors))

    inspector = inspect(connection)
    notification_columns = {
        column["name"] for column in inspector.get_columns("notifications", schema="public")
    }
    if "title" not in notification_columns:
        connection.execute(text("ALTER TABLE notifications ADD COLUMN title VARCHAR"))
        connection.execute(
            text(
                "UPDATE notifications "
                "SET title = COALESCE(NULLIF(message, ''), 'Notification') "
                "WHERE title IS NULL"
            )
        )
        connection.execute(text("ALTER TABLE notifications ALTER COLUMN title SET NOT NULL"))

    type_row = connection.execute(
        text(
            "SELECT udt_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='notifications' AND column_name='type'"
        )
    ).scalar_one()
    if type_row != "notificationtypeenum":
        invalid = connection.execute(
            text(
                "SELECT DISTINCT type FROM notifications "
                "WHERE type NOT IN ('ORDER_UPDATE', 'MESSAGE_RECEIVED', 'PAYMENT_RECEIVED', "
                "'DISPUTE_OPENED', 'SYSTEM_ALERT')"
            )
        ).scalars().all()
        if invalid:
            raise RuntimeError(f"Unsupported notification types: {invalid}")
        connection.execute(
            text(
                "ALTER TABLE notifications ALTER COLUMN type TYPE notificationtypeenum "
                "USING type::notificationtypeenum"
            )
        )

    connection.execute(
        text(
            "CREATE TABLE alembic_version ("
            "version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
        )
    )
    connection.execute(
        text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
        {"revision": BASELINE_REVISION},
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the known repairs and stamp the verified database.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the database-name confirmation prompt (requires --apply).",
    )
    args = parser.parse_args()
    if args.yes and not args.apply:
        parser.error("--yes requires --apply")

    with engine.connect() as connection:
        transaction = connection.begin()
        connection.execute(text("SET TRANSACTION READ ONLY"))
        database_name, report, has_version_table = inspect_database(connection)
        transaction.rollback()

    print(f"Database: {database_name}")
    if has_version_table:
        print("Refusing adoption: alembic_version already exists.")
        raise SystemExit(1)
    if report.errors:
        for error in report.errors:
            print(f"ERROR: {error}")
        raise SystemExit(1)
    for repair in report.repairs:
        print(f"REPAIR: {repair}")
    print("Schema is compatible with the normalized baseline.")

    if not args.apply:
        print("Read-only verification complete. Re-run with --apply to adopt it.")
        return

    if not args.yes:
        confirmation = input(f"Type the database name '{database_name}' to continue: ")
        if confirmation != database_name:
            print("Confirmation did not match; no changes were made.")
            raise SystemExit(1)

    with engine.begin() as connection:
        apply_adoption(connection)
    print(f"Database adopted at Alembic revision {BASELINE_REVISION}.")


if __name__ == "__main__":
    main()
